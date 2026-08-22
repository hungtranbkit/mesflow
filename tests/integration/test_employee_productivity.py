"""Báo cáo năng suất nhân viên -- GET /api/reports/employee-productivity(/<id>).

Business rule (task spec): employee productivity = simple average of each
CLOSED session's own completion % in the date range -- NOT
sum(good_qty)/sum(planned) for the employee. Session completion % is not a
new metric: it reuses this codebase's existing "expected time at standard
rate vs actual time" definition (ReportRepository.employee_performance()'s
efficiency_percent = expected_seconds/actual_seconds*100, and
KPIRepository.operations()'s completion_percent concept), just applied per
session instead of summed across an Operation first:
  expected_seconds = operations.standard_seconds_per_unit * (good_qty+defect_qty)
  actual_seconds   = EXTRACT(EPOCH FROM (ended_at-started_at))
  completion_percent = expected_seconds/actual_seconds*100 -- NULL (not 0)
  whenever either side is missing/zero, or the session is still OPEN.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')


def _insert_session(db, employee_id, operation_id, station_id, suffix, tag, status, start, end=None, good_qty=0, defect_qty=0):
    row = db.execute(
        """INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
           VALUES(%s,%s,%s,'docker-e2e',%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (employee_id, operation_id, station_id, status, start, end, good_qty, defect_qty,
         f'start-{tag}-{suffix}', f'finish-{tag}-{suffix}' if end else None),
    ).fetchone()
    return row['id']


def _fetch_summary(api, date_from, date_to, **extra):
    params = f'from={date_from}&to={date_to}' + ''.join(f'&{k}={v}' for k, v in extra.items())
    response = api.get(f'http://mesflow-test-api:8080/api/reports/employee-productivity?{params}', timeout=10)
    assert response.status_code == 200, response.text
    return response.json()


def _fetch_detail(api, employee_id, date_from, date_to):
    response = api.get(f'http://mesflow-test-api:8080/api/reports/employee-productivity/{employee_id}?from={date_from}&to={date_to}', timeout=10)
    assert response.status_code == 200, response.text
    return response.json()


def _one(body, employee_id):
    match = [x for x in body['employees'] if x['employee_id'] == employee_id]
    assert match, f'employee {employee_id} missing from report: {body["employees"]}'
    return match[0]


def test_employee_a_two_sessions_50_and_70_average_60(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    # session1: standard=600s (10 good x 60s), actual=1200s -> 50%
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)
    # session2: standard=840s (14 good x 60s), actual=1200s -> 70%
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's2',
                     'CLOSED', datetime(2026, 8, 6, 10, 0, tzinfo=HCM), datetime(2026, 8, 6, 10, 20, tzinfo=HCM), good_qty=14)

    body = _fetch_summary(api, '2026-08-06', '2026-08-06')
    row = _one(body, g['employee_id'])
    assert row['completed_valid_sessions'] == 2
    assert row['running_sessions'] == 0
    assert row['productivity_percent'] == 60.0  # (50+70)/2, exactly the task's own example

    detail = _fetch_detail(api, g['employee_id'], '2026-08-06', '2026-08-06')
    assert detail['productivity_percent'] == 60.0
    assert sorted(s['completion_percent'] for s in detail['sessions']) == [50.0, 70.0]


def test_employee_b_100_100_120_average_106_67(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    for tag, minutes, good in [('s1', 10, 10), ('s2', 10, 10)]:  # 600s standard / 600s actual = 100%
        start = datetime(2026, 8, 7, 9 + int(tag[1]), 0, tzinfo=HCM)
        _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], tag,
                         'CLOSED', start, start.replace(minute=minutes), good_qty=good)
    # session3: 600s standard (10 good), 500s actual -> 120%
    start3 = datetime(2026, 8, 7, 12, 0, tzinfo=HCM)
    db.execute(
        """INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,start_request_id,finish_request_id)
           VALUES(%s,%s,%s,'docker-e2e','CLOSED',%s,%s,10,%s,%s)""",
        (g['employee_id'], g['operation_id'], g['station_id'], start3,
         start3.replace(minute=8, second=20), f"start-s3-{g['suffix']}", f"finish-s3-{g['suffix']}"),
    )

    body = _fetch_summary(api, '2026-08-07', '2026-08-07')
    row = _one(body, g['employee_id'])
    assert row['completed_valid_sessions'] == 3
    assert row['productivity_percent'] == pytest.approx(106.67, abs=0.01)
    # Section 5: no clamp at 100% even though one session is 120%.
    detail = _fetch_detail(api, g['employee_id'], '2026-08-07', '2026-08-07')
    assert 120.0 in [s['completion_percent'] for s in detail['sessions']]


def test_employee_c_completed_80_plus_running_excluded_from_average(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    # completed: 480s standard (8 good), 600s actual -> 80%
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'done',
                     'CLOSED', datetime(2026, 8, 8, 9, 0, tzinfo=HCM), datetime(2026, 8, 8, 9, 10, tzinfo=HCM), good_qty=8)
    # running: no ended_at -- must never enter the main average regardless of its current implied rate.
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'running',
                     'OPEN', datetime(2026, 8, 8, 10, 0, tzinfo=HCM), good_qty=4)

    body = _fetch_summary(api, '2026-08-08', '2026-08-08')
    row = _one(body, g['employee_id'])
    assert row['completed_valid_sessions'] == 1
    assert row['running_sessions'] == 1
    assert row['productivity_percent'] == 80.0  # the running session must not pull this off 80%


