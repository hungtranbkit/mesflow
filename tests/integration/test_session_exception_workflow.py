from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')


def test_session_exception_workflow_round_trip(db, api, seeded_factory):
    g=seeded_factory
    first=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,%s,'docker-workflow','CLOSED',%s,%s,0,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],g['station_id'],datetime(2026,8,4,8,0,tzinfo=HCM),datetime(2026,8,4,10,0,tzinfo=HCM),f'wf-start-a-{g["suffix"]}',f'wf-finish-a-{g["suffix"]}')).fetchone()['id']
    second=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,%s,'docker-workflow','CLOSED',%s,%s,0,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],g['station_id'],datetime(2026,8,4,9,0,tzinfo=HCM),datetime(2026,8,4,11,0,tzinfo=HCM),f'wf-start-b-{g["suffix"]}',f'wf-finish-b-{g["suffix"]}')).fetchone()['id']
    r=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&workflow_status=NEW&limit=100',timeout=10)
    assert r.status_code==200,r.text
    item=next(x for x in r.json()['items'] if x['exception_code']=='OVERLAP' and x['session_id'] in (first,second))
    key={'session_id':item['session_id'],'exception_code':item['exception_code'],'exception_fingerprint':item['exception_fingerprint']}
    payload={'workflow_status':'IN_PROGRESS','assigned_to':'qa-supervisor','note':'Đang kiểm tra dữ liệu overlap','items':[key]}
    u=api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json=payload,timeout=10)
    assert u.status_code==200,u.text
    assert u.json()['updated_count']==1
    r2=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&workflow_status=IN_PROGRESS&limit=100',timeout=10)
    row=next(x for x in r2.json()['items'] if x['exception_fingerprint']==item['exception_fingerprint'])
    assert row['workflow_status']=='IN_PROGRESS' and row['assigned_to']=='qa-supervisor'
    payload.update(workflow_status='RESOLVED',resolution='DATA_CORRECTED',note='Đã điều chỉnh thời gian session bị overlap')
    done=api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json=payload,timeout=10)
    assert done.status_code==200,done.text
    r3=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&workflow_status=RESOLVED&limit=100',timeout=10)
    row=next(x for x in r3.json()['items'] if x['exception_fingerprint']==item['exception_fingerprint'])
    assert row['workflow_status']=='RESOLVED' and row['resolution']=='DATA_CORRECTED' and row['resolved_at']
