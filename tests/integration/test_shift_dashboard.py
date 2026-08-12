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


def test_day_shift_does_not_include_night_session(db, api, seeded_factory):
    g = seeded_factory
    day = db.execute("SELECT id FROM work_shifts WHERE code='DAY'").fetchone()['id']
    start = datetime(2026, 8, 6, 18, 30, tzinfo=HCM)
    end = datetime(2026, 8, 6, 19, 0, tzinfo=HCM)
    row = db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
                      VALUES(%s,%s,%s,'docker-e2e','CLOSED',%s,%s,3,0,%s,%s) RETURNING id""",
                     (g['employee_id'], g['operation_id'], g['station_id'], start, end,
                      f"start-day-exclude-{g['suffix']}", f"finish-day-exclude-{g['suffix']}" )).fetchone()
    response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date=2026-08-06&shift_id={day}&limit=1000', timeout=10)
    assert response.status_code == 200, response.text
    assert row['id'] not in {item['session_id'] for item in response.json()['sessions']}
