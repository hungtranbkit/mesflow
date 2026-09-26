"""Production Overview hotfix (2026-09-26): /api/dashboard/overview names who
is running each Operation right now, straight from OPEN work_sessions.

Real PostgreSQL + real API: zero workers, one worker, several workers on one
Operation, a SETUP session shown on its parent Operation, correct per-
Operation mapping, and the list following the session lifecycle (a finished
session disappears on the next fetch -- no stale cache)."""
import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _start(api, employee_id, operation_id, station_id=None):
    response = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'OV-AW-START-{uuid.uuid4()}', 'employee_id': employee_id,
        'operation_id': operation_id, 'station_id': station_id, 'device_uuid': 'TEST-OV-AW',
    }, timeout=15)
    assert response.status_code == 201, response.text
    return response.json()['session']['id']


def _finish(api, session_id):
    response = api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'OV-AW-FINISH-{uuid.uuid4()}', 'good_qty': 1, 'defect_qty': 0,
        'rework_qty': 0}, timeout=15)
    assert response.status_code == 200, response.text


def _workers(api, operation_id):
    response = api.get(f'{BASE_URL}/api/dashboard/overview?limit=5000', timeout=30)
    assert response.status_code == 200, response.text
    rows = [x for x in response.json()['operations'] if x['operation_id'] == operation_id]
    assert len(rows) == 1, f'operation {operation_id} missing from overview'
    assert rows[0]['active_worker_count'] == len(rows[0]['active_worker_list'])
    return rows[0]['active_worker_list']


@pytest.fixture
def extra(db, seeded_factory):
    """Two more employees and a second production Operation on the same Part."""
    graph = seeded_factory
    s = graph['suffix']
    with db.cursor() as cur:
        employees = []
        for i in (2, 3):
            cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) "
                        "VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                        (f'TEST{i}-{s}', f'Worker {i} {s}', f'WF|EMP|TEST{i}-{s}'))
            employees.append(cur.fetchone()['id'])
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                       VALUES(%s,%s,%s,'Second Operation','IN_PROGRESS',%s) RETURNING id""",
                    (graph['po_id'], graph['part_id'], f'TEST-OP2-{s}', f'WF|OP|TEST-OP2-{s}'))
        op2 = cur.fetchone()['id']
    yield dict(graph, employee2_id=employees[0], employee3_id=employees[1], operation2_id=op2)
    with db.cursor() as cur:
        for emp in employees:
            cur.execute("DELETE FROM kiosk_idempotency WHERE request_id IN (SELECT start_request_id FROM work_sessions WHERE employee_id=%s) "
                        "OR request_id IN (SELECT finish_request_id FROM work_sessions WHERE employee_id=%s)", (emp, emp))
            cur.execute("DELETE FROM operation_adjustments WHERE session_id IN (SELECT id FROM work_sessions WHERE employee_id=%s)", (emp,))
            cur.execute("DELETE FROM work_sessions WHERE employee_id=%s", (emp,))
        # SETUP row cascades from its parent (0047 parent_operation_id ON DELETE CASCADE).
        cur.execute("DELETE FROM work_sessions WHERE operation_id IN (SELECT id FROM operations WHERE parent_operation_id=%s)", (op2,))
        cur.execute("DELETE FROM operations WHERE id=%s", (op2,))
        for emp in employees:
            cur.execute("DELETE FROM employees WHERE id=%s", (emp,))


def test_overview_lists_current_workers_per_operation(api, extra):
    g = extra
    op1, op2 = g['operation_id'], g['operation2_id']

    # Zero: nobody has an OPEN session yet.
    assert _workers(api, op1) == []
    assert _workers(api, op2) == []

    # One worker, mapped to that Operation only.
    s1 = _start(api, g['employee_id'], op1, g['station_id'])
    (w,) = _workers(api, op1)
    assert w['employee_id'] == g['employee_id']
    assert w['name'] == 'Docker Test Worker' and w['employee_no'] == f"TEST-{g['suffix']}"
    assert w['session_count'] == 1 and w['session_ids'] == [s1] and w['setup'] is False
    assert w['station_codes'] == [f"TEST-ST-{g['suffix']}"]
    assert _workers(api, op2) == []

    # Several workers on the same Operation.
    s2 = _start(api, g['employee2_id'], op1)
    assert {x['employee_id'] for x in _workers(api, op1)} == {g['employee_id'], g['employee2_id']}

    # A SETUP session is reported on the production Operation it prepares.
    configured = api.put(f'{BASE_URL}/api/operations/{op2}/setup', json={
        'requires_setup': True, 'expected_setup_minutes': 10, 'setup_note': 'x'}, timeout=15)
    assert configured.status_code == 200, configured.text
    setup_id = api.get(f'{BASE_URL}/api/operations/{op2}/setup', timeout=15).json()['setup']['id']
    _start(api, g['employee3_id'], setup_id)
    (w3,) = _workers(api, op2)
    assert w3['employee_id'] == g['employee3_id'] and w3['setup'] is True
    assert {x['employee_id'] for x in _workers(api, op1)} == {g['employee_id'], g['employee2_id']}

    # Finishing a session removes the worker on the next fetch.
    _finish(api, s1)
    assert [x['employee_id'] for x in _workers(api, op1)] == [g['employee2_id']]
    _finish(api, s2)
    assert _workers(api, op1) == []
