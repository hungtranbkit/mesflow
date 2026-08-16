import uuid
import pytest
import requests
import time
from werkzeug.security import generate_password_hash
pytestmark=pytest.mark.postgres
BASE='http://mesflow-test-api:8080'
def start(api,g):
    return api.post(f'{BASE}/api/work-sessions/start',json={'request_id':f'v68-start-{uuid.uuid4()}','employee_id':g['employee_id'],'operation_id':g['operation_id'],'station_id':g['station_id']},timeout=10)
def finish(api,sid,**qty):
    body={'request_id':f'v68-finish-{uuid.uuid4()}','good_qty':10,'defect_qty':2,'rework_qty':1};body.update(qty);return api.post(f'{BASE}/api/work-sessions/{sid}/finish',json=body,timeout=10)
def test_session_vertical_slice_order_correlation_quantity_and_reconciliation(db,api,seeded_factory):
    begun=start(api,seeded_factory);assert begun.status_code==201,begun.text;sid=begun.json()['session']['id']
    ended=finish(api,sid);assert ended.status_code==200,ended.text
    trace=api.get(f'{BASE}/api/sessions/{sid}/trace?limit=100',timeout=10);assert trace.status_code==200,trace.text
    events=trace.json()['events'];types=[x['event_type'] for x in events]
    for expected in ('SESSION_STARTED','GOOD_QUANTITY_RECORDED','DEFECT_QUANTITY_RECORDED','REPAIRABLE_DEFECT_RECORDED','SESSION_FINISHED'):assert expected in types
    times=[x['occurred_at'] for x in events];assert times==sorted(times,reverse=True)
    quantities=api.get(f'{BASE}/api/sessions/{sid}/quantity-history',timeout=10).json()
    assert {x['movement_type']:x['delta'] for x in quantities['items']}=={'GOOD':10,'DEFECT':2,'REPAIRABLE':1}
    assert quantities['reconciliation']['matches'] is True
def test_correction_is_append_only_with_old_new_actor_reason(db,api,seeded_factory):
    sid=start(api,seeded_factory).json()['session']['id'];finish(api,sid)
    response=api.post(f'{BASE}/api/supervisor/sessions/{sid}/adjust',json={'request_id':f'v68-adjust-{uuid.uuid4()}','good_qty':8,'defect_qty':3,'rework_qty':1,'reason':'Sửa double scan'},timeout=10)
    assert response.status_code==200,response.text
    history=api.get(f'{BASE}/api/sessions/{sid}/quantity-history',timeout=10).json();rows=history['items']
    good=[x for x in rows if x['movement_type']=='GOOD'];assert {x['delta'] for x in good}=={10,-2}
    correction=next(x for x in rows if x['source']=='CORRECTION' and x['movement_type']=='GOOD')
    assert correction['previous_value']==10 and correction['new_value']==8 and correction['reason']=='Sửa double scan' and correction['actor_name']=='admin'
    assert history['reconciliation']['matches'] is True
    trace=api.get(f'{BASE}/api/sessions/{sid}/trace',timeout=10).json()['events'];assert any(x['event_type']=='VALUE_CHANGED' and x['category']=='CHANGE' for x in trace)
def test_failed_finish_creates_no_false_trace_or_quantity(db,api,seeded_factory):
    sid=start(api,seeded_factory).json()['session']['id'];bad=finish(api,sid,good_qty=1,defect_qty=1,rework_qty=2);assert bad.status_code==400
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM quantity_movements WHERE session_id=%s',(sid,));assert cur.fetchone()['n']==0
        cur.execute("SELECT COUNT(*) n FROM production_trace_events WHERE session_id=%s AND event_type='SESSION_FINISHED'",(sid,));assert cur.fetchone()['n']==0
