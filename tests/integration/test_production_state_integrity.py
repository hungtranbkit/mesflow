import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from conftest import BASE_URL


pytestmark = pytest.mark.postgres


def row(db, sql, params=()):
    with db.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def start(api, graph, token=None):
    return api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': token or f'TEST-START-{uuid.uuid4()}',
        'employee_id': graph['employee_id'],
        'operation_id': graph['operation_id'],
        'station_id': graph['station_id'],
        'device_uuid': 'TEST-P0',
    }, timeout=10)


def finish(api, session_id, good, defect=0, rework=0, token=None):
    return api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': token or f'TEST-FINISH-{uuid.uuid4()}',
        'good_qty': good, 'defect_qty': defect, 'rework_qty': rework,
    }, timeout=10)


def test_completed_and_cancelled_operation_reject_every_start(api, db, seeded_factory):
    graph = seeded_factory
    with db.cursor() as cur:
        cur.execute("UPDATE operations SET status='COMPLETED' WHERE id=%s", (graph['operation_id'],))
    completed = start(api, graph)
    assert completed.status_code == 409, completed.text
    assert 'COMPLETED' in completed.json()['message']
    web_kiosk = requests.post(f'{BASE_URL}/api/kiosk-web/start', json={
        'request_id': f'WEB-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'operation_id': graph['operation_id'], 'device_uuid': 'WEB-P0-TEST',
    }, timeout=10)
    assert web_kiosk.status_code == 409, web_kiosk.text
    legacy = requests.post(f'{BASE_URL}/api/session/group/start', json={
        'device_uuid': 'LEGACY-P0-TEST', 'worker_qr': f'WF|EMP|TEST-{graph["suffix"]}',
        'operation_qrs': [f'WF|OP|TEST-OP-{graph["suffix"]}'], 'batch_token': f'LEGACY-{uuid.uuid4()}',
    }, timeout=10)
    assert legacy.status_code == 409, legacy.text

    with db.cursor() as cur:
        cur.execute("UPDATE operations SET status='CANCELLED' WHERE id=%s", (graph['operation_id'],))
        cur.execute("UPDATE production_orders SET status='IN_PROGRESS' WHERE id=%s", (graph['po_id'],))
    cancelled = start(api, graph)
    assert cancelled.status_code == 409, cancelled.text
    assert 'CANCELLED' in cancelled.json()['message']


