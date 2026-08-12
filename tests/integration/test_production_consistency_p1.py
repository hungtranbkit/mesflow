import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from werkzeug.security import generate_password_hash

from conftest import BASE_URL
from mesflow.db.repositories.master_data import TemplateTreeRepository

pytestmark=pytest.mark.postgres

def one(db,sql,params=()):
    with db.cursor() as cur:cur.execute(sql,params);return cur.fetchone()

def test_template_dependency_cycle_is_rejected_before_instantiation():
    valid=[{'code':'A','input_flow_enabled':False},{'code':'B','input_flow_enabled':True,'input_source_code':'A'}]
    TemplateTreeRepository._validate_dependency_graph(valid)
    with pytest.raises(Exception,match='A -> B -> A|B -> A -> B'):
        TemplateTreeRepository._validate_dependency_graph([{'code':'A','input_flow_enabled':True,'input_source_code':'B'},{'code':'B','input_flow_enabled':True,'input_source_code':'A'}])

def test_dependency_self_two_three_node_cycles_and_valid_graph(api,db,seeded_factory):
    g=seeded_factory
    with db.cursor() as cur:
        ids=[]
        for suffix in ('B','C'):
            code=f"P1-{suffix}-{g['suffix']}";cur.execute("INSERT INTO operations(production_order_id,part_id,code,name,status,qr) VALUES(%s,%s,%s,%s,'PLANNED',%s) RETURNING id",(g['po_id'],g['part_id'],code,suffix,f'WF|OP|{code}'));ids.append(cur.fetchone()['id'])
    a,b,c=g['operation_id'],ids[0],ids[1]
    valid=api.patch(f'{BASE_URL}/api/operations/{b}',json={'predecessor_operation_id':a})
    assert valid.status_code==200,valid.text
    self_cycle=api.patch(f'{BASE_URL}/api/operations/{a}',json={'predecessor_operation_id':a})
    assert self_cycle.status_code==409 and 'cycle' in self_cycle.json()['message'].lower()
    two=api.patch(f'{BASE_URL}/api/operations/{a}',json={'predecessor_operation_id':b})
    assert two.status_code==409 and 'P1-B' in two.json()['message']
    assert api.patch(f'{BASE_URL}/api/operations/{c}',json={'predecessor_operation_id':b}).status_code==200
    three=api.patch(f'{BASE_URL}/api/operations/{a}',json={'predecessor_operation_id':c})
    assert three.status_code==409 and ' -> ' in three.json()['message']
    with db.cursor() as cur:cur.execute('DELETE FROM operations WHERE id=ANY(%s)',(ids,))

def test_existing_cycle_is_reported_with_path(api,db,seeded_factory):
    g=seeded_factory
    with db.cursor() as cur:
        code=f"P1-OLD-{g['suffix']}";cur.execute("INSERT INTO operations(production_order_id,part_id,code,name,status,qr) VALUES(%s,%s,%s,'B','PLANNED',%s) RETURNING id",(g['po_id'],g['part_id'],code,f'WF|OP|{code}'));b=cur.fetchone()['id']
        cur.execute('UPDATE operations SET predecessor_operation_id=%s WHERE id=%s',(b,g['operation_id']))
        cur.execute('UPDATE operations SET predecessor_operation_id=%s WHERE id=%s',(g['operation_id'],b))
    response=api.patch(f'{BASE_URL}/api/operations/{b}',json={'name':'still B'})
    assert response.status_code==409 and 'Dependency cycle:' in response.json()['message']
    with db.cursor() as cur:
        cur.execute('UPDATE operations SET predecessor_operation_id=NULL WHERE id IN (%s,%s)',(g['operation_id'],b));cur.execute('DELETE FROM operations WHERE id=%s',(b,))

