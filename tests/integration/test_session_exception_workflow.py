from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')


def test_normal_and_short_zero_quantity_sessions_do_not_raise_exceptions(db, api, seeded_factory):
    g=seeded_factory
    normal_id=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,%s,'docker-normal','CLOSED',%s,%s,5,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],g['station_id'],datetime(2026,8,3,8,0,tzinfo=HCM),datetime(2026,8,3,9,0,tzinfo=HCM),f'normal-start-{g["suffix"]}',f'normal-end-{g["suffix"]}')).fetchone()['id']
    short_zero_id=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,%s,'docker-short-zero','CLOSED',%s,%s,0,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],g['station_id'],datetime(2026,8,3,10,0,tzinfo=HCM),datetime(2026,8,3,11,0,tzinfo=HCM),f'zero-start-{g["suffix"]}',f'zero-end-{g["suffix"]}')).fetchone()['id']
    rows=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100',timeout=10).json()['items']
    assert not [row for row in rows if row['session_id'] in (normal_id,short_zero_id)]


def test_qa_missing_station_is_detected_and_traceable(db, api, seeded_factory):
    g=seeded_factory
    session_id=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,NULL,'','CLOSED',%s,%s,2,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],datetime(2026,8,3,12,0,tzinfo=HCM),datetime(2026,8,3,13,0,tzinfo=HCM),f'QA-RUN-CASE5-EXPECTED-MISSING-STATION-{g["suffix"]}',f'QA-RUN-CASE5-FINISH-{g["suffix"]}')).fetchone()['id']
    # QA-tagged exceptions are detected and traceable, but hidden from the
    # manager's default Inbox (view=inbox) -- only visible via view=all/history.
    inbox=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100',timeout=10).json()['items']
    assert not [row for row in inbox if row['session_id']==session_id]
    rows=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100&view=all',timeout=10).json()['items']
    item=next(row for row in rows if row['session_id']==session_id and row['exception_code']=='MISSING_STATION')
    assert item['data_source']=='QA_TEST'
    assert item['classification']=='QA_TEST'
    assert item['source_trace_id'].startswith('QA-RUN-CASE5-EXPECTED-MISSING-STATION-')