def test_concurrent_start_retry_creates_one_session(api, db, seeded_factory):
    graph = seeded_factory
    token = f'TEST-CONCURRENT-{uuid.uuid4()}'
    payload = {'request_id': token, 'employee_id': graph['employee_id'],
               'operation_id': graph['operation_id'], 'station_id': graph['station_id'],
               'device_uuid': 'TEST-P0'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: requests.post(f'{BASE_URL}/api/work-sessions/start',json=payload,cookies=api.cookies.get_dict(),timeout=15),range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    assert sum(bool(response.json().get('idempotent_replay')) for response in responses) == 1
    assert row(db, 'SELECT COUNT(*) n FROM work_sessions WHERE start_request_id=%s', (token,))['n'] == 1


def test_open_closed_reopen_rework_and_finish_are_deterministic(api, db, seeded_factory):
    graph = seeded_factory
    started = start(api, graph)
    assert started.status_code == 201, started.text
    session_id = started.json()['session']['id']
    open_state = row(db, 'SELECT done_qty,defect_qty,rework_qty,status FROM operations WHERE id=%s', (graph['operation_id'],))
    assert (open_state['done_qty'], open_state['defect_qty'], open_state['rework_qty'], open_state['status']) == (0, 0, 0, 'IN_PROGRESS')

    finish_token = f'TEST-FINISH-{uuid.uuid4()}'
    closed = finish(api, session_id, 100, 4, 3, finish_token)
    assert closed.status_code == 200, closed.text
    replay = finish(api, session_id, 100, 4, 3, finish_token)
    assert replay.status_code == 200, replay.text
    assert replay.json()['idempotent_replay'] is True
    completed = row(db, 'SELECT done_qty,defect_qty,rework_qty,status FROM operations WHERE id=%s', (graph['operation_id'],))
    assert (completed['done_qty'], completed['defect_qty'], completed['rework_qty'], completed['status']) == (100, 4, 3, 'COMPLETED')
    assert row(db, 'SELECT status FROM production_orders WHERE id=%s', (graph['po_id'],))['status'] == 'COMPLETED'

    reopened = api.patch(f'{BASE_URL}/api/supervisor/sessions/{session_id}', json={
        'status': 'OPEN', 'reason': 'P0 regression: reopen for rework',
    }, timeout=10)
    assert reopened.status_code == 200, reopened.text
    during_rework = row(db, 'SELECT done_qty,defect_qty,rework_qty,status FROM operations WHERE id=%s', (graph['operation_id'],))
    assert (during_rework['done_qty'], during_rework['defect_qty'], during_rework['rework_qty'], during_rework['status']) == (0, 0, 0, 'IN_PROGRESS')
    assert row(db, 'SELECT status FROM production_orders WHERE id=%s', (graph['po_id'],))['status'] == 'IN_PROGRESS'

    reclosed = finish(api, session_id, 105, 5, 4)
    assert reclosed.status_code == 200, reclosed.text
    final = row(db, 'SELECT done_qty,defect_qty,rework_qty,status FROM operations WHERE id=%s', (graph['operation_id'],))
    assert (final['done_qty'], final['defect_qty'], final['rework_qty'], final['status']) == (105, 5, 4, 'COMPLETED')
    assert row(db, 'SELECT COUNT(*) n FROM work_sessions WHERE id=%s', (session_id,))['n'] == 1
    assert row(db, 'SELECT COUNT(*) n FROM operation_adjustments WHERE session_id=%s', (session_id,))['n'] >= 1


def test_reconcile_repairs_open_session_and_mixed_po(api, db, seeded_factory):
    graph = seeded_factory
    with db.cursor() as cur:
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,good_qty,defect_qty,rework_qty,start_request_id)
            VALUES(%s,%s,%s,'OPEN',88,2,1,%s) RETURNING id""",
            (graph['employee_id'], graph['operation_id'], graph['station_id'], f'DIRECT-{uuid.uuid4()}'))
        cur.execute("UPDATE operations SET status='COMPLETED',done_qty=999,defect_qty=99,rework_qty=9 WHERE id=%s", (graph['operation_id'],))
    repaired = api.post(f'{BASE_URL}/api/production-state/reconcile', json={'operation_id': graph['operation_id']}, timeout=10)
    assert repaired.status_code == 200, repaired.text
    op = row(db, 'SELECT done_qty,defect_qty,rework_qty,status FROM operations WHERE id=%s', (graph['operation_id'],))
    assert (op['done_qty'], op['defect_qty'], op['rework_qty'], op['status']) == (0, 0, 0, 'IN_PROGRESS')

    with db.cursor() as cur:
        cur.execute("UPDATE work_sessions SET status='CLOSED',ended_at=CURRENT_TIMESTAMP,good_qty=100 WHERE operation_id=%s", (graph['operation_id'],))
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,%s,'Cancelled test OP','CANCELLED',%s) RETURNING id""",
            (graph['po_id'], graph['part_id'], f'TEST-CANCEL-{graph["suffix"]}', f'WF|OP|CANCEL-{graph["suffix"]}'))
        cancelled_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,%s,'Pending test OP','PLANNED',%s) RETURNING id""",
            (graph['po_id'], graph['part_id'], f'TEST-PENDING-{graph["suffix"]}', f'WF|OP|PENDING-{graph["suffix"]}'))
        pending_id = cur.fetchone()['id']
    mixed = api.post(f'{BASE_URL}/api/production-state/reconcile', json={'po_id': graph['po_id']}, timeout=10)
    assert mixed.status_code == 200, mixed.text
    assert row(db, 'SELECT status FROM operations WHERE id=%s', (graph['operation_id'],))['status'] == 'COMPLETED'
    assert row(db, 'SELECT status FROM production_orders WHERE id=%s', (graph['po_id'],))['status'] == 'IN_PROGRESS'

    with db.cursor() as cur:
        cur.execute("UPDATE operations SET status='CANCELLED' WHERE id=%s", (pending_id,))
    terminal = api.post(f'{BASE_URL}/api/production-state/reconcile', json={'po_id': graph['po_id']}, timeout=10)
    assert terminal.status_code == 200, terminal.text
    # CANCELLED operations are exceptions, not successful completion.  Without
    # an explicit PO cancel workflow the PO must never become normal COMPLETED.
    assert row(db, 'SELECT status FROM production_orders WHERE id=%s', (graph['po_id'],))['status'] == 'IN_PROGRESS'
    with db.cursor() as cur:
        cur.execute('DELETE FROM operations WHERE id IN (%s,%s)', (cancelled_id, pending_id))


def test_force_delete_clean_allowed_but_history_rejected(api, db, seeded_factory):
    graph = seeded_factory
    po_code = row(db, 'SELECT code FROM production_orders WHERE id=%s', (graph['po_id'],))['code']
    clean = api.delete(f'{BASE_URL}/api/production-orders/{graph["po_id"]}/force', json={'confirm_code': po_code}, timeout=10)
    assert clean.status_code == 200, clean.text
    assert row(db, 'SELECT COUNT(*) n FROM production_orders WHERE id=%s', (graph['po_id'],))['n'] == 0


def test_force_delete_with_production_history_is_rejected(api, db, seeded_factory):
    graph = seeded_factory
    assert start(api, graph).status_code == 201
    po_code = row(db, 'SELECT code FROM production_orders WHERE id=%s', (graph['po_id'],))['code']
    blocked = api.delete(f'{BASE_URL}/api/production-orders/{graph["po_id"]}/force', json={'confirm_code': po_code}, timeout=10)
    assert blocked.status_code == 409, blocked.text
    assert 'production history' in blocked.json()['message']
    assert row(db, 'SELECT COUNT(*) n FROM production_orders WHERE id=%s', (graph['po_id'],))['n'] == 1


def test_qa_owned_run_can_delete_its_exact_production_history(api, db, seeded_factory):
    graph=seeded_factory
    run_id=f'20260821-qa-{uuid.uuid4().hex[:8]}'
    po_code=row(db,'SELECT code FROM production_orders WHERE id=%s',(graph['po_id'],))['code']
    with db.cursor() as cur:
        cur.execute('UPDATE production_orders SET notes=%s WHERE id=%s',(f'QA_RUN_ID={run_id}',graph['po_id']))
    db.commit()
    started=start(api,graph)
    assert started.status_code==201,started.text
    session_id=started.json()['session']['id']
    closed=finish(api,session_id,8,1,1)
    assert closed.status_code==200,closed.text
    wrong=api.delete(f'{BASE_URL}/api/production-orders/{graph["po_id"]}/force',json={'confirm_code':po_code,'qa_run_id':run_id+'-wrong'},timeout=10)
    assert wrong.status_code==409,wrong.text
    assert row(db,'SELECT COUNT(*) n FROM production_orders WHERE id=%s',(graph['po_id'],))['n']==1
    assert row(db,'SELECT notes FROM production_orders WHERE id=%s',(graph['po_id'],))['notes']==f'QA_RUN_ID={run_id}'
    cleaned=api.delete(f'{BASE_URL}/api/production-orders/{graph["po_id"]}/force',json={'confirm_code':po_code,'qa_run_id':run_id},timeout=10)
    assert cleaned.status_code==200,cleaned.text
    assert cleaned.json()['qa_run_id']==run_id
    assert cleaned.json()['counts']['deleted_sessions']==1
    assert row(db,'SELECT COUNT(*) n FROM production_orders WHERE id=%s',(graph['po_id'],))['n']==0


def test_normal_delete_po_part_operation_rejects_output_history(api, db, seeded_factory):
    graph = seeded_factory
    with db.cursor() as cur:
        cur.execute('UPDATE operations SET done_qty=1 WHERE id=%s', (graph['operation_id'],))
    operation = api.delete(f'{BASE_URL}/api/operations/{graph["operation_id"]}', timeout=10)
    part = api.delete(f'{BASE_URL}/api/parts/{graph["part_id"]}', timeout=10)
    po = api.delete(f'{BASE_URL}/api/production-orders/{graph["po_id"]}', timeout=10)
    assert operation.status_code == 409, operation.text
    assert part.status_code == 409, part.text
    assert po.status_code == 409, po.text
    with db.cursor() as cur:
        cur.execute('UPDATE operations SET done_qty=0 WHERE id=%s', (graph['operation_id'],))
