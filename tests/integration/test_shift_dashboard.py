from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')


def test_night_shift_keeps_after_midnight_session_in_previous_shift_date(db, api, seeded_factory):
    g = seeded_factory
    night = db.execute("SELECT id FROM work_shifts WHERE code='NIGHT'").fetchone()['id']
    start = datetime(2026, 8, 6, 23, 30, tzinfo=HCM)
    end = datetime(2026, 8, 7, 1, 15, tzinfo=HCM)
    row = db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
                      VALUES(%s,%s,%s,'docker-e2e','CLOSED',%s,%s,12,1,%s,%s) RETURNING id""",
                     (g['employee_id'], g['operation_id'], g['station_id'], start, end,
                      f"start-night-{g['suffix']}", f"finish-night-{g['suffix']}" )).fetchone()

    response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date=2026-08-06&shift_id={night}&limit=1000', timeout=10)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['context']['shift_date'] == '2026-08-06'
    assert body['context']['cross_midnight'] is True
    assert body['context']['range_start'].startswith('2026-08-06T18:00:00')
    assert body['context']['range_end'].startswith('2026-08-07T03:00:00')
    session_ids = {item['session_id'] for item in body['sessions']}
    assert row['id'] in session_ids


def test_day_shift_session_list_still_includes_same_calendar_date_night_session(db, api, seeded_factory):
    # "Session theo ngày" lists by calendar date, not by the requested
    # shift's own time window -- shift_id only selects which shift's WORK
    # windows are used for work_duration_seconds; it no longer excludes an
    # otherwise same-day session from the list. (Was
    # test_day_shift_does_not_include_night_session, asserting the opposite
    # -- that contract was the bug: see test_early_morning_session_before_
    # shift_anchor_is_listed_for_its_calendar_date below.)
    g = seeded_factory
    day = db.execute("SELECT id FROM work_shifts WHERE code='DAY'").fetchone()['id']
    start = datetime(2026, 8, 6, 18, 30, tzinfo=HCM)
    end = datetime(2026, 8, 6, 19, 0, tzinfo=HCM)
    row = db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
                      VALUES(%s,%s,%s,'docker-e2e','CLOSED',%s,%s,3,0,%s,%s) RETURNING id""",
                     (g['employee_id'], g['operation_id'], g['station_id'], start, end,
                      f"start-day-include-{g['suffix']}", f"finish-day-include-{g['suffix']}" )).fetchone()
    response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date=2026-08-06&shift_id={day}&limit=1000', timeout=10)
    assert response.status_code == 200, response.text
    assert row['id'] in {item['session_id'] for item in response.json()['sessions']}


def test_early_morning_session_before_shift_anchor_is_listed_for_its_calendar_date(db, api, seeded_factory):
    # Regression for the "Session theo ngày" bug: a session that starts
    # before the DAY shift's anchor_start (08:00 in this seed) must still
    # appear when listing sessions for that calendar date -- it must not
    # require started_at to be after the shift start.
    g = seeded_factory
    day = db.execute("SELECT id FROM work_shifts WHERE code='DAY'").fetchone()['id']
    start = datetime(2026, 8, 6, 6, 30, tzinfo=HCM)
    end = datetime(2026, 8, 6, 6, 50, tzinfo=HCM)
    row = db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
                      VALUES(%s,%s,%s,'docker-e2e','CLOSED',%s,%s,5,0,%s,%s) RETURNING id""",
                     (g['employee_id'], g['operation_id'], g['station_id'], start, end,
                      f"start-early-{g['suffix']}", f"finish-early-{g['suffix']}" )).fetchone()
    response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date=2026-08-06&shift_id={day}&limit=1000', timeout=10)
    assert response.status_code == 200, response.text
    assert row['id'] in {item['session_id'] for item in response.json()['sessions']}