def test_event_retry_sequential_and_concurrent_has_one_effect(db,seeded_factory):
    event_id=f'P1-EVENT-{uuid.uuid4()}';body={'device_uuid':'LEGACY-P1','events':[{'event_id':event_id,'event_type':'ERROR','message':'retry'}]}
    first=requests.post(f'{BASE_URL}/api/station/events/sync',json=body,timeout=10);second=requests.post(f'{BASE_URL}/api/station/events/sync',json=body,timeout=10)
    assert first.status_code==200 and second.json()['results'][0]['status']=='duplicate'
    concurrent_id=f'P1-EVENT-{uuid.uuid4()}';payload={'device_uuid':'LEGACY-P1','events':[{'event_id':concurrent_id,'event_type':'ERROR'}]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda _:requests.post(f'{BASE_URL}/api/station/events/sync',json=payload,timeout=10),range(2)))
    assert all(x.status_code==200 for x in responses)
    assert one(db,'SELECT COUNT(*) n FROM kiosk_events WHERE event_uuid IN (%s,%s)',(event_id,concurrent_id))['n']==2
    with db.cursor() as cur:cur.execute('DELETE FROM notifications WHERE source_type=%s AND source_id IN (SELECT id::text FROM kiosk_events WHERE event_uuid IN (%s,%s))',('KIOSK_EVENT',event_id,concurrent_id));cur.execute('DELETE FROM kiosk_events WHERE event_uuid IN (%s,%s)',(event_id,concurrent_id))

def test_authentication_permissions_and_kiosk_admin_boundary(api,db,seeded_factory):
    g=seeded_factory
    anonymous=requests.post(f'{BASE_URL}/api/work-sessions/start',json={'request_id':str(uuid.uuid4()),'employee_id':g['employee_id'],'operation_id':g['operation_id']})
    assert anonymous.status_code==401
    assert requests.post(f'{BASE_URL}/api/production-state/reconcile',json={'po_id':g['po_id']}).status_code==401
    username=f'viewer-{g["suffix"]}';password='Viewer@123456'
    with db.cursor() as cur:cur.execute("INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,'P1 Viewer',%s,'viewer',true,false) RETURNING id",(username,generate_password_hash(password)));user_id=cur.fetchone()['id']
    viewer=requests.Session();assert viewer.post(f'{BASE_URL}/api/auth/login',json={'username':username,'password':password}).status_code==200
    assert viewer.patch(f'{BASE_URL}/api/operations/{g["operation_id"]}',json={'name':'forbidden'}).status_code==403
    assert viewer.post(f'{BASE_URL}/api/production-state/reconcile',json={'po_id':g['po_id']}).status_code==403
    assert requests.delete(f'{BASE_URL}/api/production-orders/{g["po_id"]}/force',headers={'X-Kiosk-Token':'not-an-admin-session'}).status_code==401
    with db.cursor() as cur:cur.execute('DELETE FROM users WHERE id=%s',(user_id,))

def test_direct_aggregate_rejected_but_source_edit_reconciles(api,db,seeded_factory):
    g=seeded_factory
    direct=api.patch(f'{BASE_URL}/api/operations/{g["operation_id"]}',json={'done_qty':77})
    assert direct.status_code==409,direct.text
    started=api.post(f'{BASE_URL}/api/work-sessions/start',json={'request_id':str(uuid.uuid4()),'employee_id':g['employee_id'],'operation_id':g['operation_id'],'station_id':g['station_id']})
    assert started.status_code==201,started.text
    sid=started.json()['session']['id']
    finished=api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish',json={'request_id':str(uuid.uuid4()),'good_qty':12,'defect_qty':2,'rework_qty':1})
    assert finished.status_code==200,finished.text
    edit_key=str(uuid.uuid4());edit_body={'good_qty':15,'defect_qty':3,'rework_qty':2,'reason':'P1 audited correction','request_id':edit_key}
    edited=api.patch(f'{BASE_URL}/api/supervisor/sessions/{sid}',json=edit_body)
    assert edited.status_code==200,edited.text
    replay=api.patch(f'{BASE_URL}/api/supervisor/sessions/{sid}',json=edit_body)
    assert replay.status_code==200,replay.text
    assert one(db,'SELECT COUNT(*) n FROM operation_adjustments WHERE session_id=%s AND reason=%s',(sid,'P1 audited correction'))['n']==1
    state=one(db,'SELECT done_qty,defect_qty,rework_qty FROM operations WHERE id=%s',(g['operation_id'],))
    assert (state['done_qty'],state['defect_qty'],state['rework_qty'])==(15,3,2)
