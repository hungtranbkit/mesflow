from datetime import date,datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
import uuid
import pytest

from conftest import BASE_URL
from mesflow.db.repositories.scheduling import operation_wip,priority_for_operation,priority_sort_key
from mesflow.core.working_calendar import working_seconds_between,all_shift_working_seconds_between
from mesflow.core.time_policy import business_date

pytestmark=pytest.mark.postgres

NOW=datetime(2026,8,9,5,0,tzinfo=timezone.utc)

def base(**extra):
    row={'operation_id':1,'po_code':'PO','part_sort':0,'operation_sort':0,'operation_status':'PLANNED','po_status':'IN_PROGRESS','planned_quantity':100,'done_qty':0,'defect_qty':0,'standard_seconds_per_unit':60}
    row.update(extra);return row

def test_operation_schedule_priority_is_time_sensitive_and_deterministic():
    overdue=priority_for_operation(base(planned_start_at=NOW-timedelta(hours=5),planned_end_at=NOW-timedelta(hours=1)),now=NOW)
    future=priority_for_operation(base(operation_id=2,planned_start_at=NOW+timedelta(days=2),planned_end_at=NOW+timedelta(days=3)),now=NOW)
    assert overdue['planning_priority_score']>future['planning_priority_score']
    changed=priority_for_operation(base(planned_start_at=NOW-timedelta(hours=5),planned_end_at=NOW+timedelta(hours=1)),now=NOW+timedelta(hours=3))
    assert changed['planning_priority_score']!=priority_for_operation(base(planned_start_at=NOW-timedelta(hours=5),planned_end_at=NOW+timedelta(hours=1)),now=NOW)['planning_priority_score']
    a=base(operation_id=8);b=base(operation_id=9)
    for item in (a,b):item.update(priority_for_operation(item,now=NOW));item['control_state']='ON_TRACK'
    assert sorted([b,a],key=priority_sort_key)[0]['operation_id']==8
    assert business_date(datetime(2026,8,8,18,0,tzinfo=timezone.utc))==date(2026,8,9)

def test_wip_first_operation_partial_downstream_terminal_and_rework():
    first=operation_wip(base(),None);assert first['actionable'] and first['wip_qty']==100 and first['wip_source']=='PLANNED_QUANTITY_FALLBACK'
    for status in ('COMPLETED','CANCELLED'):
        assert not operation_wip(base(operation_status=status),None)['actionable']
    downstream=base(operation_id=2,predecessor_operation_id=1)
    assert operation_wip(downstream,base(done_qty=0))['wip_qty']==0
    partial=operation_wip(downstream,base(done_qty=25));assert partial['actionable'] and partial['wip_qty']==25
    ledger=operation_wip(base(operation_id=3,input_flow_enabled=True,input_source_operation_id=1,input_available_qty=7,input_source_kind='REWORK'),None)
    assert ledger['wip_qty']==7

def test_working_time_crosses_midnight_and_excludes_break(cross_midnight_shift):
    # Fix Plan Phase 8: uses the dedicated cross_midnight_shift fixture
    # (conftest.py), NOT the real seeded NIGHT (18:00-00:00,
    # cross_midnight=FALSE as of the migration that corrected it -- see
    # test_postgres_schema.py's own fixed assertion). The fixture's own
    # WORK 22:00-00:00 / BREAK 00:00-01:00 / WORK 01:00-06:00 structure is
    # deliberately shaped so this exact 3h expectation still holds: of the
    # 4h window [22:00,02:00), 22:00-00:00 (2h) and 01:00-02:00 (1h) are
    # WORK, 00:00-01:00 (1h) is BREAK -- 3h WORK total.
    code = cross_midnight_shift['code']
    start=datetime(2026,8,8,15,0,tzinfo=timezone.utc) # 22:00 HCM
    end=datetime(2026,8,8,19,0,tzinfo=timezone.utc)   # 02:00 HCM
    assert working_seconds_between(start,end,shift_code=code)==3*3600
    # OPEN session uses the frozen report time as its effective end.
    assert working_seconds_between(start,NOW.replace(year=2026,month=8,day=8,hour=19),shift_code=code)==3*3600


def test_all_shift_working_seconds_between_sums_real_shifts_with_a_genuine_gap():
    """Fix Plan Phase 8: this used to assert 15h for the 08:00(HCM)->
    02:00(HCM,+1d) window using `all_shift_working_seconds_between` (which
    sums EVERY configured shift, not one specific shift_code) -- also
    stale against the real current NIGHT (18:00-00:00). Recomputed against
    the ACTUAL seeded config: DAY 08:00-17:00 contributes 8h WORK (480min
    work minus the lunch break, i.e. its own two WORK intervals), NIGHT
    18:00-00:00 contributes 5h WORK (target_minutes=300), and 00:00-02:00
    is a genuine NO_ACTIVE_SHIFT gap (Phase 2/8's own fix -- no shift
    covers it, contributes 0) -- 13h total, not 15h. Deliberately does NOT
    use cross_midnight_shift (that fixture would itself add a 3rd shift's
    contribution to this sum, which is not what this test is about)."""
    multi_start=datetime(2026,8,8,1,0,tzinfo=timezone.utc);multi_end=datetime(2026,8,8,19,0,tzinfo=timezone.utc)
    assert all_shift_working_seconds_between(multi_start,multi_end)==13*3600

