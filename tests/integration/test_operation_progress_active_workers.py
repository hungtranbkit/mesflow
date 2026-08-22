"""Regression coverage for "Tiến độ theo Operation" -> cột Người làm.

Bug: the column showed every employee who ever had a session on the
Operation, including ones whose session had already ended. Root cause was
DashboardRepository.daily_progress() aggregating STRING_AGG(DISTINCT e.name)
over ALL sessions in the shift window with no status filter.

Fix: /api/dashboard/shift and /api/dashboard/daily-progress items now carry
`active_workers` (distinct employees with an OPEN session -- the only ones
the UI renders as "Người làm") and `all_participants` (everyone in the
window, for an optional history tooltip), while `session_count` (total) and
`open_session_count` (running) stay exactly as before.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')
SHIFT_DATE = '2026-08-06'


def _shift_id(db, code='DAY'):
    return db.execute("SELECT id FROM work_shifts WHERE code=%s", (code,)).fetchone()['id']


def _insert_session(db, employee_id, operation_id, station_id, suffix, tag, status, start, end=None, good_qty=1, defect_qty=0):
    row = db.execute(
        """INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
           VALUES(%s,%s,%s,'docker-e2e',%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (employee_id, operation_id, station_id, status, start, end, good_qty, defect_qty,
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


def test_ended_session_worker_absent_open_session_worker_present(db, api, seeded_factory):
    # "Huỳnh Thị Mơ đã kết thúc, Phạm Xuân Dung còn đang chạy" -> chỉ hiển thị Phạm Xuân Dung.
    g = seeded_factory
    day = _shift_id(db)
    ended_id = _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'ended',
                                'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 30, tzinfo=HCM))
    runner_id = _extra_employee(db, g['suffix'], 'runner')
    try:
        open_id = _insert_session(db, runner_id, g['operation_id'], g['station_id'], g['suffix'], 'open',
                                   'OPEN', datetime(2026, 8, 6, 9, 15, tzinfo=HCM))
        item = _op_item(_fetch(api, day), g['operation_id'])
        assert item['session_count'] == 2
        assert item['open_session_count'] == 1
        active_ids = {w['employee_id'] for w in item['active_workers']}
        assert active_ids == {runner_id}
        assert g['employee_id'] not in active_ids
        all_ids = {w['employee_id'] for w in item['all_participants']}
        assert all_ids == {g['employee_id'], runner_id}
    finally:
        db.execute("DELETE FROM work_sessions WHERE id=ANY(%s)", ([ended_id, open_id],))
        db.execute("DELETE FROM employees WHERE id=%s", (runner_id,))


def test_zero_running_sessions_active_workers_empty(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    s1 = _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'closed1',
                          'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM))
    s2 = _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'closed2',
                          'CLOSED', datetime(2026, 8, 6, 10, 0, tzinfo=HCM), datetime(2026, 8, 6, 10, 20, tzinfo=HCM))
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['session_count'] == 2
    assert item['open_session_count'] == 0
    assert item['active_workers'] == []
    assert item['day_state'] != 'RUNNING'
    # History stays available for a tooltip, just never as the default value.
    assert {w['employee_id'] for w in item['all_participants']} == {g['employee_id']}


def test_three_sessions_same_employee_total_unaffected_active_workers_distinct(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                     'CLOSED', datetime(2026, 8, 6, 8, 0, tzinfo=HCM), datetime(2026, 8, 6, 8, 20, tzinfo=HCM))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's2',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's3',
                     'OPEN', datetime(2026, 8, 6, 10, 0, tzinfo=HCM))
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['session_count'] == 3  # total_sessions không bị gộp/thay đổi
    assert item['open_session_count'] == 1
    assert len(item['active_workers']) == 1  # DISTINCT theo employee_id, không lặp lại 3 lần
    assert item['active_workers'][0]['employee_id'] == g['employee_id']


def test_employee_with_closed_and_new_open_session_appears_once(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'old',
                     'CLOSED', datetime(2026, 8, 6, 8, 0, tzinfo=HCM), datetime(2026, 8, 6, 8, 30, tzinfo=HCM))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'new',
                     'OPEN', datetime(2026, 8, 6, 9, 0, tzinfo=HCM))
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['session_count'] == 2
    assert item['open_session_count'] == 1
    assert len(item['active_workers']) == 1
    assert item['active_workers'][0]['employee_id'] == g['employee_id']


def test_multiple_employees_running_same_operation_each_listed_once(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    second_id = _extra_employee(db, g['suffix'], 'second')
    try:
        s1 = _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'p1',
                              'OPEN', datetime(2026, 8, 6, 9, 0, tzinfo=HCM))
        s2 = _insert_session(db, second_id, g['operation_id'], g['station_id'], g['suffix'], 'p2',
                              'OPEN', datetime(2026, 8, 6, 9, 5, tzinfo=HCM))
        item = _op_item(_fetch(api, day), g['operation_id'])
        assert item['session_count'] == 2
        assert item['open_session_count'] == 2
        active_ids = [w['employee_id'] for w in item['active_workers']]
        assert sorted(active_ids) == sorted([g['employee_id'], second_id])
        assert len(active_ids) == len(set(active_ids))  # DISTINCT theo employee_id
    finally:
        db.execute("DELETE FROM work_sessions WHERE id=ANY(%s)", ([s1, s2],))
        db.execute("DELETE FROM employees WHERE id=%s", (second_id,))