def test_open_too_long_stays_in_progress_after_session_is_closed(db, api, seeded_factory):
    g=seeded_factory
    session_id=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,good_qty,defect_qty,start_request_id)
      VALUES(%s,%s,%s,'docker-long-open','OPEN',CURRENT_TIMESTAMP-INTERVAL '13 hours',0,0,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],g['station_id'],f'QA-RUN-CASE1-EXPECTED-FORGOT-{g["suffix"]}')).fetchone()['id']
    # QA-tagged -> hidden from the default Inbox even though it is detected.
    inbox=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100',timeout=10).json()['items']
    assert not [x for x in inbox if x['session_id']==session_id]
    url=f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100&view=all'
    item=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_code']=='OPEN_TOO_LONG')
    assert item['data_source']=='QA_TEST'
    assert item['source_trace_id'].startswith('QA-RUN-CASE1-EXPECTED-FORGOT-')
    key={k:item[k] for k in ('session_id','exception_code','exception_fingerprint')}
    claim={'workflow_status':'IN_PROGRESS','assigned_to':'qa-supervisor','items':[key]}
    assert api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json=claim,timeout=10).status_code==200
    db.execute("UPDATE work_sessions SET status='CLOSED',ended_at=CURRENT_TIMESTAMP WHERE id=%s",(session_id,))
    corrected=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_fingerprint']==item['exception_fingerprint'])
    assert corrected['workflow_status']=='IN_PROGRESS' and corrected['is_active'] is False
    claim.update(workflow_status='RESOLVED',resolution='SESSION_CLOSED',note='Đã xác minh và đóng Session')
    assert api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json=claim,timeout=10).status_code==200
    history=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_fingerprint']==item['exception_fingerprint'])
    assert history['workflow_status']=='RESOLVED' and history['resolved_at']


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
    db.execute('UPDATE work_sessions SET started_at=%s,ended_at=%s WHERE id=%s',
      (datetime(2026,8,4,11,0,tzinfo=HCM),datetime(2026,8,4,12,0,tzinfo=HCM),second))
    corrected=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&workflow_status=IN_PROGRESS&limit=100',timeout=10)
    kept=next(x for x in corrected.json()['items'] if x['exception_fingerprint']==item['exception_fingerprint'])
    assert kept['is_active'] is False
    assert 'không còn được phát hiện' in kept['exception_message'].lower()
    payload.update(workflow_status='RESOLVED',resolution='DATA_CORRECTED',note='Đã điều chỉnh thời gian session bị overlap')
    done=api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json=payload,timeout=10)
    assert done.status_code==200,done.text
    r3=api.get(f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&workflow_status=RESOLVED&limit=100',timeout=10)
    row=next(x for x in r3.json()['items'] if x['exception_fingerprint']==item['exception_fingerprint'])
    assert row['workflow_status']=='RESOLVED' and row['resolution']=='DATA_CORRECTED' and row['resolved_at']


def test_missing_station_history_and_repeat_occurrence(db, api, seeded_factory):
    g=seeded_factory
    session_id=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,NULL,'','CLOSED',%s,%s,2,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],datetime(2026,8,5,8,0,tzinfo=HCM),datetime(2026,8,5,9,0,tzinfo=HCM),f'missing-start-{g["suffix"]}',f'missing-end-{g["suffix"]}')).fetchone()['id']
    url=f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100'
    first=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_code']=='MISSING_STATION')
    key={k:first[k] for k in ('session_id','exception_code','exception_fingerprint')}
    claim={'workflow_status':'IN_PROGRESS','assigned_to':'qa-supervisor','note':'Đang xác minh trạm','items':[key]}
    assert api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json=claim,timeout=10).status_code==200
    db.execute('UPDATE work_sessions SET station_id=%s WHERE id=%s',(g['station_id'],session_id))
    inactive=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_fingerprint']==first['exception_fingerprint'])
    assert inactive['workflow_status']=='IN_PROGRESS' and inactive['is_active'] is False
    claim.update(workflow_status='RESOLVED',resolution='DATA_CORRECTED',note='Đã bổ sung trạm theo bằng chứng')
    assert api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json=claim,timeout=10).status_code==200
    # RESOLVED leaves the default Inbox, but stays fully visible in History.
    assert not [x for x in api.get(url,timeout=10).json()['items'] if x['exception_fingerprint']==first['exception_fingerprint']]
    history=next(x for x in api.get(url+'&view=all',timeout=10).json()['items'] if x['exception_fingerprint']==first['exception_fingerprint'])
    assert history['workflow_status']=='RESOLVED' and history['review_created_at']

    # Mirrors the real session-correction path (execution.update_session),
    # which always stamps updated_at -- that stamp is exactly the signal the
    # detector uses to tell a genuine new mutation from an untouched session.
    db.execute("UPDATE work_sessions SET station_id=NULL,device_uuid='',updated_at=CURRENT_TIMESTAMP WHERE id=%s",(session_id,))
    # The genuinely new occurrence is real Inbox work again (default view).
    rows=api.get(url,timeout=10).json()['items']
    repeated=next(x for x in rows if x['exception_code']=='MISSING_STATION' and x['workflow_status']=='NEW')
    assert repeated['exception_fingerprint']!=first['exception_fingerprint']
    assert '#occurrence:' in repeated['exception_fingerprint']
    # The old, already-resolved occurrence does not reappear in the default
    # Inbox alongside it -- it stays visible only in History (view=all).
    assert not [x for x in rows if x['exception_fingerprint']==first['exception_fingerprint']]
    history=api.get(url+'&view=all',timeout=10).json()['items']
    old=next(x for x in history if x['exception_fingerprint']==first['exception_fingerprint'])
    assert old['workflow_status']=='RESOLVED'


