from datetime import date,datetime,time,timezone
from zoneinfo import ZoneInfo

import pytest
from flask import Flask

from mesflow.core.time_policy import aware_utc,business_date,business_date_end_utc,business_datetime_utc
from mesflow.db.repositories.scheduling import as_utc,get_available_input,operation_wip,priority_for_operation
from mesflow.web.errors import api_error_response


def test_business_date_is_interpreted_in_site_timezone_before_utc():
    assert business_datetime_utc(date(2026,8,9),time(23,59,59)) == datetime(2026,8,9,16,59,59,tzinfo=timezone.utc)
    assert business_date_end_utc(date(2026,8,9)).date() == date(2026,8,9)
    assert as_utc(date(2026,8,9)) == datetime(2026,8,9,16,59,59,tzinfo=timezone.utc)


def test_aware_datetime_roundtrip_never_double_converts_or_attaches_zone():
    local=datetime(2026,8,9,0,30,tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))
    utc=aware_utc(local)
    assert utc == datetime(2026,8,8,17,30,tzinfo=timezone.utc)
    assert aware_utc(utc)==utc
    assert business_date(utc)==date(2026,8,9)


def test_priority_uses_hcm_end_of_business_date_near_midnight():
    row={'operation_id':1,'operation_status':'PLANNED','po_status':'IN_PROGRESS','planned_quantity':10,'done_qty':0,'defect_qty':0,'planned_end_at':date(2026,8,9),'standard_seconds_per_unit':60}
    before=priority_for_operation(row,now=datetime(2026,8,9,16,30,tzinfo=timezone.utc))
    after=priority_for_operation(row,now=datetime(2026,8,9,17,30,tzinfo=timezone.utc))
    assert before['schedule_lateness_seconds']==0
    assert after['schedule_lateness_seconds']>0


def test_first_operation_input_abstraction_is_explicit_and_bounded():
    base={'planned_quantity':500,'done_qty':0,'defect_qty':0,'operation_status':'PLANNED','po_status':'IN_PROGRESS'}
    assert get_available_input(base)=={'available_input_qty':500,'wip_source':'PLANNED_QUANTITY_FALLBACK'}
    produced={**base,'done_qty':100}
    assert get_available_input(produced)['available_input_qty']==400
    assert get_available_input({**produced,'rework_qty':80})['available_input_qty']==400
    downstream=get_available_input({**base,'done_qty':0},{'done_qty':100,'operation_status':'IN_PROGRESS'})
    assert downstream=={'available_input_qty':100,'wip_source':'PREDECESSOR'}
    assert operation_wip({**base,'operation_status':'COMPLETED'})['actionable'] is False
    assert operation_wip({**base,'operation_status':'CANCELLED'})['actionable'] is False


def test_naive_aware_utc_is_interpreted_in_site_zone_not_os_timezone():
    naive=datetime(2026,8,9,7,0)
    assert aware_utc(naive)==datetime(2026,8,9,0,0,tzinfo=timezone.utc)


def test_unexpected_failure_maps_to_500_without_leaking_exception():
    app=Flask(__name__)
    with app.app_context():
        response,status=api_error_response(RuntimeError('sensitive database detail'),logger_name=__name__)
        assert status==500
        assert response.get_json()['error']=='INTERNAL_ERROR'
        assert 'sensitive' not in response.get_json()['message']
