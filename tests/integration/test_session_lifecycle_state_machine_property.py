"""Reliability Validation Round 2, Gate 4 -- property-based testing of the
session lifecycle (NOT_STARTED -> OPEN -> MANUAL_CLOSED / NOT_STARTED ->
OPEN -> AUTO_CLOSED) against the REAL WorkSessionRepository and real
PostgreSQL, via Hypothesis. Generates random sequences of
START/duplicate-START/FINISH/duplicate-FINISH/AUTO_CLOSE and checks:

  - duplicate START (same request_id) never creates a second session row
    and always replays the original response (idempotent_replay=True)
  - duplicate FINISH (same request_id) never records a second close event
    and always replays the original response
  - a CLOSED session never reopens, and a second, genuinely-new FINISH
    attempt against an already-closed session is rejected, not silently
    accepted
  - AUTO_CLOSE never changes quantity and is a no-op (returns None) once
    the session is no longer OPEN
  - every rejected/duplicate call still leaves the database in exactly the
    state audit_integrity() considers valid

Kept to a modest max_examples/sequence length on purpose: each Hypothesis
example does several real transactional round-trips against Postgres
(unlike the pure boundary-math property test in
tests/test_shift_boundary_property.py), so this is deliberately the
slower, smaller-scale half of Gate 4 rather than the "hundreds/thousands
of examples" pure-function half.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from mesflow.db.repositories.base import ConflictError
from mesflow.db.repositories.execution import WorkSessionRepository
from mesflow.services.integrity_audit_service import audit_integrity

pytestmark = pytest.mark.postgres

ACTIONS = ['START', 'START_DUP', 'FINISH', 'FINISH_DUP', 'AUTO_CLOSE', 'FINISH_AFTER_CLOSE']


def _make_graph(db):
    suffix = uuid.uuid4().hex[:12]
    with db.cursor() as cur:
        cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                    (f'PROP-{suffix}', 'Property Test Worker', f'WF|EMP|PROP-{suffix}'))
        employee_id = cur.fetchone()['id']
        cur.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES(%s,'Property Test Station','TEST','TEST') RETURNING id",
                    (f'PROP-ST-{suffix}',))
        station_id = cur.fetchone()['id']
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'PROP PRODUCT',1000,'IN_PROGRESS') RETURNING id",
                    (f'PROP-PO-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Property Test Part') RETURNING id",
                    (po_id, f'PROP-PART-{suffix}'))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                       VALUES(%s,%s,%s,'Property Test Operation','IN_PROGRESS',%s) RETURNING id""",
                    (po_id, part_id, f'PROP-OP-{suffix}', f'WF|OP|PROP-OP-{suffix}'))
        operation_id = cur.fetchone()['id']
    return dict(employee_id=employee_id, station_id=station_id, po_id=po_id, part_id=part_id, operation_id=operation_id)