def test_ignore_requires_reason_and_remains_history(db, api, seeded_factory):
    g=seeded_factory
    db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,NULL,'','CLOSED',%s,%s,1,0,%s,%s)""",
      (g['employee_id'],g['operation_id'],datetime(2026,8,6,8,0,tzinfo=HCM),datetime(2026,8,6,9,0,tzinfo=HCM),f'ignore-start-{g["suffix"]}',f'ignore-end-{g["suffix"]}'))
    url=f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100'
    item=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_code']=='MISSING_STATION')
    assert item['data_source']=='REAL_USER'
    key={k:item[k] for k in ('session_id','exception_code','exception_fingerprint')}
    assert api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json={'workflow_status':'IN_PROGRESS','items':[key]},timeout=10).status_code==200
    rejected=api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json={'workflow_status':'IGNORED','note':'','items':[key]},timeout=10)
    assert rejected.status_code==400
    accepted=api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json={'workflow_status':'IGNORED','note':'Đã xác minh đây là dữ liệu ngoại lệ hợp lệ','items':[key]},timeout=10)
    assert accepted.status_code==200
    # IGNORE removes it from the active Inbox (default view)...
    assert not [x for x in api.get(url,timeout=10).json()['items'] if x['exception_fingerprint']==item['exception_fingerprint']]
    # ...but it remains fully visible, with evidence, in History.
    history=next(x for x in api.get(url+'&view=all',timeout=10).json()['items'] if x['exception_fingerprint']==item['exception_fingerprint'])
    assert history['workflow_status']=='IGNORED' and history['review_note']


def test_real_orphan_open_session_is_action_required(db, api, seeded_factory):
    g=seeded_factory
    # Employee has exactly one session, open far too long, and never did
    # anything else afterwards -- a genuine orphan with no ambiguity.
    db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,good_qty,defect_qty,start_request_id)
      VALUES(%s,%s,%s,'docker-orphan','OPEN',CURRENT_TIMESTAMP-INTERVAL '20 hours',0,0,%s)""",
      (g['employee_id'],g['operation_id'],g['station_id'],f'orphan-start-{g["suffix"]}'))
    url=f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100'
    item=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_code']=='OPEN_TOO_LONG')
    assert item['classification']=='ACTION_REQUIRED'


def test_ambiguous_forgotten_finish_is_confirmation(db, api, seeded_factory):
    g=seeded_factory
    db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,good_qty,defect_qty,start_request_id)
      VALUES(%s,%s,%s,'docker-forgot','OPEN',CURRENT_TIMESTAMP-INTERVAL '18 hours',3,0,%s)""",
      (g['employee_id'],g['operation_id'],g['station_id'],f'forgot-start-{g["suffix"]}'))
    # Employee moved on and clocked other work afterwards -- strong evidence
    # they simply forgot to close the earlier session, but not certain enough
    # to auto-fix (unknown true finish time/quantity) -> CONFIRMATION.
    db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,%s,'docker-forgot','CLOSED',CURRENT_TIMESTAMP-INTERVAL '2 hours',CURRENT_TIMESTAMP-INTERVAL '1 hours',5,0,%s,%s)""",
      (g['employee_id'],g['operation_id'],g['station_id'],f'forgot-later-start-{g["suffix"]}',f'forgot-later-end-{g["suffix"]}'))
    url=f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100'
    item=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_code']=='OPEN_TOO_LONG')
    assert item['classification']=='CONFIRMATION'


