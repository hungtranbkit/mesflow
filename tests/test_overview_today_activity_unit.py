"""Production Overview hotfix (2026-09-26, part 2): today's history + "Hôm nay"
metrics per Operation row.

Pure unit tests (no PostgreSQL): OPEN-wins merge, local-midnight window,
constant query count, and a static contract on the page. Real-database
behaviour: tests/integration/test_overview_today_activity.py."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from mesflow.core import working_calendar
from mesflow.db.repositories import analytics
from mesflow.db.repositories.analytics import _attach_today

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
HCM = ZoneInfo('Asia/Ho_Chi_Minh')


@pytest.fixture(autouse=True)
def _default_shifts(monkeypatch):
    monkeypatch.setattr(working_calendar, 'get_work_shifts',
                        lambda active_only=True: [dict(x) for x in working_calendar.DEFAULT_SHIFTS])


def _w(employee_id, name, **kw):
    return dict(employee_id=employee_id, employee_no=f'NV{employee_id:03d}', name=name, session_count=1,
                last_ended_at='2026-09-26T09:00:00+00:00', auto_closed=False, **kw)


def _today(**kw):
    base = dict(employee_count=2, session_count=3, open_session_count=0, good_qty=10, defect_qty=1, rework_qty=1,
                recorded_session_count=2, work_seconds=3600, productivity_percent=95.0, scored_session_count=2,
                standard_seconds_per_unit=60, last_ended_at='2026-09-26T09:00:00+00:00', date='2026-09-26')
    base.update(kw)
    return base


def test_closed_today_workers_show_as_stopped():
    row = {'operation_id': 10, 'active_worker_list': []}
    _attach_today(row, {10: _today(worker_list=[_w(7, 'An'), _w(8, 'Bình')])})
    assert row['today_state'] == 'STOPPED'
    assert [w['name'] for w in row['today_worker_list']] == ['An', 'Bình']
    assert row['today_worker_count'] == 2
    assert row['today_last_ended_at'] == '2026-09-26T09:00:00+00:00'
    assert row['today']['good_qty'] == 10 and 'worker_list' not in row['today']
    assert row['active_worker_list'] == []  # never touched


def test_open_worker_overrides_closed_today_entry():
    row = {'operation_id': 10, 'active_worker_list': [{'employee_id': 7, 'name': 'An'}]}
    _attach_today(row, {10: _today(open_session_count=1, worker_list=[_w(7, 'An'), _w(8, 'Bình')])})
    assert row['today_state'] == 'RUNNING'
    assert [w['employee_id'] for w in row['today_worker_list']] == [8]
    assert [w['employee_id'] for w in row['active_worker_list']] == [7]


def test_no_activity_today_is_idle():
    row = {'operation_id': 11, 'active_worker_list': []}
    _attach_today(row, {10: _today(worker_list=[_w(7, 'An')])})
    assert row['today'] is None and row['today_state'] == 'IDLE'
    assert row['today_worker_list'] == [] and row['today_worker_count'] == 0


@pytest.mark.parametrize('now_utc,expected_date', [
    (datetime(2026, 9, 26, 16, 59, 59, tzinfo=timezone.utc), '2026-09-26'),  # 23:59:59 local
    (datetime(2026, 9, 26, 17, 0, 0, tzinfo=timezone.utc), '2026-09-27'),    # 00:00:00 local
    (datetime(2026, 9, 25, 17, 0, 0, tzinfo=timezone.utc), '2026-09-26'),    # 00:00 local, UTC still 25th
])
def test_window_is_the_local_calendar_day(monkeypatch, now_utc, expected_date):
    seen = {}

    def fake_fetch_all(sql, params=()):
        seen['sql'], seen['params'] = sql, list(params)
        return [dict(operation_id=10, **{k: v for k, v in _today().items() if k != 'date'}, worker_list=None)]

    monkeypatch.setattr(analytics, 'fetch_all', fake_fetch_all)
    out = analytics.DashboardRepository().today_activity_by_operation(now_utc)
    day = datetime.fromisoformat(expected_date).date()
    start = datetime(day.year, day.month, day.day, tzinfo=HCM)
    # The last six params are: now (actual_seconds), day_end, now, day_start
    # (overlap filter), day_start, day_end (report_at window).
    tail = seen['params'][-6:]
    end = start + timedelta(days=1)
    assert tail == [now_utc, end, now_utc, start, start, end]
    assert out[10]['date'] == expected_date and out[10]['worker_list'] == []


def test_operation_overview_query_count_is_constant(monkeypatch):
    calls = []

    def ops(n):
        return [dict(operation_id=i, planned_quantity=100, done_qty=5, open_session_count=0,
                     operation_status='IN_PROGRESS') for i in range(1, n + 1)]

    def run(n):
        calls.clear()

        def fake_fetch_all(sql, params=()):
            calls.append(sql)
            if 'ws.id session_id' in sql:
                return []
            if 'day_sessions' in sql:
                return [dict(operation_id=1, **{k: v for k, v in _today().items() if k != 'date'},
                             worker_list=[_w(7, 'An')])]
            return ops(n)

        monkeypatch.setattr(analytics, 'fetch_all', fake_fetch_all)
        return analytics.DashboardRepository().operation_overview(5000)

    rows = run(2)
    assert len(calls) == 3  # operations + OPEN sessions + today rollup
    assert rows[0]['today_state'] == 'STOPPED' and rows[0]['today']['session_count'] == 3
    assert rows[1]['today_state'] == 'IDLE' and rows[1]['today'] is None
    run(60)
    assert len(calls) == 3  # never per row


def test_today_sql_and_page_contract():
    repo = (ROOT / 'app/mesflow/db/repositories/analytics.py').read_text(encoding='utf-8')
    page = (ROOT / 'app/mesflow/web/static/pages/overview.js').read_text(encoding='utf-8')
    body = repo.split('def today_activity_by_operation', 1)[1].split('def overview', 1)[0]
    assert "reportable_session_sql('ws')" in body
    assert '_calendar_day_context(business_date(now))' in body
    assert '_SESSION_COMPLETION_PERCENT_SQL' in body
    assert "HAVING COUNT(*) FILTER (WHERE status='OPEN')=0" in body
    # active_worker_list stays OPEN-only.
    active = repo.split('def active_workers_by_operation', 1)[1].split('def today_activity_by_operation', 1)[0]
    assert "ws.status='OPEN'" in active
    # OPEN wins on the page: the neutral line only renders without an active one.
    assert '${todayMetrics(x)}${activeWorkers(x)||todayWorkers(x)}</div>' in page
    assert "Đã dừng ${at}" in page and "'Đã làm hôm nay'" in page
    assert 'định mức × (Đạt + Lỗi) ÷ thời gian thực tế × 100%' in page
