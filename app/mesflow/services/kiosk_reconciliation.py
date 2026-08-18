"""Pure DR reconciliation gap-computation logic (no DB access).

Kept separate from OfflineSyncRepository so the exact gap-detection
algorithm used in production is directly unit-testable without a live
PostgreSQL connection -- see mesflow/tests/test_kiosk_reconciliation.py and
reports/KIOSK_OFFLINE_DR_SYNC_AUDIT.md section 7.

This is the server side of the reconciliation protocol: the kiosk sends its
local sequence range plus the event_ids it believes are already ACKed
(retained in its recent-ACK replay window -- see esp-kiosk/esp/mesflow_app.cpp
section "Offline cache + append-only event journal"). The server compares
that against what it actually has recorded and returns exactly what's
missing. The kiosk replays ONLY those -- never a full resend -- and the
existing kiosk_client_events idempotency (client_event_id UNIQUE,
(kiosk_id, local_sequence) UNIQUE) remains the final safety net regardless
of what this function computes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReconciliationResult:
    missing_sequences: list[int]
    missing_event_ids: list[str]
    # Sequences the kiosk claimed but the server has under a DIFFERENT
    # event_id at that (kiosk_id, local_sequence) slot -- structurally
    # impossible under the UNIQUE(kiosk_id, local_sequence) constraint for
    # accepted rows, so this is always empty today; kept as an explicit,
    # named field (not silently folded into missing_sequences) so a future
    # change to that invariant fails loudly here instead of being papered
    # over as "just another gap" -- see audit section 13 ("never silently
    # convert conflict into success").
    sequence_owner_conflicts: list[int] = field(default_factory=list)


def compute_missing(
    seq_min: int,
    seq_max: int,
    known_sequences: set[int],
    recent_event_ids: list[str],
    known_event_ids: set[str],
) -> ReconciliationResult:
    """`known_sequences`/`known_event_ids`: what the server actually has a
    kiosk_client_events row for (any terminal status -- accepted, duplicate
    is not a stored status but accepted covers it, or rejected all count as
    "received", since a REJECTED event is resolved, not missing). A true
    gap is a sequence number in [seq_min, seq_max] the server has never
    seen at all, or an event_id the kiosk believes is ACKed that the server
    has no record of under any sequence."""
    if seq_max < seq_min:
        seq_min, seq_max = seq_max, seq_min

    missing_sequences = sorted(
        seq for seq in range(seq_min, seq_max + 1) if seq not in known_sequences
    )
    missing_event_ids = [eid for eid in recent_event_ids if eid and eid not in known_event_ids]

    return ReconciliationResult(
        missing_sequences=missing_sequences,
        missing_event_ids=missing_event_ids,
    )


def ranges(sorted_sequences: list[int]) -> list[list[int]]:
    """Collapse a sorted list of individual sequence numbers into contiguous
    [start, end] ranges -- a compact wire format so a device missing 200
    consecutive events doesn't need 200 individual numbers in the response.
    ranges([100,101,102,105]) -> [[100,102],[105,105]]."""
    if not sorted_sequences:
        return []
    out: list[list[int]] = []
    start = prev = sorted_sequences[0]
    for seq in sorted_sequences[1:]:
        if seq == prev + 1:
            prev = seq
            continue
        out.append([start, prev])
        start = prev = seq
    out.append([start, prev])
    return out
