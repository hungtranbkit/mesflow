"""P1 business-logic audit (2026-08-28) -- regression coverage for the three
targeted fixes beyond the employee-productivity/wallboard rewrite (see
test_employee_productivity.py/test_employee_productivity_wallboard.py for
that half):

1. PAUSED status (PO and Operation) must survive an ordinary reconcile
   (finishing an already-open session, etc.) -- it was silently reverting
   to IN_PROGRESS the moment any reportable history existed, defeating the
   entire purpose of an explicit supervisor pause.
2. SupervisorRepository.edit_session() must lock its owning PO(s) BEFORE
   the session row, same as every sibling session-mutating method -- it
   was the one remaining method locking session-then-PO, a real deadlock
   opportunity against a concurrent finish() on the same session.
3. ExceptionRepository.detected_conditions() must not keep generating
   review noise for a session a supervisor already explicitly excluded
   from reporting.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from mesflow.db.repositories.execution import WorkSessionRepository, SupervisorRepository
from mesflow.db.repositories.production_state import reconcile_production_order
from mesflow.db.connection import transaction
from mesflow.db.repositories.exceptions import ExceptionRepository

pytestmark = pytest.mark.postgres

_sessions = WorkSessionRepository()
_supervisor = SupervisorRepository()


# --- 1. PAUSED stickiness ----------------------------------------------

def test_paused_po_survives_finishing_an_already_open_session(db, seeded_factory):
    g = seeded_factory
    sid = _sessions.start({'request_id': f'p1-pause-start-{uuid.uuid4()}', 'employee_id': g['employee_id'],
                            'operation_id': g['operation_id'], 'station_id': g['station_id']})['session']['id']

    with db.cursor() as cur:
        cur.execute("UPDATE production_orders SET status='PAUSED' WHERE id=%s", (g['po_id'],))

    # Finishing a session that was already OPEN before the pause must not
    # itself be blocked (see WorkSessionRepository.finish()'s own lack of a
    # PO-status gate, confirmed in this same audit) -- the bug under test
    # is specifically that doing so must not silently un-pause the PO.
    _sessions.finish(sid, {'request_id': f'p1-pause-finish-{uuid.uuid4()}', 'good_qty': 5, 'defect_qty': 0})

    with db.cursor() as cur:
        cur.execute('SELECT status FROM production_orders WHERE id=%s', (g['po_id'],))
        assert cur.fetchone()['status'] == 'PAUSED', 'an explicit pause must survive an ordinary reconcile'


def test_paused_operation_survives_reconcile_with_existing_history(db, seeded_factory):
    g = seeded_factory
    sid = _sessions.start({'request_id': f'p1-pauseop-start-{uuid.uuid4()}', 'employee_id': g['employee_id'],
                            'operation_id': g['operation_id'], 'station_id': g['station_id']})['session']['id']
    _sessions.finish(sid, {'request_id': f'p1-pauseop-finish-{uuid.uuid4()}', 'good_qty': 1, 'defect_qty': 0})

    with db.cursor() as cur:
        cur.execute("UPDATE operations SET status='PAUSED' WHERE id=%s", (g['operation_id'],))
        # Any reconcile trigger with real (reportable) history now present
        # for this operation used to flip it straight back to IN_PROGRESS.
        cur.execute('SELECT production_order_id FROM operations WHERE id=%s', (g['operation_id'],))
        po_id = cur.fetchone()['production_order_id']

    with transaction() as conn:
        with conn.cursor() as cur:
            from mesflow.db.repositories.production_state import reconcile_operation_and_po
            reconcile_operation_and_po(cur, g['operation_id'])

    with db.cursor() as cur:
        cur.execute('SELECT status FROM operations WHERE id=%s', (g['operation_id'],))
        assert cur.fetchone()['status'] == 'PAUSED'


def test_paused_po_still_completes_when_target_is_actually_met(db, seeded_factory):
    """PAUSED must not be sticky to the point of masking real completion --
    confirms the fix didn't over-correct."""
    g = seeded_factory
    with db.cursor() as cur:
        # An Operation's "planned" target is read from its PARENT PO's own
        # planned_quantity column (see reconcile_operation()'s own query --
        # operations has no planned_quantity column of its own).
        cur.execute("UPDATE production_orders SET planned_quantity=5 WHERE id=%s", (g['po_id'],))
    sid = _sessions.start({'request_id': f'p1-pausedone-start-{uuid.uuid4()}', 'employee_id': g['employee_id'],
                            'operation_id': g['operation_id'], 'station_id': g['station_id']})['session']['id']
    with db.cursor() as cur:
        cur.execute("UPDATE production_orders SET status='PAUSED' WHERE id=%s", (g['po_id'],))
    _sessions.finish(sid, {'request_id': f'p1-pausedone-finish-{uuid.uuid4()}', 'good_qty': 5, 'defect_qty': 0})

    with db.cursor() as cur:
        cur.execute('SELECT status FROM operations WHERE id=%s', (g['operation_id'],))
        assert cur.fetchone()['status'] == 'COMPLETED'
        # All operations under the PO complete -> PO completes too, even
        # from PAUSED (single-operation fixture, so this PO has exactly
        # one operation).
        cur.execute('SELECT status FROM production_orders WHERE id=%s', (g['po_id'],))
        assert cur.fetchone()['status'] == 'COMPLETED'