def _drop_graph(db, g):
    with db.cursor() as cur:
        cur.execute("DELETE FROM quantity_movements WHERE operation_id=%s", (g['operation_id'],))
        cur.execute("DELETE FROM production_trace_events WHERE operation_id=%s", (g['operation_id'],))
        cur.execute("DELETE FROM kiosk_idempotency WHERE request_id IN (SELECT start_request_id FROM work_sessions WHERE employee_id=%s) OR request_id IN (SELECT finish_request_id FROM work_sessions WHERE employee_id=%s)", (g['employee_id'], g['employee_id']))
        cur.execute("DELETE FROM work_sessions WHERE employee_id=%s", (g['employee_id'],))
        cur.execute("DELETE FROM operations WHERE id=%s", (g['operation_id'],))
        cur.execute("DELETE FROM parts WHERE id=%s", (g['part_id'],))
        cur.execute("DELETE FROM production_orders WHERE id=%s", (g['po_id'],))
        cur.execute("DELETE FROM stations WHERE id=%s", (g['station_id'],))
        cur.execute("DELETE FROM employees WHERE id=%s", (g['employee_id'],))


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(actions=st.lists(st.sampled_from(ACTIONS), min_size=1, max_size=6))
def test_session_lifecycle_random_sequences_never_corrupt(db, actions):
    g = _make_graph(db)
    repo = WorkSessionRepository()
    session_id = None
    start_request_id = None
    finish_request_id = None
    is_open = False
    seen_session_ids = set()
    try:
        for action in actions:
            if action == 'START':
                rid = f'PROP-START-{uuid.uuid4().hex[:10]}'
                try:
                    resp = repo.start({'employee_id': g['employee_id'], 'operation_id': g['operation_id'], 'request_id': rid})
                except ConflictError:
                    # Either the employee already has an OPEN session
                    # (uq_open_session_per_employee), or a previous AUTO_CLOSE
                    # in this same sequence used a shift_end in the future,
                    # so "now" (this START's started_at) falls inside that
                    # already-CLOSED session's [started_at,ended_at) range --
                    # both are correct rejections, not corruption.
                    continue
                assert resp['idempotent_replay'] is False
                session_id = resp['session']['id']
                seen_session_ids.add(session_id)
                start_request_id = rid
                finish_request_id = None
                is_open = True

            elif action == 'START_DUP':
                if start_request_id is None:
                    continue
                resp = repo.start({'employee_id': g['employee_id'], 'operation_id': g['operation_id'], 'request_id': start_request_id})
                # Property: duplicate START (same request_id) never creates
                # a second effect -- always a replay of the original session.
                assert resp['idempotent_replay'] is True
                assert resp['session']['id'] == session_id

            elif action == 'FINISH':
                if not is_open:
                    continue
                rid = f'PROP-FINISH-{uuid.uuid4().hex[:10]}'
                resp = repo.finish(session_id, {'request_id': rid, 'good_qty': 1, 'defect_qty': 0, 'rework_qty': 0})
                assert resp['idempotent_replay'] is False
                assert resp['session']['status'] == 'CLOSED'
                assert resp['session']['ended_at'] >= resp['session']['started_at']
                finish_request_id = rid
                is_open = False

            elif action == 'FINISH_DUP':
                if finish_request_id is None:
                    continue
                resp = repo.finish(session_id, {'request_id': finish_request_id, 'good_qty': 1, 'defect_qty': 0, 'rework_qty': 0})
                # Property: duplicate FINISH (same request_id) never records
                # a second close event -- always a replay.
                assert resp['idempotent_replay'] is True

            elif action == 'FINISH_AFTER_CLOSE':
                # A genuinely NEW finish request_id against an
                # already-CLOSED session must be rejected outright, never
                # silently accepted (which would be a closed-session-reopens
                # bug in disguise).
                if is_open or session_id is None:
                    continue
                rid = f'PROP-FINISH-REOPEN-{uuid.uuid4().hex[:10]}'
                with pytest.raises(ConflictError):
                    repo.finish(session_id, {'request_id': rid, 'good_qty': 1, 'defect_qty': 0, 'rework_qty': 0})

            elif action == 'AUTO_CLOSE':
                if session_id is None:
                    continue
                shift_end = datetime.now(timezone.utc) + timedelta(hours=1)
                with db.cursor() as cur:
                    cur.execute('SELECT good_qty,defect_qty,rework_qty FROM work_sessions WHERE id=%s', (session_id,))
                    before = cur.fetchone()
                resp = repo.auto_close_for_shift_end(session_id, shift_end, correlation_id='PROP-AUTO')
                if not is_open:
                    # No-op on an already-non-OPEN session -- never an error,
                    # never a state change.
                    assert resp is None
                    continue
                assert resp is not None
                # Property: AUTO_SHIFT_END never fakes/changes quantity.
                assert resp['session']['good_qty'] == before['good_qty']
                assert resp['session']['defect_qty'] == before['defect_qty']
                assert resp['session']['rework_qty'] == before['rework_qty']
                assert resp['session']['status'] == 'CLOSED'
                assert resp['session']['close_reason'] == 'AUTO_SHIFT_END'
                is_open = False

        # Whole-sequence invariants, independent of which actions actually fired.
        with db.cursor() as cur:
            cur.execute('SELECT id,status,ended_at,good_qty,defect_qty,rework_qty FROM work_sessions WHERE employee_id=%s ORDER BY id', (g['employee_id'],))
            rows = cur.fetchall()
        for row in rows:
            assert (row['status'] == 'CLOSED') == (row['ended_at'] is not None), row
            assert row['good_qty'] >= 0 and row['defect_qty'] >= 0 and row['rework_qty'] >= 0, row
        open_count = sum(1 for r in rows if r['status'] == 'OPEN')
        assert open_count <= 1, f'more than one OPEN session survived the sequence: {rows}'
        assert open_count == (1 if is_open else 0)

        integrity = audit_integrity()
        for category, items in integrity.items():
            offending = [x for x in items if x.get('employee_id') == g['employee_id'] or x.get('session_id') in seen_session_ids]
            assert not offending, f'{category}: {offending} after actions={actions}'
    finally:
        _drop_graph(db, g)
