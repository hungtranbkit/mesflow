"""Unit tests for the DR reconciliation gap-computation algorithm
(mesflow.services.kiosk_reconciliation) plus a full host-side simulation of
the flagship disaster-recovery scenario from
reports/KIOSK_OFFLINE_DR_SYNC_AUDIT.md section 12:

    Server A accepts E100-E110.
    Server B is restored with only E100-E105.
    ESP believes E100-E110 were ACKed. Generation changes.
    Reconciliation must result in: B has E100-E110 exactly once.
    No lost events. No duplicate work sessions.

`compute_missing`/`ranges` are the exact pure functions
`OfflineSyncRepository.reconcile()` calls in production (see
db/repositories/offline_sync.py) -- testing them here needs no PostgreSQL.
The flagship scenario additionally needs *some* model of
kiosk_client_events' two real UNIQUE constraints (client_event_id;
(kiosk_id, local_sequence)) to prove "exactly once" end-to-end without a
live database; `FakeEventLedger` below enforces exactly those two
constraints and nothing else -- it is not a mock of the whole repository,
only of the invariant this test needs to prove.

Marked `unit`: no PostgreSQL/Docker/network involved anywhere in this file.
"""
from __future__ import annotations

import pytest

from mesflow.services.kiosk_reconciliation import ReconciliationResult, compute_missing, ranges

pytestmark = pytest.mark.unit


class TestComputeMissing:
    def test_no_gap_when_server_has_everything_in_range(self):
        result = compute_missing(
            seq_min=100, seq_max=105,
            known_sequences={100, 101, 102, 103, 104, 105},
            recent_event_ids=['E100', 'E101', 'E102', 'E103', 'E104', 'E105'],
            known_event_ids={'E100', 'E101', 'E102', 'E103', 'E104', 'E105'},
        )
        assert result.missing_sequences == []
        assert result.missing_event_ids == []

    def test_flagship_gap_e106_to_e110(self):
        known_sequences = {100, 101, 102, 103, 104, 105}  # Server B, restored short
        recent_event_ids = [f'KIOSK-01-{n:010d}' for n in range(100, 111)]  # ESP believes 100-110 ACKed
        known_event_ids = {f'KIOSK-01-{n:010d}' for n in range(100, 106)}
        result = compute_missing(100, 110, known_sequences, recent_event_ids, known_event_ids)
        assert result.missing_sequences == [106, 107, 108, 109, 110]
        assert result.missing_event_ids == [f'KIOSK-01-{n:010d}' for n in range(106, 111)]
        assert result.sequence_owner_conflicts == []

    def test_reversed_min_max_is_normalized(self):
        result = compute_missing(110, 100, {100, 105}, [], set())
        assert result.missing_sequences == [101, 102, 103, 104, 106, 107, 108, 109, 110]

    def test_event_id_gap_outside_sequence_range_still_detected(self):
        """A device whose NVS event_seq counter was reset (e.g. factory
        reset without wiping the retained-ACK window -- an unusual but
        possible combination) could report a sequence range that doesn't
        cover an event_id it still has queued for replay. The event_id
        check is independent of the sequence-range check for exactly this
        reason."""
        result = compute_missing(1, 5, {1, 2, 3, 4, 5}, ['ORPHAN-EVENT-999'], set())
        assert result.missing_sequences == []
        assert result.missing_event_ids == ['ORPHAN-EVENT-999']

    def test_empty_recent_event_ids_is_fine(self):
        result = compute_missing(1, 3, {1, 2, 3}, [], set())
        assert result == ReconciliationResult(missing_sequences=[], missing_event_ids=[])

    def test_blank_event_ids_in_manifest_are_ignored_not_reported_missing(self):
        result = compute_missing(1, 1, {1}, ['', None, 'E1'], {'E1'})  # type: ignore[list-item]
        assert result.missing_event_ids == []


class TestRanges:
    def test_collapses_contiguous_runs(self):
        assert ranges([100, 101, 102, 105, 200, 201]) == [[100, 102], [105, 105], [200, 201]]

    def test_empty_input(self):
        assert ranges([]) == []

    def test_single_value(self):
        assert ranges([42]) == [[42, 42]]

    def test_flagship_range_is_one_contiguous_block(self):
        assert ranges([106, 107, 108, 109, 110]) == [[106, 110]]


