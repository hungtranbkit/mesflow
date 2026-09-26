"""Production Overview hotfix (2026-09-26, part 2): today's worker history and
"Hôm nay" metrics per Operation, real PostgreSQL.

Pinned clock (2026-08-06 15:00 Asia/Ho_Chi_Minh) through
today_activity_by_operation(now=...): closed and auto-closed sessions stay
visible until 23:59:59 local and disappear at 00:00, yesterday never counts,
OPEN overrides the closed-today entry, qty/session/employee/time/productivity
match the Dashboard formulas. Plus the live /api/dashboard/overview contract
(active_worker_list still OPEN-only)."""
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from conftest import BASE_URL
from mesflow.core.working_calendar import working_intervals_between
from mesflow.db.repositories.analytics import DashboardRepository, _attach_today

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')


def L(day, hour, minute=0, second=0):
    return datetime(2026, 8, day, hour, minute, second, tzinfo=HCM)


NOW = L(6, 15)


def _insert(db, employee_id, operation_id, status, start, end=None, good=0, defect=0, rework=0,
            closed_by_system=False, quantity_confirmed=True):
    tag = uuid.uuid4().hex
    return db.execute(
        """INSERT INTO work_sessions(employee_id,operation_id,device_uuid,status,started_at,ended_at,
               good_qty,defect_qty,rework_qty,closed_by_system,quantity_confirmed,start_request_id,finish_request_id)
           VALUES(%s,%s,'docker-e2e',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (employee_id, operation_id, status, start, end, good, defect, rework, closed_by_system,
         quantity_confirmed, f'ov-today-start-{tag}', f'ov-today-finish-{tag}' if end else None)).fetchone()['id']


@pytest.fixture
def graph(db, seeded_factory):
    g = dict(seeded_factory)
    s = g['suffix']
    extra = []
    with db.cursor() as cur:
        for i in (2, 3):
            cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) "
                        "VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                        (f'TEST{i}-{s}', f'Worker {i} {s}', f'WF|EMP|OVT{i}-{s}'))
            extra.append(cur.fetchone()['id'])
        cur.execute("UPDATE operations SET standard_seconds_per_unit=300 WHERE id=%s", (g['operation_id'],))
    g['employee2_id'], g['employee3_id'] = extra
    yield g
    with db.cursor() as cur:
        for emp in extra:
            cur.execute("DELETE FROM work_sessions WHERE employee_id=%s", (emp,))
            cur.execute("DELETE FROM employees WHERE id=%s", (emp,))


def _board(now):
    repo = DashboardRepository()
    return repo, repo.today_activity_by_operation(now)


def test_today_history_and_metrics_on_the_local_calendar_day(db, graph):
    g = graph
    op, e1, e2, e3 = g['operation_id'], g['employee_id'], g['employee2_id'], g['employee3_id']
    # Yesterday: closed 23:30 local -> never part of today.
    _insert(db, e1, op, 'CLOSED', L(5, 22), L(5, 23, 30), good=50)
    # Today: e1 closed by hand, 12 SP in exactly the standard time -> 100 %.
    _insert(db, e1, op, 'CLOSED', L(6, 8), L(6, 9), good=10, defect=2, rework=1)
    # Today: e2 auto-closed at shift end with nothing entered -> not scored.
    _insert(db, e2, op, 'CLOSED', L(6, 13), L(6, 14), closed_by_system=True, quantity_confirmed=False)
    # Today: e3 closed earlier (5 SP in 30 min -> 83.3 %) and is OPEN again now.
    _insert(db, e3, op, 'CLOSED', L(6, 10), L(6, 10, 30), good=5)
    _insert(db, e3, op, 'OPEN', L(6, 14, 30))

    _, today = _board(NOW)
    t = today[op]
    assert t['date'] == '2026-08-06'
    assert t['employee_count'] == 3 and t['session_count'] == 4 and t['open_session_count'] == 1
    assert (t['good_qty'], t['defect_qty'], t['rework_qty']) == (15, 2, 1)
    assert t['recorded_session_count'] == 2  # the auto-closed 0/0 is not "recorded"
    assert t['scored_session_count'] == 2
    assert t['productivity_percent'] == pytest.approx(round((100 + 1500 / 1800 * 100) / 2, 1))
    assert t['standard_seconds_per_unit'] == 300
    expected = sum((b - a).total_seconds() for s, e in [(L(6, 8), L(6, 9)), (L(6, 13), L(6, 14)),
                                                        (L(6, 10), L(6, 10, 30)), (L(6, 14, 30), NOW)]
                   for a, b in working_intervals_between(s, e))
    assert t['work_seconds'] == int(expected) and 0 < t['work_seconds'] <= 3 * 3600 + 1800
    # Closed-today history: most recent first, OPEN employee excluded in SQL.
    assert [w['employee_id'] for w in t['worker_list']] == [e2, e1]
    assert t['worker_list'][0]['auto_closed'] is True and t['worker_list'][1]['auto_closed'] is False

    # OPEN wins on the row; active_worker_list stays OPEN-only.
    repo = DashboardRepository()
    active = repo.active_workers_by_operation().get(op, [])
    assert [w['employee_id'] for w in active] == [e3]
    row = {'operation_id': op, 'active_worker_list': active}
    _attach_today(row, today)
    assert row['today_state'] == 'RUNNING'
    assert {w['employee_id'] for w in row['today_worker_list']} == {e1, e2}

    # Close e3: the row turns neutral "Đã dừng" with all three names.
    db.execute("UPDATE work_sessions SET status='CLOSED',ended_at=%s WHERE employee_id=%s AND status='OPEN'",
               (L(6, 14, 50), e3))
    _, today = _board(NOW)
    row = {'operation_id': op, 'active_worker_list': repo.active_workers_by_operation().get(op, [])}
    _attach_today(row, today)
    assert row['active_worker_list'] == []
    assert row['today_state'] == 'STOPPED'
    assert [w['employee_id'] for w in row['today_worker_list']] == [e3, e2, e1]
    assert datetime.fromisoformat(str(row['today_last_ended_at'])) == L(6, 14, 50)

    # Still visible at 23:59:59 local ...
    _, today = _board(L(6, 23, 59, 59))
    assert today[op]['session_count'] == 4 and len(today[op]['worker_list']) == 3
    # ... and gone at 00:00 local (17:00 UTC), with yesterday's numbers.
    midnight = L(7, 0).astimezone(timezone.utc)
    _, today = _board(midnight)
    assert op not in today
    # The previous day (seen at 23:45 local) only has its own 22:00-23:30 session.
    _, today = _board(L(5, 23, 45))
    assert today[op]['good_qty'] == 50 and [w['employee_id'] for w in today[op]['worker_list']] == [e1]


def test_overview_api_exposes_today_fields(api, db, graph):
    g = graph
    op, e1, e2 = g['operation_id'], g['employee_id'], g['employee2_id']
    now = datetime.now(timezone.utc)
    midnight = datetime.now(HCM).replace(hour=0, minute=0, second=0, microsecond=0)
    start = max(midnight + timedelta(seconds=1), now - timedelta(minutes=20))
    _insert(db, e1, op, 'CLOSED', start, start + (now - start) / 2, good=3, defect=1)

    def row():
        r = api.get(f'{BASE_URL}/api/dashboard/overview?limit=5000', timeout=30)
        assert r.status_code == 200, r.text
        (x,) = [x for x in r.json()['operations'] if x['operation_id'] == op]
        return x

    x = row()
    assert x['active_worker_list'] == [] and x['active_worker_count'] == 0
    assert x['today_state'] == 'STOPPED'
    assert [w['employee_id'] for w in x['today_worker_list']] == [e1] and x['today_worker_count'] == 1
    assert x['today']['session_count'] == 1 and x['today']['good_qty'] == 3 and x['today']['defect_qty'] == 1
    assert x['today']['date'] == datetime.now(HCM).date().isoformat()

    _insert(db, e2, op, 'OPEN', now - timedelta(minutes=1))
    x = row()
    assert [w['employee_id'] for w in x['active_worker_list']] == [e2]  # OPEN-only
    assert x['today_state'] == 'RUNNING'
    assert [w['employee_id'] for w in x['today_worker_list']] == [e1]
    assert x['today']['employee_count'] == 2 and x['today']['open_session_count'] == 1
