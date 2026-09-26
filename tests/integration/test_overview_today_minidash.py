"""Production Overview mini-dashboard (2026-09-26, part 3), real PostgreSQL.

today_activity_by_operation(now=...) pinned to 2026-08-06 15:00
Asia/Ho_Chi_Minh: first/last time, break-aware work time (same
working_intervals_between() Dashboard uses), expected time = định mức ×
(Đạt + Lỗi) with Sửa được never added again, weighted So định mức
(SUM dự kiến ÷ SUM thực tế over CLOSED sessions with output), delta/pace,
no-standard behaviour, exact employee_ids, local-midnight clamp, OPEN
precedence, and the live /api/dashboard/overview contract."""
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


def _work(*spans):
    return int(sum((b - a).total_seconds() for s, e in spans for a, b in working_intervals_between(s, e)))


def _insert(db, employee_id, operation_id, status, start, end=None, good=0, defect=0, rework=0,
            closed_by_system=False, quantity_confirmed=True):
    tag = uuid.uuid4().hex
    return db.execute(
        """INSERT INTO work_sessions(employee_id,operation_id,device_uuid,status,started_at,ended_at,
               good_qty,defect_qty,rework_qty,closed_by_system,quantity_confirmed,start_request_id,finish_request_id)
           VALUES(%s,%s,'docker-e2e',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (employee_id, operation_id, status, start, end, good, defect, rework, closed_by_system,
         quantity_confirmed, f'ov-mini-start-{tag}', f'ov-mini-finish-{tag}' if end else None)).fetchone()['id']


@pytest.fixture
def graph(db, seeded_factory):
    g = dict(seeded_factory)
    s = g['suffix']
    extra = []
    with db.cursor() as cur:
        for i in (2, 3):
            cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) "
                        "VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                        (f'MINI{i}-{s}', f'Mini {i} {s}', f'WF|EMP|MINI{i}-{s}'))
            extra.append(cur.fetchone()['id'])
        cur.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,standard_seconds_per_unit)
                       VALUES(%s,%s,%s,'No standard','IN_PROGRESS',%s,0) RETURNING id""",
                    (g['po_id'], g['part_id'], f'MINI-OPB-{s}', f'WF|OP|MINI-OPB-{s}'))
        g['operation_b_id'] = cur.fetchone()['id']
    g['employee2_id'], g['employee3_id'] = extra
    yield g
    with db.cursor() as cur:
        for emp in extra:
            cur.execute("DELETE FROM work_sessions WHERE employee_id=%s", (emp,))
            cur.execute("DELETE FROM employees WHERE id=%s", (emp,))


def test_minidash_metrics_for_one_operation(db, graph):
    g = graph
    op, opb = g['operation_id'], g['operation_b_id']
    e1, e2, e3 = g['employee_id'], g['employee2_id'], g['employee3_id']
    _insert(db, e1, op, 'CLOSED', L(5, 9), L(5, 10), good=500)                      # yesterday: never counts
    _insert(db, e1, op, 'CLOSED', L(6, 11), L(6, 14), good=100, defect=10, rework=4)  # spans lunch
    _insert(db, e2, op, 'CLOSED', L(6, 7, 30), L(6, 8, 30), good=20)                 # starts before shift
    _insert(db, e3, op, 'OPEN', L(6, 14, 30))                                        # running, no output yet
    _insert(db, e1, opb, 'CLOSED', L(6, 9), L(6, 10), good=5)                        # no định mức

    today = DashboardRepository().today_activity_by_operation(NOW)
    t = today[op]
    assert (t['good_qty'], t['defect_qty'], t['rework_qty']) == (120, 10, 4)
    # Sửa được is a subset of Lỗi: 60 s × (120 + 10), never × 134.
    assert t['expected_seconds'] == 60 * 130
    assert t['standard_configured'] is True
    assert t['employee_count'] == 3 and t['employee_ids'] == sorted([e1, e2, e3])
    assert t['session_count'] == 3 and t['open_session_count'] == 1
    assert datetime.fromisoformat(str(t['first_started_at'])) == L(6, 7, 30)
    assert datetime.fromisoformat(str(t['last_ended_at'])) == L(6, 14)
    # Break-aware actual time, the working calendar's own WORK windows.
    w1, w2, w3 = _work((L(6, 11), L(6, 14))), _work((L(6, 7, 30), L(6, 8, 30))), _work((L(6, 14, 30), NOW))
    assert t['actual_work_seconds'] == t['work_seconds'] == w1 + w2 + w3
    # Seeded calendar (DAY 08-12 / 13-17): lunch and pre-shift time do not count.
    assert (w1, w2, w3) == (7200, 1800, 1800)
    # Weighted basis = the two CLOSED sessions with output; the OPEN one is out.
    assert t['weighted_session_count'] == 2
    assert t['scored_work_seconds'] == w1 + w2
    assert t['scored_expected_seconds'] == 60 * 110 + 60 * 20
    assert t['weighted_productivity_percent'] == pytest.approx(round(7800 / (w1 + w2) * 100, 1))
    assert t['delta_seconds'] == (w1 + w2) - 7800
    assert t['delta_seconds'] == 1200 and t['pace'] == 'SLOW' and t['weighted_productivity_percent'] == 86.7
    # Not the unweighted AVG of per-session scores.
    assert t['weighted_productivity_percent'] != t['productivity_percent']

    b = today[opb]
    assert b['standard_configured'] is False and b['expected_seconds'] == 0
    assert b['weighted_productivity_percent'] is None and b['delta_seconds'] is None and b['pace'] is None
    assert b['good_qty'] == 5 and b['employee_ids'] == [e1]

    # OPEN wins: e3 is only in active_worker_list, the others are history.
    repo = DashboardRepository()
    row = {'operation_id': op, 'active_worker_list': repo.active_workers_by_operation().get(op, [])}
    _attach_today(row, today)
    assert [w['employee_id'] for w in row['active_worker_list']] == [e3]
    assert row['today_state'] == 'RUNNING'
    assert {w['employee_id'] for w in row['today_worker_list']} == {e1, e2}
    assert row['today']['employee_ids'] == sorted([e1, e2, e3])


