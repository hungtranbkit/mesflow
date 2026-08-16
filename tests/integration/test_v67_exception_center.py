"""Behavioral V67 lifecycle against PostgreSQL and the real HTTP API."""
import pytest
import requests
import uuid
from concurrent.futures import ThreadPoolExecutor
from werkzeug.security import generate_password_hash
pytestmark=pytest.mark.postgres
BASE='http://mesflow-test-api:8080'

def make_long_open(db,g):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,start_request_id)
          VALUES(%s,%s,%s,'OPEN',CURRENT_TIMESTAMP-INTERVAL '13 hours',%s) RETURNING id""",
          (g['employee_id'],g['operation_id'],g['station_id'],f"TEST-V67-{g['suffix']}"))
        return cur.fetchone()['id']

def find(items,session_id,kind='LONG_OPEN_SESSION'):
    return next(x for x in items if x['session_id']==session_id and x['exception_type']==kind)

def test_long_open_detection_dedup_decision_history_and_stale_conflict(db,api,seeded_factory):
    sid=make_long_open(db,seeded_factory)
    first=api.get(f'{BASE}/api/exceptions?view=action',timeout=10)
    assert first.status_code==200,first.text
    item=find(first.json()['items'],sid)
    second=api.get(f'{BASE}/api/exceptions?view=action',timeout=10)
    assert find(second.json()['items'],sid)['id']==item['id']
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM exception_records WHERE fingerprint=%s",(item['fingerprint'],))
        assert cur.fetchone()['n']==1

    ack_trace=f'v67-ack-{uuid.uuid4()}';resolve_trace=f'v67-resolve-{uuid.uuid4()}'
    acknowledged=api.post(f"{BASE}/api/exceptions/{item['id']}/acknowledge",json={'expected_version':item['row_version']},headers={'X-Trace-ID':ack_trace},timeout=10)
    assert acknowledged.status_code==200,acknowledged.text
    changed=acknowledged.json()['item'];assert changed['status']=='ACKNOWLEDGED'
    resolved=api.post(f"{BASE}/api/exceptions/{item['id']}/resolve",json={'expected_version':changed['row_version'],'reason':'Đã kiểm tra phiếu giấy'},headers={'X-Trace-ID':resolve_trace},timeout=10)
    assert resolved.status_code==200,resolved.text
    stale=api.post(f"{BASE}/api/exceptions/{item['id']}/resolve",json={'expected_version':changed['row_version'],'reason':'retry'},timeout=10)
    assert stale.status_code==409
    history=api.get(f"{BASE}/api/exceptions/{item['id']}/history",timeout=10).json()['items']
    assert [x['action'] for x in history]==['DETECTED','ACKNOWLEDGED','RESOLVED']
    assert history[-1]['actor_username']=='admin' and history[-1]['correlation_id']==resolve_trace
    with db.cursor() as cur:
        cur.execute("SELECT action,correlation_id FROM audit_logs WHERE entity_type='exception' AND entity_id=%s ORDER BY id",(str(item['id']),))
        assert [x['action'] for x in cur.fetchall()]==['EXCEPTION_ACKNOWLEDGED','EXCEPTION_RESOLVED']

def test_session_close_auto_ignores_long_open_with_explicit_reason(db,api,seeded_factory):
    sid=make_long_open(db,seeded_factory)
    item=find(api.get(f'{BASE}/api/exceptions?view=action',timeout=10).json()['items'],sid)
    with db.cursor() as cur:
        cur.execute("UPDATE work_sessions SET status='CLOSED',ended_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=%s",(sid,))
    api.get(f'{BASE}/api/exceptions?view=action',timeout=10)
    with db.cursor() as cur:
        cur.execute("SELECT status,auto_ignore_reason,auto_ignored_at FROM exception_records WHERE id=%s",(item['id'],));row=cur.fetchone()
    assert row['status']=='AUTO_IGNORED' and row['auto_ignore_reason']=='SESSION_ALREADY_CLOSED' and row['auto_ignored_at']

def test_session_context_contains_related_center_exception(db,api,seeded_factory):
    sid=make_long_open(db,seeded_factory);api.get(f'{BASE}/api/exceptions?view=action',timeout=10)
    response=api.get(f'{BASE}/api/sessions/{sid}/context',timeout=10)
    assert response.status_code==200,response.text
    body=response.json();assert body['session']['session_id']==sid
    assert body['session']['employee_id']==seeded_factory['employee_id']
    assert body['session']['po_id']==seeded_factory['po_id']
    assert any(x['exception_type']=='LONG_OPEN_SESSION' for x in body['center_exceptions'])

def test_worker_cannot_view_or_mutate_exception_center(db,api,seeded_factory):
    sid=make_long_open(db,seeded_factory);item=find(api.get(f'{BASE}/api/exceptions?view=action',timeout=10).json()['items'],sid)
    username=f"v67-worker-{seeded_factory['suffix']}";password='Test@123456'
    with db.cursor() as cur:
        cur.execute("INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,'V67 Worker',%s,'worker',TRUE,FALSE) RETURNING id",(username,generate_password_hash(password)))
        user_id=cur.fetchone()['id']
    try:
        worker=requests.Session();login=worker.post(f'{BASE}/api/auth/login',json={'username':username,'password':password},timeout=10)
        assert login.status_code==200,login.text
        assert worker.get(f'{BASE}/api/exceptions',timeout=10).status_code==403
        assert worker.post(f"{BASE}/api/exceptions/{item['id']}/acknowledge",json={'expected_version':item['row_version']},timeout=10).status_code==403
    finally:
        with db.cursor() as cur:cur.execute('DELETE FROM users WHERE id=%s',(user_id,))

def test_concurrent_detection_jobs_create_one_active_incident(db,api,seeded_factory):
    sid=make_long_open(db,seeded_factory)
    def detect(_):return api.get(f'{BASE}/api/exceptions?view=action',timeout=10).status_code
    with ThreadPoolExecutor(max_workers=5) as pool:statuses=list(pool.map(detect,range(5)))
    assert statuses==[200]*5
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM exception_records WHERE session_id=%s AND exception_type='LONG_OPEN_SESSION' AND status IN ('OPEN','ACKNOWLEDGED')",(sid,))
        assert cur.fetchone()['n']==1

def test_new_true_edge_after_resolved_incident_creates_new_occurrence(db,api,seeded_factory):
    sid=make_long_open(db,seeded_factory);first=find(api.get(f'{BASE}/api/exceptions?view=action',timeout=10).json()['items'],sid)
    response=api.post(f"{BASE}/api/exceptions/{first['id']}/resolve",json={'expected_version':first['row_version'],'reason':'Đã kiểm tra'},timeout=10)
    assert response.status_code==200,response.text
    with db.cursor() as cur:cur.execute("UPDATE work_sessions SET status='CLOSED',ended_at=CURRENT_TIMESTAMP WHERE id=%s",(sid,))
    api.get(f'{BASE}/api/exceptions?view=action',timeout=10)
    with db.cursor() as cur:cur.execute("UPDATE work_sessions SET status='OPEN',ended_at=NULL,started_at=CURRENT_TIMESTAMP-INTERVAL '13 hours' WHERE id=%s",(sid,))
    second=find(api.get(f'{BASE}/api/exceptions?view=action',timeout=10).json()['items'],sid)
    assert second['id']!=first['id'] and second['occurrence_no']==2