def test_kiosk_session_trace_id_is_correlated(db,api,seeded_factory):
    sid=start(api,seeded_factory).json()['session']['id'];trace_id=f'session-trace-{uuid.uuid4()}'
    with db.cursor() as cur:cur.execute("""INSERT INTO kiosk_client_events(client_event_id,payload_hash,kiosk_id,local_sequence,session_trace_id,event_type,status,server_session_id,payload_json)
      VALUES(%s,'hash','K-V68',987654321,%s,'SCAN_OPERATION','APPLIED',%s,'{}')""",(str(uuid.uuid4()),trace_id,sid))
    events=api.get(f'{BASE}/api/sessions/{sid}/trace',timeout=10).json()['events'];row=next(x for x in events if x['source']=='KIOSK');assert row['session_trace_id']==trace_id and row['session_id']==sid
def test_po_trace_merges_sessions_and_cursor_pagination(db,api,seeded_factory):
    sid=start(api,seeded_factory).json()['session']['id'];finish(api,sid)
    first=api.get(f"{BASE}/api/production-orders/{seeded_factory['po_id']}/trace?limit=2",timeout=10).json();assert len(first['events'])==2 and first['has_more'] is True
    second=api.get(f"{BASE}/api/production-orders/{seeded_factory['po_id']}/trace",params={'limit':2,'before':first['next_before']},timeout=10).json();assert not ({x['id'] for x in first['events']}&{x['id'] for x in second['events']})
    assert all(x['po_id']==seeded_factory['po_id'] for x in first['events'])
def test_exception_lifecycle_appears_in_po_trace(db,api,seeded_factory):
    sid=start(api,seeded_factory).json()['session']['id']
    with db.cursor() as cur:cur.execute("UPDATE work_sessions SET started_at=CURRENT_TIMESTAMP-INTERVAL '13 hours' WHERE id=%s",(sid,))
    exceptions=api.get(f'{BASE}/api/exceptions?view=action',timeout=10).json()['items'];x=next(x for x in exceptions if x['session_id']==sid and x['exception_type']=='LONG_OPEN_SESSION')
    ack=api.post(f"{BASE}/api/exceptions/{x['id']}/acknowledge",json={'expected_version':x['row_version']},timeout=10).json()['item']
    api.post(f"{BASE}/api/exceptions/{x['id']}/resolve",json={'expected_version':ack['row_version'],'reason':'Đã xác minh'},timeout=10)
    events=api.get(f"{BASE}/api/production-orders/{seeded_factory['po_id']}/trace?category=EXCEPTION",timeout=10).json()['events'];types={e['event_type'] for e in events}
    assert {'EXCEPTION_DETECTED','EXCEPTION_ACKNOWLEDGED','EXCEPTION_RESOLVED'}<=types
def test_worker_cannot_read_trace_or_quantity_history(db,api,seeded_factory):
    username=f"v68-worker-{seeded_factory['suffix']}";password='Test@123456'
    with db.cursor() as cur:cur.execute("INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,'worker',%s,'worker',TRUE,FALSE) RETURNING id",(username,generate_password_hash(password)));uid=cur.fetchone()['id']
    try:
        worker=requests.Session();assert worker.post(f'{BASE}/api/auth/login',json={'username':username,'password':password},timeout=10).status_code==200
        assert worker.get(f"{BASE}/api/production-orders/{seeded_factory['po_id']}/trace",timeout=10).status_code==403
        assert worker.get(f"{BASE}/api/production-orders/{seeded_factory['po_id']}/quantity-history",timeout=10).status_code==403
    finally:
        with db.cursor() as cur:cur.execute('DELETE FROM users WHERE id=%s',(uid,))
def test_trace_2500_events_paginates_without_n_plus_one(db,api,seeded_factory):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_trace_events(event_type,category,production_order_id,part_id,operation_id,title,occurred_at)
          SELECT 'LOAD_EVENT','SYSTEM',%s,%s,%s,'Load event',CURRENT_TIMESTAMP-(g||' seconds')::interval FROM generate_series(1,2500) g""",(seeded_factory['po_id'],seeded_factory['part_id'],seeded_factory['operation_id']))
    started=time.perf_counter();response=api.get(f"{BASE}/api/production-orders/{seeded_factory['po_id']}/trace?limit=100",timeout=10);elapsed=time.perf_counter()-started
    assert response.status_code==200 and len(response.json()['events'])==100 and response.json()['has_more'] is True
    assert elapsed<3.0
