"""Repaired pieces must not be supplied twice to downstream operations.

Residual risk #4 from the 2026-09-09 rework audit, stated there as unproven:
a repair credits the SOURCE operation's good output (done_qty += N) AND its
rework_qty (+= N) -- the same N physical pieces -- while
_validate_and_upsert_input_consumption() budgets GOOD and REWORK separately
(its `consumed` subquery filters on source_qty_kind). So a Part with one
successor consuming GOOD and another consuming REWORK could each draw the
same repaired pieces.

This test proves or disproves that with a real graph and real sessions.
"""
import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _start(api, employee_id, operation_id, station_id):
    return api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'FLOW-START-{uuid.uuid4()}', 'employee_id': employee_id,
        'operation_id': operation_id, 'station_id': station_id, 'device_uuid': 'TEST-FLOW',
    }, timeout=10)


def _finish(api, session_id, good, defect=0):
    return api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'FLOW-FINISH-{uuid.uuid4()}', 'good_qty': good,
        'defect_qty': defect, 'rework_qty': 0,
    }, timeout=10)


def test_repaired_pieces_are_supplied_once_across_good_and_rework_inputs(api, db, seeded_factory):
    graph = seeded_factory
    extra_ops, rework_op_id = [], None
    try:
        # Source operation: 92 good + 8 NG, then repair 6 -> done_qty 98,
        # rework_qty 6. The 6 repaired pieces are part of the 98.
        source = _start(api, graph['employee_id'], graph['operation_id'], graph['station_id'])
        assert source.status_code == 201, source.text
        source_session = source.json()['session']['id']
        assert _finish(api, source_session, 92, 8).status_code == 200
        resolved = api.post(f'{BASE_URL}/api/rework/queue/{source_session}/resolve', json={
            'request_id': f'FLOW-RESOLVE-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
            'repaired_qty': 6,
        }, timeout=15)
        assert resolved.status_code == 200, resolved.text
        rework_op_id = db.execute('SELECT id FROM operations WHERE production_order_id=%s AND is_rework_op',
                                  (graph['po_id'],)).fetchone()['id']
        src = db.execute('SELECT done_qty,rework_qty FROM operations WHERE id=%s', (graph['operation_id'],)).fetchone()
        assert (src['done_qty'], src['rework_qty']) == (98, 6)

        # Two successors of the SAME source: one fed by GOOD, one by REWORK.
        with db.cursor() as cur:
            for suffix, kind in (('GOOD', 'GOOD'), ('RWK', 'REWORK')):
                cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,sort_order,qr,
                        input_flow_enabled,input_source_operation_id,input_source_kind)
                    VALUES(%s,%s,%s,%s,'IN_PROGRESS',%s,%s,TRUE,%s,%s) RETURNING id""",
                    (graph['po_id'], graph['part_id'], f"FLOW-{suffix}-{graph['suffix']}", f'TARGET {suffix}',
                     10 if suffix == 'GOOD' else 11, f"WF|OP|FLOW-{suffix}-{graph['suffix']}",
                     graph['operation_id'], kind))
                extra_ops.append(cur.fetchone()['id'])
        good_target, rework_target = extra_ops

        # Consume all 6 repaired pieces through the REWORK-fed successor.
        s = _start(api, graph['employee_id'], rework_target, graph['station_id'])
        assert s.status_code == 201, s.text
        assert _finish(api, s.json()['session']['id'], 6).status_code == 200

        # Now the GOOD-fed successor asks for all 98. Only 92 unrepaired pieces
        # are actually still available -- the other 6 were just consumed above.
        s2 = _start(api, graph['employee_id'], good_target, graph['station_id'])
        assert s2.status_code == 201, s2.text
        response = _finish(api, s2.json()['session']['id'], 98)

        consumed = db.execute("""SELECT COALESCE(SUM(good_qty_consumed+defect_qty_consumed),0) total
            FROM operation_input_consumptions WHERE source_operation_id=%s""",
            (graph['operation_id'],)).fetchone()['total']
        assert consumed <= src['done_qty'], (
            f'{consumed} pieces drawn from an operation that only produced {src["done_qty"]} -- '
            'the repaired pieces were supplied twice (once as GOOD, once as REWORK)')
        assert response.status_code == 409, (
            'asking for all 98 GOOD after 6 of them were consumed as REWORK must be refused, '
            f'got HTTP {response.status_code}: {response.text}')
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM operation_input_consumptions WHERE source_operation_id=%s', (graph['operation_id'],))
            if extra_ops:
                cur.execute('DELETE FROM work_sessions WHERE operation_id=ANY(%s)', (extra_ops,))
                cur.execute('DELETE FROM operations WHERE id=ANY(%s)', (extra_ops,))
            if rework_op_id:
                cur.execute('DELETE FROM rework_ledger WHERE rework_operation_id=%s', (rework_op_id,))
                cur.execute('DELETE FROM work_sessions WHERE operation_id=%s', (rework_op_id,))
                cur.execute('DELETE FROM operations WHERE id=%s', (rework_op_id,))
