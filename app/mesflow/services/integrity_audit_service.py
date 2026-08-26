"""Read-only database invariant auditor.

Backs `mesflow audit-integrity` (cli.py). Every query here is a plain
SELECT -- this module never writes anything, by design (see Gate 3 of the
2026-08-26 Reliability Validation Round 2 request: "Never auto-repair").

This complements session_audit_service.audit() (which is about *staleness*
-- sessions that should have been closed by now) with checks about
*correctness* -- rows that should never exist at all if every write path
and DB constraint behaved. Most of these are defense-in-depth: the
condition is already supposed to be impossible (a CHECK constraint, a FK,
a partial UNIQUE index), and a non-empty category here means that
assumption broke somewhere -- a raw SQL fix during an incident, a
constraint dropped by a bad migration, a partially-restored backup, or a
genuine application bug. Intended to be run after every chaos/load/soak
phase, per the same request's rule: "After every chaos/load phase run:
audit-sessions / audit-integrity."
"""
from __future__ import annotations

from typing import Any

from mesflow.db.connection import fetch_all


def _status_ended_at_mismatch() -> list[dict[str, Any]]:
    # Invariant: CLOSED <=> ended_at IS NOT NULL (this holds both directions
    # -- an OPEN session must never carry a stale ended_at either, which
    # would be just as confusing to any code that branches on one field but
    # displays the other).
    return fetch_all("""
        SELECT id,employee_id,operation_id,status,started_at,ended_at
        FROM work_sessions
        WHERE (status='CLOSED' AND ended_at IS NULL) OR (status='OPEN' AND ended_at IS NOT NULL)
        ORDER BY id""")


def _negative_quantity() -> list[dict[str, Any]]:
    # rework_qty already has a DB CHECK constraint (rework_qty>=0 AND
    # rework_qty<=defect_qty, migration 0022); good_qty/defect_qty do not --
    # this is the only thing standing between a bad code path and a
    # negative quantity silently corrupting every report built on top of
    # these columns.
    return fetch_all("""
        SELECT id,employee_id,operation_id,status,good_qty,defect_qty,rework_qty
        FROM work_sessions
        WHERE good_qty<0 OR defect_qty<0 OR rework_qty<0 OR rework_qty>defect_qty
        ORDER BY id""")


def _ended_before_started() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT id,employee_id,operation_id,started_at,ended_at,status
        FROM work_sessions WHERE ended_at IS NOT NULL AND ended_at<started_at
        ORDER BY started_at""")


def _multiple_open_per_employee() -> list[dict[str, Any]]:
    # Defense check for uq_open_session_per_employee (migration 0003: a
    # partial UNIQUE index on work_sessions(employee_id) WHERE
    # status='OPEN'). Should always be empty by construction; a non-empty
    # result means that index was dropped, bypassed by a raw write, or
    # never actually applied against this database.
    return fetch_all("""
        SELECT employee_id,COUNT(*) open_count,array_agg(id ORDER BY id) session_ids
        FROM work_sessions WHERE status='OPEN'
        GROUP BY employee_id HAVING COUNT(*)>1
        ORDER BY employee_id""")


def _orphan_employee() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT ws.id,ws.employee_id,ws.operation_id,ws.status,ws.started_at
        FROM work_sessions ws LEFT JOIN employees e ON e.id=ws.employee_id
        WHERE e.id IS NULL ORDER BY ws.id""")


def _orphan_operation() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT ws.id,ws.employee_id,ws.operation_id,ws.status,ws.started_at
        FROM work_sessions ws LEFT JOIN operations o ON o.id=ws.operation_id
        WHERE o.id IS NULL ORDER BY ws.id""")


def _orphan_part_or_po() -> list[dict[str, Any]]:
    # operations.part_id/production_order_id both carry FK CASCADE -- an
    # orphan here would mean a part/PO was deleted without cascading
    # correctly, which would then make every session on that operation
    # reference production context that no longer exists.
    return fetch_all("""
        SELECT o.id operation_id,o.production_order_id,o.part_id
        FROM operations o
        LEFT JOIN production_orders po ON po.id=o.production_order_id
        LEFT JOIN parts p ON p.id=o.part_id
        WHERE po.id IS NULL OR p.id IS NULL
        ORDER BY o.id""")


def _duplicate_close_event() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT session_id,COUNT(*) close_event_count,array_agg(id ORDER BY id) event_ids
        FROM production_trace_events WHERE event_type='SESSION_FINISHED' AND session_id IS NOT NULL
        GROUP BY session_id HAVING COUNT(*)>1 ORDER BY session_id""")


def _duplicate_auto_close_event() -> list[dict[str, Any]]:
    return fetch_all("""
        SELECT session_id,COUNT(*) auto_close_event_count,array_agg(id ORDER BY id) event_ids
        FROM production_trace_events WHERE event_type='SESSION_AUTO_CLOSED' AND session_id IS NOT NULL
        GROUP BY session_id HAVING COUNT(*)>1 ORDER BY session_id""")


