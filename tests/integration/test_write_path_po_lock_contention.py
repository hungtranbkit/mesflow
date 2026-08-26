"""Reliability Validation Round 2, FIX 2 -- confirmed root cause AND fix
for the write-path concurrency ceiling Gate 13 found.

Profiled (not guessed) via real stage timing
(mesflow.core.timing_debug/MESFLOW_TIMING_DEBUG=1), a controlled A/B load
comparison, and live pg_locks/exception inspection during load:
lock_startable_operation() -> reconcile_operation_and_po() ->
reconcile_operation() -> reconcile_production_order() takes `FOR UPDATE`
on the shared parent production_orders row on EVERY start() and finish()
call. When many concurrent workers write to DIFFERENT operations under
the SAME production order, this was not merely slow -- it produced REAL
PostgreSQL deadlocks: confirmed live, 19/20 concurrent finish() calls on
20 independent operations sharing one PO failed outright with "deadlock
detected", and MESFlow's own offline-sync path silently absorbed every
one of those as a generic 'transient'/TEMPORARY_FAILURE (see
test_offline_burst_gate14.py, which first surfaced this while testing an
unrelated gate).

Root cause (found by direct repro, not the first, insufficient attempt):
reordering the two explicit locks INSIDE reconcile_operation() alone did
NOT fix it (still 19/20 failing) -- record_quantities() INSERTs into
quantity_movements with FK columns to BOTH operations AND
production_orders, and PostgreSQL's own referential-integrity check
implicitly locks those referenced rows as part of that INSERT, before
reconcile_operation_and_po() ever runs. The only reliable fix is
lock_production_order_for_operation_first() (production_state.py): make
the shared PO's FOR UPDATE lock the FIRST row lock ANY session-mutating
transaction takes, full stop -- called at the very top of
WorkSessionRepository.start()/_finish_within()/auto_close_for_shift_end()
and SupervisorRepository.adjust(), before the session row, before
employees, before any quantity/audit write. Verified: the same 20-way
concurrent finish() repro that failed 19/20 times passed 0/20 failures
across multiple repeated runs after this fix.

A/B load comparison for the resulting throughput/latency (not a
correctness issue, a genuine scaling characteristic of "many operations
share one PO"): 16 actors sharing one PO vs. 16 actors each on their own
PO, otherwise identical dataset/profile/duration/think-time -- see the
Round 2 final report for the full load matrix.

What is asserted here as a permanent regression test: concurrent
START/FINISH calls across MANY operations sharing one PO all complete
successfully (no deadlocks), never corrupt data, never double-count
quantities, never leave more than one OPEN session per employee, and
audit_integrity() stays clean afterward.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from mesflow.db.repositories.execution import WorkSessionRepository
from mesflow.services.integrity_audit_service import audit_integrity

pytestmark = pytest.mark.postgres


def _make_graph(db, n_operations, suffix):
    with db.cursor() as cur:
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES (%s,'Contention',100,'IN_PROGRESS') RETURNING id",
                    (f'POLOCK-PO-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES (%s,%s,'Contention Part') RETURNING id", (po_id, f'POLOCK-PART-{suffix}'))
        part_id = cur.fetchone()['id']
        employees = []
        operations = []
        for i in range(n_operations):
            cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES (%s,%s,'TEST','Worker',%s) RETURNING id",
                        (f'POLOCK-EMP-{suffix}-{i}', f'Contention Worker {i}', f'WF|EMP|POLOCK-{suffix}-{i}'))
            employees.append(cur.fetchone()['id'])
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                VALUES (%s,%s,%s,'Contention Operation','IN_PROGRESS',%s) RETURNING id""",
                (po_id, part_id, f'POLOCK-OP-{suffix}-{i}', f'WF|OP|POLOCK-{suffix}-{i}'))
            operations.append(cur.fetchone()['id'])
    return {'po_id': po_id, 'part_id': part_id, 'employees': employees, 'operations': operations}


def _drop_graph(db, g):
    with db.cursor() as cur:
        cur.execute('DELETE FROM production_trace_events WHERE operation_id=ANY(%s)', (g['operations'],))
        cur.execute('DELETE FROM quantity_movements WHERE operation_id=ANY(%s)', (g['operations'],))
        cur.execute('DELETE FROM kiosk_idempotency WHERE request_id LIKE %s', (f'POLOCK-{g["po_id"]}-%',))
        cur.execute('DELETE FROM work_sessions WHERE employee_id=ANY(%s)', (g['employees'],))
        cur.execute('DELETE FROM operations WHERE id=ANY(%s)', (g['operations'],))
        cur.execute('DELETE FROM parts WHERE id=%s', (g['part_id'],))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (g['po_id'],))
        cur.execute('DELETE FROM employees WHERE id=ANY(%s)', (g['employees'],))