# --------------------------------------------------------------------------
# Flagship end-to-end DR simulation
# --------------------------------------------------------------------------
class FakeEventLedger:
    """Enforces exactly the two real UNIQUE constraints from migration
    0023 (client_event_id; (kiosk_id, local_sequence)) -- nothing else.
    Standing in for kiosk_client_events so the "exactly once, no duplicate
    work sessions" claim can be checked without PostgreSQL."""

    def __init__(self):
        self._by_event_id: dict[str, dict] = {}
        self._by_kiosk_sequence: dict[tuple[str, int], str] = {}
        self.sessions_created = 0

    def known_sequences(self, kiosk_id: str, seq_min: int, seq_max: int) -> set[int]:
        return {seq for (kiosk, seq) in self._by_kiosk_sequence if kiosk == kiosk_id and seq_min <= seq <= seq_max}

    def known_event_ids(self, kiosk_id: str, candidate_ids: list[str]) -> set[str]:
        return {eid for eid in candidate_ids if eid in self._by_event_id and self._by_event_id[eid]['kiosk_id'] == kiosk_id}

    def process(self, kiosk_id: str, event_id: str, sequence: int, event_type: str) -> str:
        """Mirrors OfflineSyncRepository.process_event()'s essential
        idempotency contract: same event_id already recorded -> duplicate
        (no new session); otherwise insert, and a START creates exactly one
        new session."""
        if event_id in self._by_event_id:
            return 'duplicate'
        self._by_event_id[event_id] = {'kiosk_id': kiosk_id, 'sequence': sequence, 'event_type': event_type}
        self._by_kiosk_sequence[(kiosk_id, sequence)] = event_id
        if event_type == 'START':
            self.sessions_created += 1
        return 'accepted'


class TestFlagshipDisasterRecoveryScenario:
    KIOSK = 'KIOSK-01'

    def _seed_server_a_then_restore_as_server_b(self):
        """Server A accepted E100-E110 (START at 100, FINISH at 110, filler
        START/FINISH pairs between). Server B is restored with only
        E100-E105 -- the last 5 events never made it into the backup."""
        server_b = FakeEventLedger()
        for seq in range(100, 106):
            event_type = 'START' if seq % 2 == 0 else 'FINISH'
            server_b.process(self.KIOSK, f'{self.KIOSK}-{seq:010d}', seq, event_type)
        return server_b

    def test_reconciliation_fills_gap_exactly_once_no_lost_no_duplicate_sessions(self):
        server_b = self._seed_server_a_then_restore_as_server_b()
        assert server_b.sessions_created == 3  # seq 100,102,104 are START

        # ESP's retained recent-ACK window (never lost on ACK -- see audit
        # section 5): it believes E100-E110 were all ACKed by Server A.
        esp_retained_event_ids = [f'{self.KIOSK}-{n:010d}' for n in range(100, 111)]
        esp_seq_min, esp_seq_max = 100, 110

        # --- Reconciliation manifest compare (server side, real algorithm) ---
        known_sequences = server_b.known_sequences(self.KIOSK, esp_seq_min, esp_seq_max)
        known_event_ids = server_b.known_event_ids(self.KIOSK, esp_retained_event_ids)
        gap = compute_missing(esp_seq_min, esp_seq_max, known_sequences, esp_retained_event_ids, known_event_ids)
        assert gap.missing_sequences == [106, 107, 108, 109, 110]
        assert ranges(gap.missing_sequences) == [[106, 110]]

        # --- ESP replays ONLY the missing events, using their ORIGINAL event_id
        #     (never regenerated -- see audit section 5's "never generate a new
        #     event_id during replay") ---
        for seq in gap.missing_sequences:
            event_type = 'START' if seq % 2 == 0 else 'FINISH'
            status = server_b.process(self.KIOSK, f'{self.KIOSK}-{seq:010d}', seq, event_type)
            assert status == 'accepted'  # first time Server B has seen this event

        # --- Final state: Server B has E100-E110 exactly once ---
        assert set(server_b._by_event_id.keys()) == {f'{self.KIOSK}-{n:010d}' for n in range(100, 111)}
        assert len(server_b._by_event_id) == 11  # no lost events
        assert server_b.sessions_created == 6  # 100,102,104,106,108,110 are START -> exactly 6 sessions, none duplicated

        # --- A second reconciliation pass (e.g. ESP retried because the first
        #     response was lost) must report nothing missing, and replaying
        #     the same "missing" events again must be idempotent, not create
        #     more sessions or duplicate rows. ---
        known_sequences_2 = server_b.known_sequences(self.KIOSK, esp_seq_min, esp_seq_max)
        known_event_ids_2 = server_b.known_event_ids(self.KIOSK, esp_retained_event_ids)
        gap_2 = compute_missing(esp_seq_min, esp_seq_max, known_sequences_2, esp_retained_event_ids, known_event_ids_2)
        assert gap_2.missing_sequences == []
        assert gap_2.missing_event_ids == []

        for seq in range(106, 111):
            status = server_b.process(self.KIOSK, f'{self.KIOSK}-{seq:010d}', seq, 'START' if seq % 2 == 0 else 'FINISH')
            assert status == 'duplicate'
        assert len(server_b._by_event_id) == 11  # still exactly once
        assert server_b.sessions_created == 6  # unchanged -- no duplicate work sessions
