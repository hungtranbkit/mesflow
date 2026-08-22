"""Kiosk trình chiếu năng suất nhân viên (wallboard) -- config publish/read
and the public data endpoint the Kiosk screen polls.

Covers the backend-testable half of the task's 10 required CASEs (CASE
5/8's client-only halves -- Preview never calling publish, and the JS
keeping last-good data on a fetch error -- live in
wallboard-employee-productivity.js and are exercised by hand/Playwright,
not pytest). No business logic is duplicated here: every number asserted
below comes from the exact same ReportRepository.employee_productivity()
formula already covered by test_employee_productivity.py -- this file only
asserts that the wallboard's config layer (publish/get/persist) and its
public read-only projection reuse that source of truth correctly.
"""
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')
CONFIG_URL = 'http://mesflow-test-api:8080/api/reports/employee-productivity/wallboard-config'
WALLBOARD_URL = 'http://mesflow-test-api:8080/api/wallboard/employee-productivity'


def _insert_session(db, employee_id, operation_id, station_id, suffix, tag, status, start, end=None, good_qty=0, defect_qty=0):
    row = db.execute(
        """INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
           VALUES(%s,%s,%s,'docker-e2e',%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (employee_id, operation_id, station_id, status, start, end, good_qty, defect_qty,
         f'wb-start-{tag}-{suffix}', f'wb-finish-{tag}-{suffix}' if end else None),
    ).fetchone()
    return row['id']


def _publish(api, **overrides):
    body = {
        'date_mode': 'fixed', 'from': '2026-08-01', 'to': '2026-08-22',
        'department': None, 'sort': 'productivity_desc', 'page_size': 10,
        'refresh_interval_seconds': 20,
    }
    body.update(overrides)
    response = api.post(CONFIG_URL, json=body, timeout=10)
    assert response.status_code == 200, response.text
    body_out = response.json()
    assert body_out['ok'] is True
    return body_out['config']


def _get_config(api):
    response = api.get(CONFIG_URL, timeout=10)
    assert response.status_code == 200, response.text
    return response.json()['config']


def _get_wallboard(api=None):
    import requests
    session = api or requests
    response = session.get(WALLBOARD_URL, timeout=10)
    assert response.status_code == 200, response.text
    return response.json()


def _one(employees, employee_id):
    match = [x for x in employees if x['employee_id'] == employee_id]
    assert match, f'employee {employee_id} missing from wallboard payload: {employees}'
    return match[0]


@pytest.fixture(autouse=True)
def _reset_wallboard_config(db):
    """Every CASE below publishes its own config -- start each test from a
    clean, unconfigured slate rather than inheriting the previous test's."""
    yield
    db.execute("DELETE FROM app_settings WHERE key='employee_productivity_wallboard'")


# CASE 1 -- fixed range publish -> public wallboard reflects that exact range/data.
def test_case1_fixed_range_publish_reflected_on_public_wallboard(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)

    _publish(api, date_mode='fixed', to='2026-08-06', **{'from': '2026-08-06'})
    payload = _get_wallboard()
    assert payload['configured'] is True
    assert payload['config']['from'] == '2026-08-06' and payload['config']['to'] == '2026-08-06'
    row = _one(payload['employees'], g['employee_id'])
    assert row['productivity_percent'] == 50.0
    assert row['completed_valid_sessions'] == 1


# CASE 2 -- dynamic month-to-date: no from/to stored; public payload's
# resolved summary range is [first of current month, today] in HCM time.
def test_case2_dynamic_month_to_date_resolves_to_today(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    today_hcm = datetime.now(HCM).date()
    session_day = datetime.combine(today_hcm, datetime.min.time(), tzinfo=HCM).replace(hour=9)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                     'CLOSED', session_day, session_day + timedelta(minutes=20), good_qty=10)

    cfg = _publish(api, date_mode='dynamic_mtd', **{'from': None, 'to': None})
    assert cfg['date_mode'] == 'dynamic_mtd' and cfg['from'] is None and cfg['to'] is None

    payload = _get_wallboard()
    assert payload['summary']['from'] == today_hcm.replace(day=1).isoformat()
    assert payload['summary']['to'] == today_hcm.isoformat()
    row = _one(payload['employees'], g['employee_id'])
    assert row['productivity_percent'] == 50.0


# CASE 3 -- department filter published -> wallboard only shows that department.
def test_case3_department_filter_propagates_to_wallboard(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    db.execute("UPDATE employees SET department='LINE-A' WHERE id=%s", (g['employee_id'],))
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)

    _publish(api, date_mode='fixed', **{'from': '2026-08-06', 'to': '2026-08-06'}, department='LINE-B')
    payload = _get_wallboard()
    assert not any(x['employee_id'] == g['employee_id'] for x in payload['employees'])

    _publish(api, date_mode='fixed', **{'from': '2026-08-06', 'to': '2026-08-06'}, department='LINE-A')
    payload = _get_wallboard()
    assert _one(payload['employees'], g['employee_id'])['employee_id'] == g['employee_id']


# CASE 4 -- sort change published -> wallboard employee order changes accordingly.
def test_case4_sort_change_propagates_to_wallboard_order(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    # Two employees under one department via a second employee row (reuse station/op).
    row = db.execute(
        "INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,'B Second','SORTDEPT','Worker',%s) RETURNING id",
        (f'TEST2-{g["suffix"]}', f'WF|EMP|TEST2-{g["suffix"]}'),
    ).fetchone()
    second_id = row['id']
    db.execute("UPDATE employees SET name='A First', department='SORTDEPT' WHERE id=%s", (g['employee_id'],))
    try:
        _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                         'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)  # 50%
        _insert_session(db, second_id, g['operation_id'], g['station_id'], g['suffix'], 's2',
                         'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 10, tzinfo=HCM), good_qty=10)  # 100%

        _publish(api, date_mode='fixed', **{'from': '2026-08-06', 'to': '2026-08-06'}, department='SORTDEPT', sort='name_asc')
        names = [x['employee_name'] for x in _get_wallboard()['employees']]
        assert names == ['A First', 'B Second']

        _publish(api, date_mode='fixed', **{'from': '2026-08-06', 'to': '2026-08-06'}, department='SORTDEPT', sort='productivity_desc')
        ids_by_pct = [x['employee_id'] for x in _get_wallboard()['employees']]
        assert ids_by_pct[0] == second_id  # 100% ranks above 50%
    finally:
        db.execute("DELETE FROM work_sessions WHERE employee_id=%s", (second_id,))
        db.execute("DELETE FROM employees WHERE id=%s", (second_id,))


# CASE 5 -- "preview" is just a plain GET against the existing authenticated
# report endpoint (no wallboard-config write happens); confirm calling it
# with arbitrary params never mutates the published config.
def test_case5_preview_style_report_call_does_not_mutate_published_config(db, api, seeded_factory):
    g = seeded_factory
    published = _publish(api, date_mode='fixed', **{'from': '2026-08-01', 'to': '2026-08-22'}, sort='name_asc', page_size=7)

    response = api.get('http://mesflow-test-api:8080/api/reports/employee-productivity?from=2020-01-01&to=2020-01-31&department=NOPE', timeout=10)
    assert response.status_code == 200, response.text

    unchanged = _get_config(api)
    assert unchanged['from'] == published['from'] and unchanged['to'] == published['to']
    assert unchanged['sort'] == 'name_asc' and unchanged['page_size'] == 7


# CASE 6 -- publish DOES update the config visible to both the manager panel and the public wallboard.
def test_case6_publish_updates_config_state(api):
    before = _get_config(api)
    assert before['configured'] is False

    after = _publish(api, date_mode='fixed', **{'from': '2026-08-10', 'to': '2026-08-11'}, sort='sessions_desc', page_size=15, refresh_interval_seconds=30)
    assert after['configured'] is True
    assert after['from'] == '2026-08-10' and after['to'] == '2026-08-11'
    assert after['sort'] == 'sessions_desc' and after['page_size'] == 15 and after['refresh_interval_seconds'] == 30
    assert after['updated_by'] == 'admin' and after['updated_at']


# CASE 7 -- kiosk polling again after new data lands keeps the same
# published filter but returns the freshly updated numbers.
def test_case7_wallboard_refetch_keeps_filter_but_updates_data(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    _publish(api, date_mode='fixed', **{'from': '2026-08-06', 'to': '2026-08-06'})

    first = _get_wallboard()
    assert not any(x['employee_id'] == g['employee_id'] for x in first['employees'])

    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)
    second = _get_wallboard()
    assert second['config']['from'] == first['config']['from'] == '2026-08-06'
    row = _one(second['employees'], g['employee_id'])
    assert row['productivity_percent'] == 50.0


# CASE 9 -- wallboard payload never server-side truncates to page_size; it
# hands the FULL filtered list back so the client can page through it.
def test_case9_wallboard_returns_full_list_for_client_side_paging(db, api, seeded_factory):
    g = seeded_factory
    db.execute("UPDATE operations SET standard_seconds_per_unit=60 WHERE id=%s", (g['operation_id'],))
    db.execute("UPDATE employees SET department='PAGEDEPT' WHERE id=%s", (g['employee_id'],))
    ids = [g['employee_id']]
    try:
        for i in range(25):
            row = db.execute(
                "INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'PAGEDEPT','Worker',%s) RETURNING id",
                (f'PG{i}-{g["suffix"]}', f'Page Worker {i:02d}', f'WF|EMP|PG{i}-{g["suffix"]}'),
            ).fetchone()
            ids.append(row['id'])
            _insert_session(db, row['id'], g['operation_id'], g['station_id'], g['suffix'], f'pg{i}',
                             'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)
        _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 's1',
                         'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 20, tzinfo=HCM), good_qty=10)

        _publish(api, date_mode='fixed', **{'from': '2026-08-06', 'to': '2026-08-06'}, department='PAGEDEPT', page_size=10)
        payload = _get_wallboard()
        assert payload['config']['page_size'] == 10
        assert len(payload['employees']) == 26  # full list, client pages it in chunks of page_size
    finally:
        db.execute("DELETE FROM work_sessions WHERE employee_id=ANY(%s)", (ids[1:],))
        db.execute("DELETE FROM employees WHERE id=ANY(%s)", (ids[1:],))


# CASE 10 -- published config is a real DB row (app_settings), not
# in-process state -- a fresh read (simulating a post-restart reload) still
# returns it, and the row itself is directly inspectable.
def test_case10_published_config_persists_in_app_settings_table(db, api):
    _publish(api, date_mode='fixed', **{'from': '2026-08-01', 'to': '2026-08-02'}, sort='name_asc', page_size=12, refresh_interval_seconds=25)

    row = db.execute("SELECT value_json, updated_at FROM app_settings WHERE key='employee_productivity_wallboard'").fetchone()
    assert row is not None
    assert row['value_json']['from'] == '2026-08-01' and row['value_json']['page_size'] == 12
    assert row['updated_at'] is not None

    reread = _get_config(api)
    assert reread['from'] == '2026-08-01' and reread['page_size'] == 12


# --- Validation -------------------------------------------------------
def test_publish_rejects_fixed_mode_without_dates(api):
    response = api.post(CONFIG_URL, json={'date_mode': 'fixed', 'from': None, 'to': None}, timeout=10)
    assert response.status_code == 400, response.text


def test_publish_rejects_from_after_to(api):
    response = api.post(CONFIG_URL, json={'date_mode': 'fixed', 'from': '2026-08-20', 'to': '2026-08-01'}, timeout=10)
    assert response.status_code == 400, response.text


def test_publish_rejects_unknown_sort(api):
    response = api.post(CONFIG_URL, json={'date_mode': 'dynamic_mtd', 'sort': 'not-a-real-sort'}, timeout=10)
    assert response.status_code == 400, response.text


def test_publish_rejects_out_of_range_page_size(api):
    response = api.post(CONFIG_URL, json={'date_mode': 'dynamic_mtd', 'page_size': 999}, timeout=10)
    assert response.status_code == 400, response.text


# --- Permissions --------------------------------------------------------
def test_public_wallboard_data_requires_no_auth(db):
    """The TV has no one logged in -- matches /kiosk's existing precedent."""
    payload = _get_wallboard()
    assert payload['ok'] is True


def test_publish_forbidden_for_viewer_role(api):
    import requests
    suffix = datetime.now(HCM).strftime('%H%M%S%f')
    username = f'wbviewer{suffix}'
    create = api.post('http://mesflow-test-api:8080/api/users', json={
        'username': username, 'display_name': 'Wallboard Viewer Test',
        'role': 'viewer', 'password': 'Viewer@12345', 'must_change_password': False,
    }, timeout=10)
    assert create.status_code in (200, 201), create.text
    try:
        viewer_session = requests.Session()
        login = viewer_session.post('http://mesflow-test-api:8080/api/auth/login', json={
            'username': username, 'password': 'Viewer@12345',
        }, timeout=10)
        assert login.status_code == 200, login.text

        response = viewer_session.post(CONFIG_URL, json={'date_mode': 'dynamic_mtd'}, timeout=10)
        assert response.status_code == 403, response.text

        # GET (read the current publish state) stays available to any logged-in role.
        read = viewer_session.get(CONFIG_URL, timeout=10)
        assert read.status_code == 200, read.text
    finally:
        # users.py exposes no DELETE route -- deactivate instead so this
        # throwaway test account can't be used to log in afterwards.
        user_id = create.json().get('id')
        if user_id:
            api.patch(f'http://mesflow-test-api:8080/api/users/{user_id}', json={'active': False}, timeout=10)
