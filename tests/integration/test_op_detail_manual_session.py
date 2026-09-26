"""Operation Detail "Bổ sung phiên" (2026-09-26 hotfix): a manager records a
session an employee forgot to scan on a past day.

Real PostgreSQL + real API. The supplement must be a REAL historical CLOSED
work_sessions row -- so Operation Detail, the report rollup, Operation/PO
totals and Overview pick it up with no special casing -- with a
SESSION_MANUAL_CREATE audit row and an initial operation_adjustments entry
(0 -> entered). It must never show up as someone currently working
(active_worker_list is OPEN sessions only)."""
import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests
from werkzeug.security import generate_password_hash

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

TZ = ZoneInfo('Asia/Ho_Chi_Minh')
URL = f'{BASE_URL}/api/supervisor/sessions/manual'


def _local(dt):
    """datetime-local shape the browser sends (no offset, minute precision)."""
    return dt.strftime('%Y-%m-%dT%H:%M')


def _yesterday(hour, minute=0):
    base = datetime.now(TZ) - timedelta(days=1)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _body(g, **over):
    body = {
        'operation_id': g['operation_id'], 'employee_id': g['employee_id'],
        'started_at': _local(_yesterday(8)), 'ended_at': _local(_yesterday(10)),
        'good_qty': 30, 'defect_qty': 2, 'reason': 'Công nhân quên quét QR kết thúc',
        'note': 'ghi chú kiểm thử', 'request_id': f'TEST-MANUAL-{uuid.uuid4()}',
    }
    body.update(over)
    return body


def _count_sessions(db, g):
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s', (g['employee_id'],))
        return cur.fetchone()['n']


@pytest.fixture
def graph(db, seeded_factory):
    with db.cursor() as cur:
        cur.execute('UPDATE operations SET standard_seconds_per_unit=120 WHERE id=%s', (seeded_factory['operation_id'],))
    return seeded_factory