def _auto_close_changed_quantity() -> list[dict[str, Any]]:
    # Invariant: AUTO_SHIFT_END must never fake/change quantity -- a
    # SESSION_AUTO_CLOSED trace event should only ever touch status/ended_at,
    # never carry a non-null quantity_delta. auto_close_for_shift_end()
    # itself never sets good_qty/defect_qty, but this checks the actual
    # emitted event, not just the code's intent -- catches a regression
    # that started attaching a quantity_delta to that event type.
    return fetch_all("""
        SELECT id,session_id,quantity_delta,occurred_at
        FROM production_trace_events
        WHERE event_type='SESSION_AUTO_CLOSED' AND quantity_delta IS NOT NULL AND quantity_delta<>0
        ORDER BY id""")


def _duplicate_quantity_movement() -> list[dict[str, Any]]:
    # Invariant: quantity movements don't duplicate one logical event --
    # a movement carrying a non-empty correlation_id should never appear
    # more than once for the same session/type/delta under that
    # correlation_id (the standard idempotency-key shape used elsewhere in
    # this codebase, e.g. kiosk_idempotency.request_id).
    return fetch_all("""
        SELECT correlation_id,session_id,movement_type,delta,COUNT(*) occurrence_count,array_agg(id ORDER BY id) movement_ids
        FROM quantity_movements
        WHERE correlation_id<>''
        GROUP BY correlation_id,session_id,movement_type,delta HAVING COUNT(*)>1
        ORDER BY correlation_id""")


def _duplicate_offline_event() -> list[dict[str, Any]]:
    # Defense check for kiosk_client_events.client_event_id's UNIQUE
    # constraint (migration 0023) -- offline replay dedup depends entirely
    # on that constraint; this is the same "verify the assumption, don't
    # just trust it" pattern as _multiple_open_per_employee().
    return fetch_all("""
        SELECT client_event_id,COUNT(*) occurrence_count,array_agg(id ORDER BY id) event_ids
        FROM kiosk_client_events
        GROUP BY client_event_id HAVING COUNT(*)>1
        ORDER BY client_event_id""")


def _closed_session_operation_still_completed_conflict() -> list[dict[str, Any]]:
    # Invariant: Operation/PO state compatible with work-session state --
    # an Operation already marked COMPLETED should not have a session still
    # OPEN against it (this is also surfaced live as the
    # OPERATION_COMPLETED_SESSION_OPEN exception in exception_service.py;
    # checking it here too means the raw data condition is caught even if
    # the exception detector's reconcile() didn't run or was disabled).
    return fetch_all("""
        SELECT ws.id session_id,ws.employee_id,ws.operation_id,o.status operation_status,ws.started_at
        FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
        WHERE ws.status='OPEN' AND o.status='COMPLETED'
        ORDER BY ws.id""")


def _inactive_kiosk_with_live_status() -> list[dict[str, Any]]:
    # Invariant: a DISABLED/PENDING kiosk identity can't become ACTIVE via
    # execution -- heartbeat()/execution requests already gate on
    # status='ACTIVE' (see KioskRepository.heartbeat() and
    # _legacy_kiosk_identity()), so a DISABLED/PENDING identity with a
    # *recent* kiosk_status heartbeat would mean that gate was bypassed
    # somewhere. A stale heartbeat from before the identity was disabled is
    # expected and not flagged -- only one within the last 24h, i.e. one
    # that could only have happened after whatever disabled it.
    return fetch_all("""
        SELECT ki.id identity_id,ki.device_uuid,ki.status identity_status,ks.last_heartbeat_at
        FROM kiosk_identities ki JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid
        WHERE ki.status IN ('DISABLED','PENDING') AND ks.last_heartbeat_at>CURRENT_TIMESTAMP-INTERVAL '24 hours'
        ORDER BY ki.id""")


def audit_integrity() -> dict[str, list[dict[str, Any]]]:
    """Run every invariant check and return {category: [violations]}.

    Read-only. An empty list for a category means that invariant held
    across every row checked; it does not mean the category was skipped."""
    return {
        'STATUS_ENDED_AT_MISMATCH': _status_ended_at_mismatch(),
        'NEGATIVE_QUANTITY': _negative_quantity(),
        'ENDED_BEFORE_STARTED': _ended_before_started(),
        'MULTIPLE_OPEN_PER_EMPLOYEE': _multiple_open_per_employee(),
        'ORPHAN_EMPLOYEE': _orphan_employee(),
        'ORPHAN_OPERATION': _orphan_operation(),
        'ORPHAN_PART_OR_PO': _orphan_part_or_po(),
        'DUPLICATE_CLOSE_EVENT': _duplicate_close_event(),
        'DUPLICATE_AUTO_CLOSE_EVENT': _duplicate_auto_close_event(),
        'AUTO_CLOSE_CHANGED_QUANTITY': _auto_close_changed_quantity(),
        'DUPLICATE_QUANTITY_MOVEMENT': _duplicate_quantity_movement(),
        'DUPLICATE_OFFLINE_EVENT': _duplicate_offline_event(),
        'OPERATION_COMPLETED_SESSION_STILL_OPEN': _closed_session_operation_still_completed_conflict(),
        'INACTIVE_KIOSK_WITH_LIVE_STATUS': _inactive_kiosk_with_live_status(),
    }