# --- 2. edit_session() lock ordering -------------------------------------

def test_edit_session_locks_po_before_session_row_same_as_finish(db, seeded_factory):
    """Direct regression for the deadlock fix: many concurrent finish() +
    edit_session() calls across sessions that all share ONE production
    order must never deadlock. Before the fix, edit_session() locked the
    session row before any PO lock while finish() always locked PO-first --
    a classic AB/BA cycle triggered reliably by enough concurrent pairs."""
    g = seeded_factory
    n = 12
    session_ids = []
    with db.cursor() as cur:
        for i in range(n):
            cur.execute(
                """INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,start_request_id)
                   VALUES(%s,%s,%s,'docker-e2e','OPEN',CURRENT_TIMESTAMP,%s) RETURNING id""",
                (g['employee_id'] if i == 0 else _extra_employee(db, g, i), g['operation_id'], g['station_id'],
                 f'p1-lockorder-{g["suffix"]}-{i}'))
            session_ids.append(cur.fetchone()['id'])

    errors = []

    def do_finish(sid):
        try:
            _sessions.finish(sid, {'request_id': f'p1-lockorder-finish-{sid}-{uuid.uuid4()}', 'good_qty': 1, 'defect_qty': 0})
        except Exception as exc:  # noqa: BLE001 -- capturing for the assertion below, not swallowing silently
            errors.append(('finish', sid, exc))

    def do_edit(sid):
        try:
            _supervisor.edit_session(sid, {'good_qty': 2, 'defect_qty': 0, 'reason': 'p1 lock-order regression test'}, user_id=1)
        except Exception as exc:  # noqa: BLE001
            errors.append(('edit', sid, exc))

    try:
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = []
            for sid in session_ids:
                futures.append(pool.submit(do_finish, sid))
                futures.append(pool.submit(do_edit, sid))
            for f in futures:
                f.result(timeout=30)

        deadlocks = [e for e in errors if 'deadlock' in str(e[2]).lower()]
        assert not deadlocks, f'deadlock detected under concurrent finish()+edit_session() on a shared PO: {deadlocks}'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM production_trace_events WHERE session_id=ANY(%s)', (session_ids,))
            cur.execute('DELETE FROM quantity_movements WHERE session_id=ANY(%s)', (session_ids,))
            cur.execute('DELETE FROM operation_adjustments WHERE session_id=ANY(%s)', (session_ids,))
            cur.execute('DELETE FROM work_sessions WHERE id=ANY(%s)', (session_ids,))


_extra_employee_cache: dict[str, list[int]] = {}


def _extra_employee(db, g, i):
    """One employee per concurrent session in the lock-order test (each
    session needs its own OPEN slot -- uq_open_session_per_employee would
    otherwise block the very concurrency this test needs to create)."""
    key = g['suffix']
    ids = _extra_employee_cache.setdefault(key, [])
    with db.cursor() as cur:
        cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                    (f'P1LOCK-{key}-{i}', f'P1 Lock Test {i}', f'WF|EMP|P1LOCK-{key}-{i}'))
        emp_id = cur.fetchone()['id']
    ids.append(emp_id)
    return emp_id


@pytest.fixture(autouse=True)
def _cleanup_extra_employees(db):
    yield
    for ids in _extra_employee_cache.values():
        if ids:
            with db.cursor() as cur:
                cur.execute('DELETE FROM work_sessions WHERE employee_id=ANY(%s)', (ids,))
                cur.execute('DELETE FROM employees WHERE id=ANY(%s)', (ids,))
    _extra_employee_cache.clear()


# --- 3. Excluded session stops generating exception noise ------------------

def test_excluded_long_open_session_is_not_detected(db, seeded_factory):
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,start_request_id,excluded_from_reports,exclusion_reason)
               VALUES(%s,%s,%s,'OPEN',CURRENT_TIMESTAMP-INTERVAL '13 hours',%s,TRUE,'QA test data') RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], f'p1-excl-{g["suffix"]}'))
        sid = cur.fetchone()['id']
    try:
        conditions = ExceptionRepository().detected_conditions()
        assert not any(c['session_id'] == sid for c in conditions), \
            'an excluded session must not generate new Session Exception noise'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM work_sessions WHERE id=%s', (sid,))


def test_non_excluded_long_open_session_still_detected_control(db, seeded_factory):
    """Control for the test above -- confirms the fix filters specifically
    on excluded_from_reports, not accidentally hiding LONG_OPEN_SESSION
    detection altogether."""
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,start_request_id)
               VALUES(%s,%s,%s,'OPEN',CURRENT_TIMESTAMP-INTERVAL '13 hours',%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], f'p1-noexcl-{g["suffix"]}'))
        sid = cur.fetchone()['id']
    try:
        conditions = ExceptionRepository().detected_conditions()
        match = [c for c in conditions if c['session_id'] == sid]
        assert match and match[0]['exception_type'] == 'LONG_OPEN_SESSION'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM work_sessions WHERE id=%s', (sid,))
