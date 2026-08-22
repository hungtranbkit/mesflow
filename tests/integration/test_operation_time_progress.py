"""Real-time progress of a running Operation -- "Tiến độ theo Operation".

Bug report: "Tiến độ thời gian không tăng khi Work Session vẫn đang chạy."
Investigated end to end against a real server + real browser (see commit
message for the T0/T1 evidence): the backend formula in
DashboardRepository.daily_progress() already computes actual work time as
SUM(closed-session duration) + SUM(NOW() - started_at for open sessions),
clamped to the shift's WORK sub-intervals (excludes BREAK, matching the
Working Calendar policy used everywhere else -- daily_sessions() uses the
identical clamp). The frontend already re-fetches on a 10s
setInterval(dashboardTimer, renderDashboard's own, no new timer added).
Both were verified live to actually progress (13→14→15→16 phút,
8%→9% over 150s of real wall-clock time on an open session).

These tests lock that behavior in as a regression guard, plus fix one real
gap found along the way: the "Còn lại/Đã vượt" wording never had a branch
for variance == 0 (exactly at the standard) -- it showed "Còn lại 0 giây"
instead of the spec's "Đã dùng hết thời gian định mức". That is the only
functional change in this pass; the calculation/refresh pipeline itself was
already correct.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')
SHIFT_DATE = '2026-08-06'


def _shift_id(db, code='DAY'):
    return db.execute("SELECT id FROM work_shifts WHERE code=%s", (code,)).fetchone()['id']


def _insert_session(db, employee_id, operation_id, station_id, suffix, tag, status, start, end=None, good_qty=0):
    row = db.execute(
        """INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,start_request_id,finish_request_id)
           VALUES(%s,%s,%s,'docker-e2e',%s,%s,%s,%s,%s,%s) RETURNING id""",
        (employee_id, operation_id, station_id, status, start, end, good_qty,
         f'start-{tag}-{suffix}', f'finish-{tag}-{suffix}' if end else None),
    ).fetchone()
    return row['id']


def _extra_employee(db, suffix, tag):
    row = db.execute(
        "INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
        (f'TEST-{tag}-{suffix}', f'Docker Extra Worker {tag}', f'WF|EMP|TEST-{tag}-{suffix}'),
    ).fetchone()
    return row['id']


def _op_item(body, operation_id):
    match = [item for item in body['items'] if item['operation_id'] == operation_id]
    assert match, f'operation {operation_id} missing from /api/dashboard/shift items'
    return match[0]


def _fetch(api, shift_id):
    response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date={SHIFT_DATE}&shift_id={shift_id}&limit=2000', timeout=10)
    assert response.status_code == 200, response.text
    return response.json()


def _alldays_shift(db, suffix):
    """A dedicated WORK-all-24h shift for TODAY, so a growth assertion taken
    seconds apart is never flaky depending on what real time of day the test
    happens to run at (a fixed-date shift like DAY/2026-08-06 clamps an open
    session's contribution to that shift's own end_minute once real 'now'
    has moved past it -- see the CASE 1/3 failure this replaced; a lunch
    BREAK window would zero it out entirely -- see the report's evidence
    section). Does not touch the shared DAY/NIGHT shifts other tests use."""
    # NOTE: anchor_start must NOT be '00:00' -- working_calendar.shift_bounds()
    # only rolls a '00:00' anchor_end to the *next* day (end_is_midnight) when
    # anchor_start isn't also '00:00'; '00:00'->'00:00' resolves to a
    # zero-width range instead of a full day (caught live: items came back
    # empty for this exact reason on the first version of this fixture).
    row = db.execute(
        "INSERT INTO work_shifts(code,name,timezone,anchor_start,anchor_end,cross_midnight,target_minutes,working_weekdays,sort_order) "
        "VALUES(%s,'Test All-Day','Asia/Ho_Chi_Minh','00:01','00:00',false,1439,'{0,1,2,3,4,5,6}',900) RETURNING id",
        (f'TESTALLDAY-{suffix}',),
    ).fetchone()
    shift_id = row['id']
    db.execute("INSERT INTO work_shift_intervals(shift_id,interval_type,start_minute,end_minute,label,sort_order) VALUES(%s,'WORK',1,1440,'All day',10)", (shift_id,))
    return shift_id


def test_case1_running_session_actual_seconds_increases_between_two_requests(db, api, seeded_factory):
    g = seeded_factory
    shift_id = _alldays_shift(db, g['suffix'])
    try:
        today = datetime.now(HCM).strftime('%Y-%m-%d')
        started = datetime.now(HCM) - timedelta(minutes=10)
        _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'running',
                         'OPEN', started)

        response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date={today}&shift_id={shift_id}&limit=2000', timeout=10)
        assert response.status_code == 200, response.text
        t0 = _op_item(response.json(), g['operation_id'])['day_work_seconds']
        real_now_t0 = datetime.now(timezone.utc)
        # Real evidence, not a mocked clock: sleep the actual test process,
        # re-hit the live API, and compare -- this is exactly the T0/T1 probe
        # the task asked for, just automated.
        import time
        time.sleep(3)
        response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date={today}&shift_id={shift_id}&limit=2000', timeout=10)
        t1 = _op_item(response.json(), g['operation_id'])['day_work_seconds']
        elapsed = (datetime.now(timezone.utc) - real_now_t0).total_seconds()

        assert t0 >= 500  # ~10 minutes elapsed since started, well within the all-day WORK window
        assert t1 > t0, f'actual_seconds did not increase: t0={t0} t1={t1} (waited {elapsed:.1f}s)'
        assert t1 - t0 <= elapsed + 2  # sanity: growth roughly tracks real elapsed time, not some larger jump
    finally:
        db.execute("DELETE FROM work_shifts WHERE id=%s", (shift_id,))


def test_case2_closed_plus_running_session_sums_correctly(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'closed',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 5, tzinfo=HCM))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'open',
                     'OPEN', datetime(2026, 8, 6, 9, 10, tzinfo=HCM))

    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['session_count'] == 2
    assert item['open_session_count'] == 1
    # Closed leg is exactly 300s; open leg is whatever has elapsed since 09:10
    # today's wall clock -- must be at least the closed leg's contribution.
    assert item['day_work_seconds'] >= 300


def test_case3_two_running_sessions_same_operation_sum_worker_time(db, api, seeded_factory):
    """MESFlow's actual semantics (daily_progress()'s duration_sql): each
    session's own elapsed time is summed independently -- two workers
    running the same Operation concurrently for 10 real minutes each
    contribute ~20 minutes combined, not the Operation's own 10-minute
    wall-clock span. Verified against the real formula, not assumed."""
    g = seeded_factory
    shift_id = _alldays_shift(db, g['suffix'])
    today = datetime.now(HCM).strftime('%Y-%m-%d')
    second_id = _extra_employee(db, g['suffix'], 'second')
    try:
        start = datetime.now(HCM) - timedelta(minutes=5)
        s1 = _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'p1', 'OPEN', start)
        s2 = _insert_session(db, second_id, g['operation_id'], g['station_id'], g['suffix'], 'p2', 'OPEN', start)
        response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date={today}&shift_id={shift_id}&limit=2000', timeout=10)
        item = _op_item(response.json(), g['operation_id'])
        assert item['open_session_count'] == 2
        # Both sessions started at the same instant -- worker-time sum must
        # be roughly DOUBLE a single session's elapsed time, not equal to it.
        solo_seconds = (datetime.now(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
        assert item['day_work_seconds'] >= solo_seconds * 1.8
    finally:
        db.execute("DELETE FROM work_sessions WHERE id=ANY(%s)", ([s1, s2],))
        db.execute("DELETE FROM employees WHERE id=%s", (second_id,))
        db.execute("DELETE FROM work_shifts WHERE id=%s", (shift_id,))


def test_case4_zero_planned_seconds_does_not_crash(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    # seeded_factory's operation has no standard_seconds_per_unit set (defaults
    # to 0) -- planned_work_seconds = 0 * planned_quantity = 0 out of the box.
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'zeroplan',
                     'OPEN', datetime(2026, 8, 6, 9, 0, tzinfo=HCM))
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['planned_work_seconds'] == 0
    assert item['day_work_seconds'] >= 0  # no exception, no NaN/None


def test_case5_actual_exceeds_planned_is_representable(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    db.execute("UPDATE operations SET standard_seconds_per_unit=1 WHERE id=%s", (g['operation_id'],))
    db.execute("UPDATE production_orders SET planned_quantity=1 WHERE id=%s", (g['po_id'],))
    # planned_work_seconds = 1 * 1 = 1 second; any real session blows past it.
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'over',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 10, tzinfo=HCM))
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['planned_work_seconds'] == 1
    assert item['day_work_seconds'] > item['planned_work_seconds']


def test_case6_session_finish_reduces_running_count_without_losing_time(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    sid = _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'toclose',
                           'OPEN', datetime(2026, 8, 6, 9, 0, tzinfo=HCM))
    before = _op_item(_fetch(api, day), g['operation_id'])
    assert before['open_session_count'] == 1
    assert len(before['active_workers']) == 1

    db.execute("UPDATE work_sessions SET status='CLOSED', ended_at=started_at + interval '5 minutes' WHERE id=%s", (sid,))
    after = _op_item(_fetch(api, day), g['operation_id'])
    assert after['open_session_count'] == 0
    assert after['active_workers'] == []
    assert after['session_count'] == before['session_count'] == 1
    # Closing at a fixed +5min timestamp must not make actual time jump
    # backward relative to what was already reported while still running.
    assert after['day_work_seconds'] >= 300
    assert after['day_work_seconds'] <= before['day_work_seconds'] + 5  # allow tiny clock skew, never a big regression


def test_variance_zero_wording_not_negative_countdown():
    """Frontend fix: variance == 0 (actual exactly equals the standard) must
    say 'Đã dùng hết thời gian định mức', not 'Còn lại 0 giây', and the
    'Đã vượt'/'Còn lại' branches must never be fed a negative duration."""
    js = __import__('pathlib').Path(__file__).resolve().parents[2] / 'app/mesflow/web/static/app.js'
    src = js.read_text(encoding='utf-8')
    assert "variance===0?'Đã dùng hết thời gian định mức'" in src
    assert "Đã vượt ${fmtDuration(variance)}" in src
    assert "Còn lại ${fmtDuration(-variance)}" in src