def test_trivial_overlap_wrong_scan_is_auto_ignored_and_history_only(db, api, seeded_factory):
    g=seeded_factory
    # The session the employee actually worked.
    real_id=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,%s,'docker-real','CLOSED',%s,%s,4,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],g['station_id'],datetime(2026,8,7,8,0,tzinfo=HCM),datetime(2026,8,7,10,0,tzinfo=HCM),f'real-start-{g["suffix"]}',f'real-end-{g["suffix"]}')).fetchone()['id']
    # A mis-scan opened a bogus second session overlapping the real one for
    # two minutes before the operator noticed and corrected it: zero
    # production, short-lived -- a trivial mistake, not real overlapping
    # work. Matches the task's own example: wrong_scan AND no production
    # mutation occurred AND subsequent valid action happened -> AUTO_IGNORED.
    mistake_id=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,%s,'docker-mistake','CLOSED',%s,%s,0,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],g['station_id'],datetime(2026,8,7,8,30,tzinfo=HCM),datetime(2026,8,7,8,32,tzinfo=HCM),f'mistake-start-{g["suffix"]}',f'mistake-end-{g["suffix"]}')).fetchone()['id']
    url=f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100'
    # Reading the Inbox reconciles auto-ignore -- the trivial overlap never
    # shows up as manager work.
    inbox=api.get(url,timeout=10).json()['items']
    assert not [x for x in inbox if x['exception_code']=='OVERLAP' and mistake_id in (x['session_id'],x['conflict_session_id'])]
    history=api.get(url+'&view=all',timeout=10).json()['items']
    item=next(x for x in history if x['exception_code']=='OVERLAP' and mistake_id in (x['session_id'],x['conflict_session_id']))
    assert item['workflow_status']=='IGNORED'
    assert item['resolution']=='AUTO_IGNORED'
    assert item['resolved_by']=='system:auto_ignore'
    # The real session itself is never touched or flagged as the mistake.
    assert not [x for x in history if x['exception_code']=='OVERLAP' and x['session_id']==real_id and x['resolution']=='AUTO_IGNORED']


def test_accidental_action_with_no_session_created_produces_no_exception(db, api, seeded_factory):
    g=seeded_factory
    # A cancelled/mis-scanned kiosk action that never resulted in a session
    # row cannot, by construction (the detector only ever reads
    # work_sessions), surface as an exception. Nothing to see for this employee.
    url=f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100&view=all'
    assert api.get(url,timeout=10).json()['items']==[]


def test_ignored_condition_does_not_reappear_when_unchanged(db, api, seeded_factory):
    g=seeded_factory
    session_id=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,NULL,'','CLOSED',%s,%s,2,0,%s,%s) RETURNING id""",
      (g['employee_id'],g['operation_id'],datetime(2026,8,8,8,0,tzinfo=HCM),datetime(2026,8,8,9,0,tzinfo=HCM),f'stay-start-{g["suffix"]}',f'stay-end-{g["suffix"]}')).fetchone()['id']
    url=f'http://mesflow-test-api:8080/api/session-exceptions?employee_id={g["employee_id"]}&limit=100'
    item=next(x for x in api.get(url,timeout=10).json()['items'] if x['exception_code']=='MISSING_STATION')
    key={k:item[k] for k in ('session_id','exception_code','exception_fingerprint')}
    assert api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json={'workflow_status':'IN_PROGRESS','items':[key]},timeout=10).status_code==200
    ignore=api.patch('http://mesflow-test-api:8080/api/session-exceptions/workflow',json={'workflow_status':'IGNORED','note':'Đã xác nhận không cần bổ sung trạm','items':[key]},timeout=10)
    assert ignore.status_code==200
    # The underlying condition (station still missing) never changed -- re-reading
    # the Inbox several times must not mint a new NEW occurrence.
    for _ in range(3):
        rows=api.get(url,timeout=10).json()['items']
        assert not [x for x in rows if x['session_id']==session_id]
    history=api.get(url+'&view=all',timeout=10).json()['items']
    matching=[x for x in history if x['session_id']==session_id and x['exception_code']=='MISSING_STATION']
    assert len(matching)==1
    assert matching[0]['exception_fingerprint']==item['exception_fingerprint']
    assert matching[0]['workflow_status']=='IGNORED'
