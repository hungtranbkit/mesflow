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

Teardown of the auto-created SỬA HÀNG operation is the seeded_factory
fixture's job (tests/integration/conftest.py), not each test's.
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


def _resolve(api, graph, session_id, repaired=0, scrapped=0):
    return api.post(f'{BASE_URL}/api/rework/queue/{session_id}/resolve', json={
        'request_id': f'RWOV-RESOLVE-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'repaired_qty': repaired, 'scrapped_qty': scrapped,
    }, timeout=15)


def _po_row(api, po_id):
    response = api.get(f'{BASE_URL}/api/dashboard/overview', timeout=15)
    assert response.status_code == 200, response.text
    return next(x for x in response.json()['production_orders'] if x['po_id'] == po_id)


def _rework_op_id(db, po_id):
    row = db.execute('SELECT id FROM operations WHERE production_order_id=%s AND is_rework_op', (po_id,)).fetchone()
    assert row is not None, 'resolve() should have created the SỬA HÀNG operation'
    return row['id']


def test_resolving_rework_keeps_po_progress_and_repair_buckets_honest(api, db, seeded_factory):
    graph = seeded_factory
    po_id = graph['po_id']
    source = _start(api, graph)
    assert source.status_code == 201, source.text
    source_id = source.json()['session']['id']
    assert _finish(api, source_id, 92, 8).status_code == 200

    before = _po_row(api, po_id)
    # 8 NG, none triaged yet: all 8 are pending repair, nothing is scrap.
    assert (before['good_quantity'], before['defect_quantity']) == (92, 8)
    assert (before['repair_pending_quantity'], before['scrap_quantity']) == (8, 0)
    assert float(before['progress_percent']) == 92.0

    assert _resolve(api, graph, source_id, repaired=6, scrapped=2).status_code == 200
    rework_op_id = _rework_op_id(db, po_id)

    after = _po_row(api, po_id)
    # The 6 repaired pieces are credited to the SOURCE operation's good output;
    # the PO's progress must move UP, never collapse.
    assert after['good_quantity'] == 98, f"PO good_quantity corrupted: {after['good_quantity']}"
    assert float(after['progress_percent']) == 98.0
    assert after['remaining_quantity'] == 2
    # Buckets stay distinct: 8 NG = 6 repaired + 2 scrapped + 0 pending.
    assert (after['repaired_quantity'], after['scrap_quantity']) == (6, 2)
    assert after['repair_pending_quantity'] == 0
    # SỬA HÀNG is a workbench, not a routing step: it must not inflate the PO's
    # operation counts nor appear in the Operation list.
    assert after['operation_count'] == 1
    assert after['terminal_operation_count'] == 1
    overview = api.get(f'{BASE_URL}/api/dashboard/overview', timeout=15).json()
    assert not [x for x in overview['operations'] if x['operation_id'] == rework_op_id]


def test_rework_session_is_not_a_second_quantity_source(api, db, seeded_factory):
    """A repaired piece exists exactly once in work_sessions -- unfiltered.

    resolve() used to write good_qty=repaired / defect_qty=scrapped onto the
    rework session as well as crediting the source session: two rows carrying
    the same physical pieces. Nothing double-counted only while every report
    remembered to filter is_rework_op, and the one query that forgot
    (po_progress) is exactly the P0 the test above guards. This asserts the
    stronger property instead -- sum the raw rows with NO filter at all and the
    totals still have to be the truth -- so a future query that forgets the
    filter can no longer produce a wrong number.
    """
    graph = seeded_factory
    source = _start(api, graph)
    assert source.status_code == 201, source.text
    source_id = source.json()['session']['id']
    assert _finish(api, source_id, 92, 8).status_code == 200
    assert _resolve(api, graph, source_id, repaired=6, scrapped=2).status_code == 200
    rework_op_id = _rework_op_id(db, graph['po_id'])

    # Deliberately NO is_rework_op filter: this is what a query that forgot it
    # would see, and it must still be the real production total.
    totals = db.execute("""SELECT COALESCE(SUM(ws.good_qty),0) good,COALESCE(SUM(ws.defect_qty),0) defect,
          COALESCE(SUM(ws.rework_qty),0) rework,COALESCE(SUM(ws.scrap_qty),0) scrap
        FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
        WHERE o.production_order_id=%s""", (graph['po_id'],)).fetchone()
    assert (totals['good'], totals['defect'], totals['rework'], totals['scrap']) == (98, 8, 6, 2)

    # The rework session still exists as the record of who did the repair and
    # when -- it just carries no quantities of its own.
    labour = db.execute("""SELECT employee_id,good_qty,defect_qty,rework_qty,scrap_qty,status
        FROM work_sessions WHERE operation_id=%s""", (rework_op_id,)).fetchone()
    assert labour is not None, 'the repair itself must still be recorded'
    assert int(labour['employee_id']) == int(graph['employee_id'])
    assert (labour['good_qty'], labour['defect_qty'], labour['rework_qty'], labour['scrap_qty']) == (0, 0, 0, 0)

    # ...and the quantities are in the ledger, which is where the dated audit of
    # this specific action belongs.
    entry = db.execute('SELECT qty_reworked,qty_scrapped FROM rework_ledger WHERE source_session_id=%s',
                       (source_id,)).fetchone()
    assert (entry['qty_reworked'], entry['qty_scrapped']) == (6, 2)


def test_repair_labour_shows_in_the_day_view_without_touching_operation_progress(api, db, seeded_factory):
    """The repair itself is working time, and must appear as such.

    "Ngày công theo nhân viên" reads daily_sessions(); that query used to
    exclude rework sessions, so an operator who spent the afternoon on the SỬA
    HÀNG bench had a hole in their day. Including them is only safe because the
    rework session now carries zero quantities (see the test above) -- the
    dashboard KPIs sum good_qty/defect_qty straight off this same list. "Tiến
    độ theo Operation" (daily_progress) still excludes the workbench, which has
    no target of its own.
    """
    graph = seeded_factory
    source = _start(api, graph)
    assert source.status_code == 201, source.text
    source_id = source.json()['session']['id']
    assert _finish(api, source_id, 92, 8).status_code == 200
    assert _resolve(api, graph, source_id, repaired=6, scrapped=2).status_code == 200
    rework_op_id = _rework_op_id(db, graph['po_id'])

    today = db.execute("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::date d").fetchone()['d']
    day = api.get(f'{BASE_URL}/api/dashboard/day?date={today}&limit=1000', timeout=15)
    assert day.status_code == 200, day.text
    payload = day.json()

    repair_sessions = [x for x in payload['sessions'] if x['operation_id'] == rework_op_id]
    assert len(repair_sessions) == 1, 'the repair session must show up as working time'
    assert repair_sessions[0]['employee_id'] == graph['employee_id']
    # It contributes time, never quantity.
    assert (repair_sessions[0]['good_qty'], repair_sessions[0]['defect_qty']) == (0, 0)

    # The KPIs are summed off this same list, so they must be unchanged by it.
    assert sum(x['good_qty'] for x in payload['sessions']) == 98
    assert sum(x['defect_qty'] for x in payload['sessions']) == 8
    # ...and the Operation progress panel still ignores the workbench.
    assert not [x for x in payload['items'] if x['operation_id'] == rework_op_id]
