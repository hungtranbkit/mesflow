import uuid

import pytest

from conftest import BASE_URL


pytestmark = pytest.mark.postgres


def _start(api, graph):
    return api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'REWORK-START-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'operation_id': graph['operation_id'], 'station_id': graph['station_id'],
        'device_uuid': 'TEST-REWORK',
    }, timeout=10)


def _finish(api, session_id, good, defect, repairable=None):
    # rework_qty = how many of the NG the operator declares REPAIRABLE (0051).
    # Default: all of them, which is what every test below wants queued.
    return api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'REWORK-FINISH-{uuid.uuid4()}', 'good_qty': good,
        'defect_qty': defect, 'rework_qty': defect if repairable is None else repairable,
    }, timeout=10)


def test_rework_queue_buckets_credit_original_operation_and_completion(api, db, seeded_factory):
    """Target 100: unresolved NG is pending, never implicit scrap.

    92 good + 8 NG -> repair 6 -> good 98/pending 2 -> scrap 2 -> good 98/
    scrap 2, still incomplete -> produce 2 additional good -> complete.
    """
    graph = seeded_factory
    source = _start(api, graph)
    assert source.status_code == 201, source.text
    source_id = source.json()['session']['id']
    assert _finish(api, source_id, 92, 8).status_code == 200

    queued = api.get(f'{BASE_URL}/api/rework/queue', timeout=10)
    assert queued.status_code == 200, queued.text
    item = next(x for x in queued.json()['items'] if x['source_session_id'] == source_id)
    assert (item['pending_qty'], item['scrap_qty']) == (8, 0)
    assert db.execute('SELECT status FROM operations WHERE id=%s', (graph['operation_id'],)).fetchone()['status'] != 'COMPLETED'

    repair = api.post(f'{BASE_URL}/api/rework/queue/{source_id}/resolve', json={
        'request_id': f'REWORK-RESOLVE-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'repaired_qty': 6,
    }, timeout=10)
    assert repair.status_code == 200, repair.text
    op = db.execute('SELECT done_qty,defect_qty,rework_qty,repaired_qty,scrap_qty,status FROM operations WHERE id=%s', (graph['operation_id'],)).fetchone()
    # rework_qty stays 8: the declaration is history, the repair is repaired_qty.
    assert tuple(op.values()) == (98, 8, 8, 6, 0, 'IN_PROGRESS')

    scrap = api.post(f'{BASE_URL}/api/rework/queue/{source_id}/resolve', json={
        'request_id': f'REWORK-SCRAP-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'scrapped_qty': 2,
    }, timeout=10)
    assert scrap.status_code == 200, scrap.text
    op = db.execute('SELECT done_qty,defect_qty,rework_qty,repaired_qty,scrap_qty,status FROM operations WHERE id=%s', (graph['operation_id'],)).fetchone()
    assert tuple(op.values()) == (98, 8, 8, 6, 2, 'IN_PROGRESS')
    assert db.execute('SELECT COUNT(*) n FROM rework_ledger WHERE source_session_id=%s', (source_id,)).fetchone()['n'] == 2
    assert db.execute('SELECT rework_qty-repaired_qty-scrap_qty pending_qty FROM work_sessions WHERE id=%s', (source_id,)).fetchone()['pending_qty'] == 0

    # Only two real additional GOOD pieces complete the source OP.  Pending
    # or repaired+scrapped quantities must never be used as a completion hack.
    second = _start(api, graph)
    assert second.status_code == 201, second.text
    assert _finish(api, second.json()['session']['id'], 2, 0).status_code == 200
    op = db.execute('SELECT done_qty,defect_qty,rework_qty,repaired_qty,scrap_qty,status FROM operations WHERE id=%s', (graph['operation_id'],)).fetchone()
    assert tuple(op.values()) == (100, 8, 8, 6, 2, 'COMPLETED')