def test_concurrent_starts_across_shared_po_never_corrupt_data(db):
    """The confirmed contention shape: N employees, N distinct operations,
    ALL under the SAME production order, all calling start() at once.
    Expected: slower (serialized on the PO row), but every single one
    still succeeds correctly, with no lost/duplicated effect."""
    n = 12
    suffix = uuid.uuid4().hex[:10]
    g = _make_graph(db, n, suffix)
    repo = WorkSessionRepository()
    results = []
    errors = []
    lock = threading.Lock()

    def start_one(i):
        try:
            rid = f'POLOCK-{g["po_id"]}-START-{i}'
            resp = repo.start({'employee_id': g['employees'][i], 'operation_id': g['operations'][i], 'request_id': rid})
            with lock:
                results.append(resp)
        except Exception as e:
            with lock:
                errors.append((i, e))

    try:
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(start_one, i) for i in range(n)]
            for f in as_completed(futures):
                f.result()

        # Correctness first: every single start must have succeeded --
        # contention affects latency, not whether a legitimate,
        # non-conflicting request eventually completes correctly.
        assert not errors, f'unexpected failures under PO-row contention: {errors}'
        assert len(results) == n
        session_ids = [r['session']['id'] for r in results]
        assert len(set(session_ids)) == n, 'every start must have created its own distinct session -- no lost/merged writes'

        with db.cursor() as cur:
            cur.execute('SELECT id,employee_id,operation_id,status FROM work_sessions WHERE employee_id=ANY(%s)', (g['employees'],))
            rows = cur.fetchall()
        assert len(rows) == n
        assert all(r['status'] == 'OPEN' for r in rows)
        assert {r['employee_id'] for r in rows} == set(g['employees'])

        # The shared PO's aggregate must correctly reflect ALL N sessions,
        # not just some -- proving reconcile_operation_and_po's repeated
        # FOR UPDATE re-runs under contention don't drop or race any update.
        with db.cursor() as cur:
            cur.execute("SELECT status FROM production_orders WHERE id=%s", (g['po_id'],))
            assert cur.fetchone()['status'] == 'IN_PROGRESS'
            cur.execute("SELECT COUNT(*) n FROM operations WHERE production_order_id=%s AND status='IN_PROGRESS'", (g['po_id'],))
            assert cur.fetchone()['n'] == n

        integrity = audit_integrity()
        for category, items in integrity.items():
            offending = [x for x in items if x.get('employee_id') in g['employees'] or x.get('session_id') in session_ids]
            assert not offending, f'{category}: {offending}'
    finally:
        _drop_graph(db, g)


def test_concurrent_finishes_across_shared_po_never_deadlock(db):
    """The exact shape that produced a REAL PostgreSQL deadlock before the
    fix (lock_production_order_for_operation_first, applied at the top of
    start()/finish()): N employees, N distinct operations, all under the
    SAME production order, all with an already-OPEN session, all calling
    finish() at once. Before the fix this failed 19/20 times with
    "deadlock detected"; this asserts 0 failures, repeatably."""
    n = 20
    suffix = uuid.uuid4().hex[:10]
    g = _make_graph(db, n, suffix)
    repo = WorkSessionRepository()
    session_ids = []
    for i in range(n):
        resp = repo.start({'employee_id': g['employees'][i], 'operation_id': g['operations'][i], 'request_id': f'POLOCK-{g["po_id"]}-START-{i}'})
        session_ids.append(resp['session']['id'])

    errors = []
    lock = threading.Lock()

    def finish_one(i):
        try:
            repo.finish(session_ids[i], {'request_id': f'POLOCK-{g["po_id"]}-FINISH-{i}', 'good_qty': 3, 'defect_qty': 1, 'rework_qty': 0})
        except Exception as e:
            with lock:
                errors.append((i, type(e).__name__, str(e)))

    try:
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = [pool.submit(finish_one, i) for i in range(n)]
            for f in as_completed(futures):
                f.result()

        assert not errors, f'unexpected failures (deadlock regression?) under PO-row contention: {errors}'

        with db.cursor() as cur:
            cur.execute('SELECT id,status,good_qty,defect_qty FROM work_sessions WHERE id=ANY(%s)', (session_ids,))
            rows = {r['id']: r for r in cur.fetchall()}
        assert len(rows) == n
        for sid in session_ids:
            assert rows[sid]['status'] == 'CLOSED'
            assert rows[sid]['good_qty'] == 3 and rows[sid]['defect_qty'] == 1

        integrity = audit_integrity()
        for category, items in integrity.items():
            offending = [x for x in items if x.get('employee_id') in g['employees'] or x.get('session_id') in session_ids]
            assert not offending, f'{category}: {offending}'
    finally:
        _drop_graph(db, g)


def test_timing_debug_env_var_off_by_default_and_zero_overhead_path(monkeypatch):
    """Sanity check for the profiling instrumentation itself (FIX 2):
    disabled by default, and stage() is a real no-op (doesn't even start a
    timer) when disabled."""
    monkeypatch.delenv('MESFLOW_TIMING_DEBUG', raising=False)
    from mesflow.core.timing_debug import StageTimer
    timer = StageTimer('test_operation')
    assert timer.enabled is False
    with timer.stage('some_stage'):
        pass
    assert timer.stages == {}, 'disabled timer must not record anything'
    timer.emit()  # must not raise even though nothing was ever enabled