def test_manual_session_is_a_real_closed_session_with_audit_and_totals(api, db, graph):
    g = graph
    body = _body(g)
    response = api.post(URL, json=body, timeout=15)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload['ok'] is True and payload['idempotent_replay'] is False
    session = payload['session']
    sid = session['id']

    with db.cursor() as cur:
        cur.execute('SELECT * FROM work_sessions WHERE id=%s', (sid,))
        row = cur.fetchone()
    assert row['status'] == 'CLOSED'
    assert row['employee_id'] == g['employee_id'] and row['operation_id'] == g['operation_id']
    # Naive datetime-local is read in the factory timezone, whatever the browser's.
    assert row['started_at'] == _yesterday(8) and row['ended_at'] == _yesterday(10)
    assert (row['good_qty'], row['defect_qty'], row['rework_qty']) == (30, 2, 0)
    assert row['close_reason'] == 'MANUAL_SUPPLEMENT'
    assert row['quantity_confirmed'] is True and row['closed_by_system'] is False
    assert row['excluded_from_reports'] is False
    assert row['note'] == 'ghi chú kiểm thử'
    assert row['start_request_id'] == body['request_id']

    with db.cursor() as cur:
        cur.execute("SELECT * FROM audit_logs WHERE action='SESSION_MANUAL_CREATE' AND entity_id=%s", (str(sid),))
        audits = cur.fetchall()
        cur.execute('SELECT * FROM operation_adjustments WHERE session_id=%s', (sid,))
        adjustments = cur.fetchall()
        cur.execute('SELECT movement_type,delta,source FROM quantity_movements WHERE session_id=%s ORDER BY movement_type', (sid,))
        movements = cur.fetchall()
        cur.execute('SELECT done_qty,defect_qty FROM operations WHERE id=%s', (g['operation_id'],))
        op = cur.fetchone()
    assert len(audits) == 1
    audit = audits[0]
    details = audit['details_json'] if isinstance(audit['details_json'], dict) else json.loads(audit['details_json'])
    assert audit['actor_username'] == 'admin' and audit['entity_type'] == 'work_session'
    assert audit['employee_id'] == g['employee_id'] and audit['correlation_id'] == body['request_id']
    for key in ('actor', 'reason', 'session_id', 'operation_id', 'employee_id', 'started_at', 'ended_at', 'good_qty', 'defect_qty'):
        assert key in details, key
    assert details['reason'] == body['reason'] and details['session_id'] == sid
    assert details['operation_id'] == g['operation_id'] and details['employee_id'] == g['employee_id']
    assert (details['good_qty'], details['defect_qty']) == (30, 2)
    assert len(adjustments) == 1
    adj = adjustments[0]
    assert (adj['old_good_qty'], adj['new_good_qty'], adj['old_defect_qty'], adj['new_defect_qty']) == (0, 30, 0, 2)
    assert adj['reason'] == body['reason']
    assert [(m['movement_type'], m['delta'], m['source']) for m in movements] == [
        ('DEFECT', 2, 'MANUAL_SUPPLEMENT'), ('GOOD', 30, 'MANUAL_SUPPLEMENT')]
    # Real totals via the ordinary reconcile, not a patched aggregate.
    assert (op['done_qty'], op['defect_qty']) == (30, 2)

    report = api.get(f'{BASE_URL}/api/reports/operation-sessions?operation_id={g["operation_id"]}&limit=3000', timeout=15).json()['report']
    (listed,) = [s for s in report['sessions'] if s['session_id'] == sid]
    assert listed['status'] == 'CLOSED' and listed['close_reason'] == 'MANUAL_SUPPLEMENT'
    assert listed['duration_seconds'] == 7200 and listed['adjustment_count'] == 1
    (user,) = [u for u in report['users'] if u['employee_id'] == g['employee_id']]
    assert (user['good_qty'], user['defect_qty'], user['session_count'], user['open_session_count']) == (30, 2, 1, 0)

    overview = api.get(f'{BASE_URL}/api/dashboard/overview?limit=5000', timeout=30).json()
    (ov,) = [x for x in overview['operations'] if x['operation_id'] == g['operation_id']]
    assert ov['active_worker_list'] == [] and ov['active_worker_count'] == 0

    # Double submit with the same key replays -- still exactly one session.
    replay = api.post(URL, json=body, timeout=15)
    assert replay.status_code == 200, replay.text
    assert replay.json()['idempotent_replay'] is True and replay.json()['session']['id'] == sid
    assert _count_sessions(db, g) == 1


def test_manual_session_never_counts_as_currently_active(api, db, graph):
    g = graph
    started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'TEST-MANUAL-OPEN-{uuid.uuid4()}', 'employee_id': g['employee_id'],
        'operation_id': g['operation_id'], 'device_uuid': 'TEST-MANUAL'}, timeout=15)
    assert started.status_code == 201, started.text
    open_id = started.json()['session']['id']
    created = api.post(URL, json=_body(g), timeout=15)
    assert created.status_code == 201, created.text
    overview = api.get(f'{BASE_URL}/api/dashboard/overview?limit=5000', timeout=30).json()
    (ov,) = [x for x in overview['operations'] if x['operation_id'] == g['operation_id']]
    (worker,) = ov['active_worker_list']
    assert worker['employee_id'] == g['employee_id']
    assert worker['session_ids'] == [open_id] and worker['session_count'] == 1