def test_backend_start_uses_partial_upstream_wip(api,db,seeded_factory):
    g=seeded_factory;code=f'P2-DOWN-{g["suffix"]}'
    with db.cursor() as cur:
        cur.execute("INSERT INTO operations(production_order_id,part_id,code,name,status,qr,predecessor_operation_id) VALUES(%s,%s,%s,'Downstream','PLANNED',%s,%s) RETURNING id",(g['po_id'],g['part_id'],code,f'WF|OP|{code}',g['operation_id']));down=cur.fetchone()['id']
    blocked=api.post(f'{BASE_URL}/api/work-sessions/start',json={'request_id':str(uuid.uuid4()),'employee_id':g['employee_id'],'operation_id':down,'station_id':g['station_id']})
    assert blocked.status_code==409 and 'WIP=0' in blocked.json()['message']
    started=api.post(f'{BASE_URL}/api/work-sessions/start',json={'request_id':str(uuid.uuid4()),'employee_id':g['employee_id'],'operation_id':g['operation_id'],'station_id':g['station_id']});sid=started.json()['session']['id']
    assert api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish',json={'request_id':str(uuid.uuid4()),'good_qty':20}).status_code==200
    allowed=api.post(f'{BASE_URL}/api/work-sessions/start',json={'request_id':str(uuid.uuid4()),'employee_id':g['employee_id'],'operation_id':down,'station_id':g['station_id']})
    assert allowed.status_code==201,allowed.text
    down_sid=allowed.json()['session']['id'];api.post(f'{BASE_URL}/api/work-sessions/{down_sid}/finish',json={'request_id':str(uuid.uuid4()),'good_qty':10})
    with db.cursor() as cur:
        cur.execute('DELETE FROM kiosk_idempotency WHERE request_id IN (SELECT start_request_id FROM work_sessions WHERE operation_id=%s) OR request_id IN (SELECT finish_request_id FROM work_sessions WHERE operation_id=%s)',(down,down))
        cur.execute('DELETE FROM operation_input_consumptions WHERE target_operation_id=%s OR source_operation_id=%s',(down,down))
        cur.execute('DELETE FROM operation_adjustments WHERE operation_id=%s',(down,))
        cur.execute('DELETE FROM work_sessions WHERE operation_id=%s',(down,));cur.execute('DELETE FROM operations WHERE id=%s',(down,))

def test_shift_api_allocates_cross_boundary_without_changing_session(api,db,seeded_factory,cross_midnight_shift):
    # Fix Plan Phase 8: uses the dedicated cross_midnight_shift fixture
    # instead of the real NIGHT (no longer cross-midnight) -- see
    # test_working_time_crosses_midnight_and_excludes_break's own comment
    # for why 3h WORK / 4h duration still holds for this fixture's shape.
    g=seeded_factory
    shift=cross_midnight_shift['id']
    start=datetime(2026,8,8,15,0,tzinfo=timezone.utc);end=datetime(2026,8,8,19,0,tzinfo=timezone.utc)
    with db.cursor() as cur:
        cur.execute("INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,ended_at,start_request_id,finish_request_id) VALUES(%s,%s,%s,'CLOSED',%s,%s,%s,%s) RETURNING id",(g['employee_id'],g['operation_id'],g['station_id'],start,end,f'P2-S-{uuid.uuid4()}',f'P2-F-{uuid.uuid4()}'));sid=cur.fetchone()['id']
    response=api.get(f'{BASE_URL}/api/dashboard/shift?shift_date=2026-08-08&shift_id={shift}&limit=100')
    assert response.status_code==200,response.text
    item=next(x for x in response.json()['sessions'] if x['session_id']==sid)
    assert item['duration_seconds']==4*3600 and item['work_duration_seconds']==3*3600 and item['total_duration_seconds']==4*3600
    original=db.execute('SELECT started_at,ended_at FROM work_sessions WHERE id=%s',(sid,)).fetchone();assert original['started_at']==start and original['ended_at']==end
    # Flask serializes this legacy field as an RFC 7231 HTTP-date.  Parse the
    # public representation and prove that it denotes the same UTC instant as
    # the PostgreSQL timestamptz value (no implicit/double +07 conversion).
    assert parsedate_to_datetime(item['started_at']).astimezone(timezone.utc)==start
