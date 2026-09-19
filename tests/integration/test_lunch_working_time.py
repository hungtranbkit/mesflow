"""Regression: full calendar-day visibility must never mean 24h WORK."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

pytestmark=pytest.mark.postgres
HCM=ZoneInfo("Asia/Ho_Chi_Minh")

@pytest.fixture
def lunch_1130(db):
    day=db.execute("SELECT id,anchor_start FROM work_shifts WHERE code='DAY'").fetchone()
    rows=db.execute("SELECT id,start_minute,end_minute FROM work_shift_intervals WHERE shift_id=%s",(day["id"],)).fetchall()
    try:
        db.execute("UPDATE work_shifts SET anchor_start='07:30' WHERE id=%s",(day["id"],))
        db.execute("UPDATE work_shift_intervals SET start_minute=450,end_minute=690 WHERE shift_id=%s AND interval_type='WORK' AND start_minute<720",(day["id"],))
        db.execute("UPDATE work_shift_intervals SET start_minute=690,end_minute=780 WHERE shift_id=%s AND interval_type='BREAK'",(day["id"],))
        yield
    finally:
        for row in rows:
            db.execute("UPDATE work_shift_intervals SET start_minute=%s,end_minute=%s WHERE id=%s",(row["start_minute"],row["end_minute"],row["id"]))
        db.execute("UPDATE work_shifts SET anchor_start=%s WHERE id=%s",(day["anchor_start"],day["id"]))

@pytest.mark.parametrize("start,end,expected", [("11:00","14:00",5400),("11:45","12:45",0),("06:30","06:50",0)])
def test_day_api_and_session_detail_use_real_work_windows(db,api,seeded_factory,lunch_1130,start,end,expected):
    g=seeded_factory
    at=lambda s:datetime.fromisoformat("2026-09-18T"+s).replace(tzinfo=HCM)
    row=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
      VALUES(%s,%s,%s,'lunch-regression','CLOSED',%s,%s,2,0,%s,%s) RETURNING id""",
      (g["employee_id"],g["operation_id"],g["station_id"],at(start),at(end),"lunch-start-"+g["suffix"],"lunch-end-"+g["suffix"])).fetchone()
    response=api.get(f"http://mesflow-test-api:8080/api/dashboard/day?date=2026-09-18&po_id={g['po_id']}",timeout=15)
    assert response.status_code==200,response.text
    body=response.json()
    item=next(s for s in body["sessions"] if s["session_id"]==row["id"])
    assert item["work_duration_seconds"]==expected
    assert item["duration_seconds"]==int((at(end)-at(start)).total_seconds())
    assert next(x for x in body["items"] if x["operation_id"]==g["operation_id"])["day_work_seconds"]==expected
    assert not any(x["interval_type"]=="WORK" and x["start_minute"]<780 and x["end_minute"]>690 for x in body["context"]["intervals"])
    response=api.get(f"http://mesflow-test-api:8080/api/session-management/{row['id']}",timeout=15)
    assert response.status_code==200,response.text
    assert response.json()["session"]["work_duration_seconds"]==expected