@pytest.mark.parametrize('override,status', [
    ({'reason': '   '}, 400),
    ({'reason': None}, 400),
    ({'ended_at': 'SAME'}, 400),
    ({'ended_at': 'BEFORE'}, 400),
    ({'ended_at': None}, 400),
    ({'started_at': ''}, 400),
    ({'started_at': 'not-a-date'}, 400),
    ({'ended_at': 'FUTURE'}, 400),
    ({'good_qty': -1}, 400),
    ({'defect_qty': -3}, 400),
    ({'good_qty': 1.5}, 400),
    ({'good_qty': 'abc'}, 400),
    ({'employee_id': 999999999}, 404),
    ({'employee_id': None}, 400),
    ({'operation_id': 999999999}, 404),
])
def test_manual_session_validation(api, db, graph, override, status):
    g = graph
    special = {'SAME': _local(_yesterday(8)), 'BEFORE': _local(_yesterday(7)),
               'FUTURE': _local(datetime.now(TZ) + timedelta(hours=2))}
    override = {k: special.get(v, v) if isinstance(v, str) else v for k, v in override.items()}
    before = _count_sessions(db, g)
    response = api.post(URL, json=_body(g, **override), timeout=15)
    assert response.status_code == status, response.text
    assert response.json()['ok'] is False
    assert _count_sessions(db, g) == before


def test_overlap_is_only_blocked_on_the_same_operation(api, db, graph):
    g = graph
    first = api.post(URL, json=_body(g), timeout=15)
    assert first.status_code == 201, first.text
    # Same employee, same Operation, overlapping time: the existing
    # same-Operation integrity rule (start/finish/edit_session) applies.
    clash = api.post(URL, json=_body(g, started_at=_local(_yesterday(9)), ended_at=_local(_yesterday(11))), timeout=15)
    assert clash.status_code == 409, clash.text
    # Different Operation, same hours: multi-session (0054) stays allowed.
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                       VALUES(%s,%s,%s,'Manual second OP','IN_PROGRESS',%s) RETURNING id""",
                    (g['po_id'], g['part_id'], f'TEST-MOP2-{g["suffix"]}', f'WF|OP|TEST-MOP2-{g["suffix"]}'))
        op2 = cur.fetchone()['id']
    other = api.post(URL, json=_body(g, operation_id=op2, started_at=_local(_yesterday(9)), ended_at=_local(_yesterday(11))), timeout=15)
    assert other.status_code == 201, other.text


def test_setup_operation_is_refused(api, db, graph):
    g = graph
    configured = api.put(f'{BASE_URL}/api/operations/{g["operation_id"]}/setup', json={
        'requires_setup': True, 'expected_setup_minutes': 10, 'setup_note': 'x'}, timeout=15)
    assert configured.status_code == 200, configured.text
    setup_id = api.get(f'{BASE_URL}/api/operations/{g["operation_id"]}/setup', timeout=15).json()['setup']['id']
    response = api.post(URL, json=_body(g, operation_id=setup_id, good_qty=0, defect_qty=0), timeout=15)
    assert response.status_code == 409, response.text


def _login_as(db, role):
    username = f'manualtest-{role}-{uuid.uuid4().hex[:10]}'
    with db.cursor() as cur:
        cur.execute("INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) "
                    "VALUES(%s,%s,%s,%s,TRUE,FALSE) RETURNING id",
                    (username, role, generate_password_hash('Test@123456'), role))
        user_id = cur.fetchone()['id']
    s = requests.Session()
    r = s.post(f'{BASE_URL}/api/auth/login', json={'username': username, 'password': 'Test@123456'}, timeout=15)
    assert r.status_code == 200, r.text
    return s, user_id


def test_permission_boundary_matches_session_edit(db, graph):
    g = graph
    created_users = []
    try:
        for role, expected in (('operator', 403), ('viewer', 403), ('supervisor', 201), ('manager', 201)):
            s, user_id = _login_as(db, role)
            created_users.append(user_id)
            hour = {'supervisor': 13, 'manager': 15}.get(role, 13)
            r = s.post(URL, json=_body(g, started_at=_local(_yesterday(hour)), ended_at=_local(_yesterday(hour + 1))), timeout=15)
            assert r.status_code == expected, f'{role}: {r.status_code} {r.text}'
        anonymous = requests.post(URL, json=_body(g), timeout=15)
        assert anonymous.status_code in (401, 403)
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM users WHERE id=ANY(%s)', (created_users,))