def test_employee_d_missing_denominator_not_zero_not_crash(db, api, seeded_factory):
    g = seeded_factory
    # standard_seconds_per_unit left at its default (0/unconfigured) -> expected_seconds=0 for every session.
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'nodata',
                     'CLOSED', datetime(2026, 8, 9, 9, 0, tzinfo=HCM), datetime(2026, 8, 9, 9, 10, tzinfo=HCM), good_qty=5)

    body = _fetch_summary(api, '2026-08-09', '2026-08-09')
    row = _one(body, g['employee_id'])
    assert row['completed_valid_sessions'] == 0
    assert row['completed_invalid_sessions'] == 1  # counted, not silently dropped
    assert row['productivity_percent'] is None  # NOT 0 -- "Không đủ dữ liệu" in the UI

    detail = _fetch_detail(api, g['employee_id'], '2026-08-09', '2026-08-09')
    assert detail['productivity_percent'] is None
    assert detail['sessions'][0]['completion_percent'] is None


def test_date_range_excludes_sessions_outside_window(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'inside',
                     'CLOSED', datetime(2026, 8, 10, 9, 0, tzinfo=HCM), datetime(2026, 8, 10, 9, 10, tzinfo=HCM), good_qty=10)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'outside',
                     'CLOSED', datetime(2026, 8, 15, 9, 0, tzinfo=HCM), datetime(2026, 8, 15, 9, 10, tzinfo=HCM), good_qty=10)

    body = _fetch_summary(api, '2026-08-10', '2026-08-10')
    row = _one(body, g['employee_id'])
    assert row['completed_valid_sessions'] == 1  # the 08-15 session must not leak into an 08-10-only window


def test_timezone_boundary_late_evening_session_stays_in_its_hcm_calendar_day(db, api, seeded_factory):
    """A session at 23:50 Asia/Ho_Chi_Minh must count for THAT calendar date,
    not roll into the next UTC day (UTC is 7h behind HCM, so a naive UTC
    ::date cast would misfile this -- exactly what business_date_start_utc()
    is used to avoid)."""
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    start = datetime(2026, 8, 11, 23, 50, tzinfo=HCM)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'late',
                     'CLOSED', start, datetime(2026, 8, 12, 0, 0, tzinfo=HCM), good_qty=10)

    same_day = _fetch_summary(api, '2026-08-11', '2026-08-11')
    assert any(x['employee_id'] == g['employee_id'] for x in same_day['employees']), 'session must appear on 2026-08-11 (its HCM calendar date)'
    next_day_only = _fetch_summary(api, '2026-08-12', '2026-08-12')
    assert not any(x['employee_id'] == g['employee_id'] for x in next_day_only['employees']), 'session must not also leak into 2026-08-12'


def test_multiple_employees_ranked_descending_by_productivity(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    second = db.execute(
        "INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
        (f"TEST-second-{g['suffix']}", 'Docker Second Worker', f"WF|EMP|TEST-second-{g['suffix']}"),
    ).fetchone()['id']
    try:
        # g's employee: 600s standard (10 good) / 1200s actual -> 50%.
        _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'low',
                         'CLOSED', datetime(2026, 8, 13, 9, 0, tzinfo=HCM), datetime(2026, 8, 13, 9, 20, tzinfo=HCM), good_qty=10)
        # second employee: 540s standard (9 good) / 600s actual -> 90%.
        _insert_session(db, second, g['operation_id'], g['station_id'], g['suffix'], 'high',
                         'CLOSED', datetime(2026, 8, 13, 10, 0, tzinfo=HCM), datetime(2026, 8, 13, 10, 10, tzinfo=HCM), good_qty=9)

        body = _fetch_summary(api, '2026-08-13', '2026-08-13')
        ids_in_order = [x['employee_id'] for x in body['employees'] if x['employee_id'] in (g['employee_id'], second)]
        assert ids_in_order == [second, g['employee_id']]  # higher productivity first
        assert body['summary']['employee_count'] >= 2
        assert body['summary']['avg_employee_productivity_percent'] == pytest.approx((50.0 + 90.0) / 2, abs=0.01)
    finally:
        db.execute("DELETE FROM work_sessions WHERE employee_id=%s", (second,))
        db.execute("DELETE FROM employees WHERE id=%s", (second,))


def test_empty_state_no_sessions_in_range(api):
    body = _fetch_summary(api, '2020-01-01', '2020-01-02')
    assert body['employees'] == []
    assert body['summary']['employee_count'] == 0
    assert body['summary']['avg_employee_productivity_percent'] is None
    assert body['summary']['top_employee'] is None


def test_detail_endpoint_404_for_unknown_employee(api):
    response = api.get('http://mesflow-test-api:8080/api/reports/employee-productivity/99999999?from=2026-08-01&to=2026-08-22', timeout=10)
    assert response.status_code == 404


def test_endpoint_requires_login():
    import requests
    response = requests.get('http://mesflow-test-api:8080/api/reports/employee-productivity?from=2026-08-01&to=2026-08-22', timeout=10)
    assert response.status_code == 401
