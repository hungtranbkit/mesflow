"""Báo cáo năng suất nhân viên -- GET /api/reports/employee-productivity(/<id>).

Business rule (task spec, revised 2026-08-22): this report is completed
Work Session ONLY. It does not care about running sessions, which
Operation an employee is currently on, running_sessions, active_workers,
or any realtime state.

  completed session = work_sessions.status='CLOSED' AND ended_at IS NOT NULL
  (application-enforced status domain is just {'OPEN','CLOSED'} -- see
  WorkSessionRepository -- so CLOSED is already the complete "hoàn thành
  hợp lệ" set; there is no CANCELLED/VOID/INVALID work_session status in
  this schema to additionally exclude)

  employee productivity = AVG(session_completion_percent) over that
  employee's completed sessions in the date range -- a running session's
  implied rate must never enter this average, at any %, ever.

  session_completion_percent is not a new metric: it reuses this
  codebase's existing "expected time at standard rate vs actual time"
  definition (ReportRepository.employee_performance()'s efficiency_percent
  = expected_seconds/actual_seconds*100), just applied per session:
    expected_seconds = operations.standard_seconds_per_unit * (good_qty+defect_qty)
    actual_seconds   = EXTRACT(EPOCH FROM (ended_at-started_at))
    completion_percent = expected_seconds/actual_seconds*100 -- NULL (not 0)
    whenever either side is missing/zero.

  Date filter is on ended_at (business date, Asia/Ho_Chi_Minh), not
  started_at -- a session that starts one day and ends the next files
  under the day it ENDED.
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
    assert row['completed_sessions'] == 2
    assert row['completed_valid_sessions'] == 2
    assert 'running_sessions' not in row
    assert row['productivity_percent'] == 60.0  # (50+70)/2, exactly the task's own example

    detail = _fetch_detail(api, g['employee_id'], '2026-08-06', '2026-08-06')
    assert detail['productivity_percent'] == 60.0
    assert sorted(s['completion_percent'] for s in detail['sessions']) == [50.0, 70.0]


def test_task_case_employee_a_50_70_running_120_excluded_entirely(db, api, seeded_factory):
    """Task's own CASE: closed=50%, closed=70%, running(120%-implied) must be
    completely ignored -- not just excluded from the average, but excluded
    from the query itself (never appears anywhere in the response)."""
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's2',
                     'CLOSED', datetime(2026, 8, 6, 10, 0, tzinfo=HCM), datetime(2026, 8, 6, 10, 20, tzinfo=HCM), good_qty=14)
    # running session whose implied rate would be 120% if it were ever scored -- it must not be.
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'running',
                     'OPEN', datetime(2026, 8, 6, 11, 0, tzinfo=HCM), good_qty=10)

    body = _fetch_summary(api, '2026-08-06', '2026-08-06')
    row = _one(body, g['employee_id'])
    assert row['completed_sessions'] == 2  # the running session is not counted at all
    assert row['productivity_percent'] == 60.0

    detail = _fetch_detail(api, g['employee_id'], '2026-08-06', '2026-08-06')
    assert detail['productivity_percent'] == 60.0
    assert len(detail['sessions']) == 2  # the running session never appears in the session list either
    assert all(s['status'] == 'CLOSED' for s in detail['sessions'])


def test_task_case_employee_b_only_running_sessions_no_score_not_zero(db, api, seeded_factory):
    """Task's own CASE: an employee with ONLY running sessions must not even
    appear with a 0% score -- they simply have no productivity data."""
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'running',
                     'OPEN', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), good_qty=10)

    body = _fetch_summary(api, '2026-08-06', '2026-08-06')
    assert not any(x['employee_id'] == g['employee_id'] for x in body['employees']), \
        'an employee with only a running session must not appear at all (never as 0%)'


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
    assert row['completed_sessions'] == 3
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
    assert row['completed_sessions'] == 1
    assert row['productivity_percent'] == 80.0  # the running session must not pull this off 80%


def test_employee_d_missing_denominator_not_zero_not_crash(db, api, seeded_factory):
    g = seeded_factory
    # standard_seconds_per_unit left at its default (0/unconfigured) -> expected_seconds=0 for every session.
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'nodata',
                     'CLOSED', datetime(2026, 8, 9, 9, 0, tzinfo=HCM), datetime(2026, 8, 9, 9, 10, tzinfo=HCM), good_qty=5)

    body = _fetch_summary(api, '2026-08-09', '2026-08-09')
    row = _one(body, g['employee_id'])
    assert row['completed_sessions'] == 1  # counted, not silently dropped
    assert row['completed_valid_sessions'] == 0
    assert row['completed_invalid_sessions'] == 1
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
    assert row['completed_sessions'] == 1  # the 08-15 session must not leak into an 08-10-only window


def test_timezone_boundary_late_evening_session_stays_in_its_hcm_calendar_day(db, api, seeded_factory):
    """A session that both starts AND ends at 23:5x/23:5x the same HCM
    calendar date must count for THAT date, not roll into the next UTC day
    (UTC is 7h behind HCM, so a naive UTC ::date cast would misfile this --
    exactly what business_date_start_utc() is used to avoid)."""
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    start = datetime(2026, 8, 11, 23, 50, tzinfo=HCM)
    end = datetime(2026, 8, 11, 23, 58, tzinfo=HCM)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'late',
                     'CLOSED', start, end, good_qty=10)

    same_day = _fetch_summary(api, '2026-08-11', '2026-08-11')
    assert any(x['employee_id'] == g['employee_id'] for x in same_day['employees']), 'session must appear on 2026-08-11 (its HCM calendar date)'
    next_day_only = _fetch_summary(api, '2026-08-12', '2026-08-12')
    assert not any(x['employee_id'] == g['employee_id'] for x in next_day_only['employees']), 'session must not also leak into 2026-08-12'


def test_ended_at_not_started_at_decides_the_reporting_date(db, api, seeded_factory):
    """Task section 6's explicit concern: a session that STARTS the day
    before but ENDS today must file under TODAY (its ended_at date), not
    under the day it started. This is the exact scenario the switch from
    started_at to ended_at as the report's date field exists to fix."""
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    # Starts 2026-08-13 23:50, ends 2026-08-14 00:10 -- crosses midnight HCM.
    start = datetime(2026, 8, 13, 23, 50, tzinfo=HCM)
    end = datetime(2026, 8, 14, 0, 10, tzinfo=HCM)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'crossmidnight',
                     'CLOSED', start, end, good_qty=10)

    ended_day = _fetch_summary(api, '2026-08-14', '2026-08-14')
    assert any(x['employee_id'] == g['employee_id'] for x in ended_day['employees']), \
        'a session ending 2026-08-14 must count for 2026-08-14 even though it started the day before'
    started_day_only = _fetch_summary(api, '2026-08-13', '2026-08-13')
    assert not any(x['employee_id'] == g['employee_id'] for x in started_day_only['employees']), \
        'the session must NOT file under its start date any more -- only its end date'


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


