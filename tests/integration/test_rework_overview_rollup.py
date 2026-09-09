"""Resolving a rework item must not corrupt the PO's Overview numbers.

Regression for the P0 found in the 2026-09-09 rework audit: po_progress()'s
ranked_operations/operation_rollup/repair_rollup CTEs selected FROM operations
with no is_rework_op filter, so the auto-created SỬA HÀNG operation
(sort_order=2147483647, no predecessor, done_qty permanently 0 because it is
never reconciled) either stole the Part's terminal slot or joined the terminal
set -- collapsing good_quantity/progress_percent to 0 (or halving them) for the
entire PO the first time anyone resolved a single queue item.

Reproduced before the fix: good_quantity 92 -> 0, progress 92.0% -> 0.0%,
remaining 8 -> 100.
"""
import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _start(api, graph):
    return api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'RWOV-START-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'operation_id': graph['operation_id'], 'station_id': graph['station_id'],
        'device_uuid': 'TEST-RWOV',
    }, timeout=10)


def _finish(api, session_id, good, defect):
    return api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'RWOV-FINISH-{uuid.uuid4()}', 'good_qty': good,
        'defect_qty': defect, 'rework_qty': 0,
    }, timeout=10)


def _po_row(api, po_id):
    response = api.get(f'{BASE_URL}/api/dashboard/overview', timeout=15)
    assert response.status_code == 200, response.text
    return next(x for x in response.json()['production_orders'] if x['po_id'] == po_id)


def test_resolving_rework_keeps_po_progress_and_repair_buckets_honest(api, db, seeded_factory):
    graph = seeded_factory
    po_id = graph['po_id']
    rework_op_id = None
    try:
        source = _start(api, graph)
        assert source.status_code == 201, source.text
        source_id = source.json()['session']['id']
        assert _finish(api, source_id, 92, 8).status_code == 200

        before = _po_row(api, po_id)
        # 8 NG, none triaged yet: all 8 are pending repair, nothing is scrap.
        assert (before['good_quantity'], before['defect_quantity']) == (92, 8)
        assert (before['repair_pending_quantity'], before['scrap_quantity']) == (8, 0)
        assert float(before['progress_percent']) == 92.0

        resolved = api.post(f'{BASE_URL}/api/rework/queue/{source_id}/resolve', json={
            'request_id': f'RWOV-RESOLVE-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
            'repaired_qty': 6, 'scrapped_qty': 2,
        }, timeout=15)
        assert resolved.status_code == 200, resolved.text

        rework_op = db.execute(
            'SELECT id FROM operations WHERE production_order_id=%s AND is_rework_op', (po_id,)).fetchone()
        assert rework_op is not None, 'resolve() should have created the SỬA HÀNG operation'
        rework_op_id = rework_op['id']

        after = _po_row(api, po_id)
        # The 6 repaired pieces are credited to the SOURCE operation's good
        # output; the PO's progress must move UP, never collapse.
        assert after['good_quantity'] == 98, f"PO good_quantity corrupted: {after['good_quantity']}"
        assert float(after['progress_percent']) == 98.0
        assert after['remaining_quantity'] == 2
        # Buckets stay distinct: 8 NG = 6 repaired + 2 scrapped + 0 pending.
        assert (after['repaired_quantity'], after['scrap_quantity']) == (6, 2)
        assert after['repair_pending_quantity'] == 0
        # SỬA HÀNG is a workbench, not a routing step: it must not inflate the
        # PO's operation counts nor appear in the Operation list.
        assert after['operation_count'] == 1
        assert after['terminal_operation_count'] == 1
        overview = api.get(f'{BASE_URL}/api/dashboard/overview', timeout=15).json()
        assert not [x for x in overview['operations'] if x['operation_id'] == rework_op_id]
    finally:
        with db.cursor() as cur:
            if rework_op_id:
                cur.execute('DELETE FROM rework_ledger WHERE rework_operation_id=%s', (rework_op_id,))
                cur.execute('DELETE FROM work_sessions WHERE operation_id=%s', (rework_op_id,))
                cur.execute('DELETE FROM operations WHERE id=%s', (rework_op_id,))