def test_on_target_and_fast_pace(db, graph):
    g = graph
    op, e1, e2 = g['operation_id'], g['employee_id'], g['employee2_id']
    # 09:00-10:00 inside the morning window: 60 SP × 60 s = exactly one hour.
    _insert(db, e1, op, 'CLOSED', L(6, 9), L(6, 10), good=55, defect=5, rework=5)
    work = _work((L(6, 9), L(6, 10)))
    t = DashboardRepository().today_activity_by_operation(NOW)[op]
    assert t['expected_seconds'] == 3600 and t['scored_work_seconds'] == work
    assert work == 3600
    assert t['pace'] == 'ON_TARGET' and t['delta_seconds'] == 0 and t['weighted_productivity_percent'] == 100.0
    # A second, fast session: 30 SP in 15 minutes.
    _insert(db, e2, op, 'CLOSED', L(6, 10, 15), L(6, 10, 30), good=30)
    t = DashboardRepository().today_activity_by_operation(NOW)[op]
    work += _work((L(6, 10, 15), L(6, 10, 30)))
    assert t['scored_expected_seconds'] == 5400 and t['delta_seconds'] == work - 5400
    assert work == 4500
    assert t['pace'] == 'FAST' and t['weighted_productivity_percent'] == 120.0


def test_only_open_or_unconfirmed_sessions_have_no_score(db, graph):
    g = graph
    op, e1, e2 = g['operation_id'], g['employee_id'], g['employee2_id']
    _insert(db, e1, op, 'OPEN', L(6, 14))
    _insert(db, e2, op, 'CLOSED', L(6, 9), L(6, 10), closed_by_system=True, quantity_confirmed=False)
    t = DashboardRepository().today_activity_by_operation(NOW)[op]
    assert t['standard_configured'] is True and t['actual_work_seconds'] > 0
    assert t['weighted_session_count'] == 0
    assert t['weighted_productivity_percent'] is None and t['delta_seconds'] is None and t['pace'] is None


def test_first_start_is_clamped_to_local_midnight(db, graph):
    g = graph
    op, e1 = g['operation_id'], g['employee_id']
    _insert(db, e1, op, 'CLOSED', L(5, 23, 30), L(6, 0, 30), good=3)
    t = DashboardRepository().today_activity_by_operation(NOW)[op]
    assert datetime.fromisoformat(str(t['first_started_at'])) == L(6, 0)
    assert t['good_qty'] == 3 and t['expected_seconds'] == 180
    # Seen from the previous day at 23:45 the session started at 23:30 and
    # its quantity (reported after midnight) is not yet "today".
    prev = DashboardRepository().today_activity_by_operation(L(5, 23, 45))[op]
    assert datetime.fromisoformat(str(prev['first_started_at'])) == L(5, 23, 30)
    assert prev['good_qty'] == 0
    # Next day: gone.
    assert op not in DashboardRepository().today_activity_by_operation(L(7, 0).astimezone(timezone.utc))


def test_overview_api_exposes_minidash_fields(api, db, graph):
    g = graph
    op, e1 = g['operation_id'], g['employee_id']
    now = datetime.now(timezone.utc)
    midnight = datetime.now(HCM).replace(hour=0, minute=0, second=0, microsecond=0)
    start = max(midnight + timedelta(seconds=1), now - timedelta(minutes=20))
    _insert(db, e1, op, 'CLOSED', start, start + (now - start) / 2, good=3, defect=1, rework=1)
    r = api.get(f'{BASE_URL}/api/dashboard/overview?limit=5000', timeout=30)
    assert r.status_code == 200, r.text
    (x,) = [x for x in r.json()['operations'] if x['operation_id'] == op]
    t = x['today']
    assert t['expected_seconds'] == 240 and t['standard_configured'] is True
    assert t['employee_ids'] == [e1] and t['first_started_at'] and t['last_ended_at']
    for key in ('actual_work_seconds', 'scored_work_seconds', 'scored_expected_seconds', 'weighted_session_count',
                'weighted_productivity_percent', 'delta_seconds', 'pace'):
        assert key in t
    assert x['active_worker_list'] == []  # still OPEN-only