def test_response_never_exposes_running_or_active_worker_fields(db, api, seeded_factory):
    """Section 8: the API must not return running_sessions/active_workers
    (or an equivalent) -- for either the per-employee rows or the summary."""
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'done',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'running',
                     'OPEN', datetime(2026, 8, 6, 11, 0, tzinfo=HCM), good_qty=1)

    body = _fetch_summary(api, '2026-08-06', '2026-08-06')
    forbidden = {'running_sessions', 'active_workers', 'active_employee_count', 'current_operation'}
    row = _one(body, g['employee_id'])
    assert not (forbidden & row.keys()), f'forbidden realtime fields leaked into employee row: {forbidden & row.keys()}'
    assert not (forbidden & body['summary'].keys()), f'forbidden realtime fields leaked into summary: {forbidden & body["summary"].keys()}'


def test_empty_state_no_sessions_in_range(api):
    body = _fetch_summary(api, '2020-01-01', '2020-01-02')
    assert body['employees'] == []
    assert body['summary']['employee_count'] == 0
    assert body['summary']['avg_employee_productivity_percent'] is None


def test_detail_endpoint_404_for_unknown_employee(api):
    response = api.get('http://mesflow-test-api:8080/api/reports/employee-productivity/99999999?from=2026-08-01&to=2026-08-22', timeout=10)
    assert response.status_code == 404


def test_endpoint_requires_login():
    import requests
    response = requests.get('http://mesflow-test-api:8080/api/reports/employee-productivity?from=2026-08-01&to=2026-08-22', timeout=10)
    assert response.status_code == 401
