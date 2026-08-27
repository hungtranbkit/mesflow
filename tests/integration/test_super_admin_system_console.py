"""SUPER_ADMIN / IT System Console -- DB-backed behavior over the real
running app (mesflow-test-api), mirroring test_permission_matrix.py's
pattern (real users, real login, real HTTP). RBAC 403 coverage itself lives
in tests/test_super_admin_system_console_unit.py (in-process, no DB needed
since the gate short-circuits before any query); this file covers what
genuinely requires the database and the real running service: the positive
path, role-assignment protection + audit, system-error independence from
product/session data, and service-control honesty (no real Deploy Agent is
configured in this test compose -- see compose.test.yml -- so this proves
the endpoint reports that honestly rather than faking success).
"""
from __future__ import annotations

import uuid

import pytest
import requests
from werkzeug.security import generate_password_hash

pytestmark = pytest.mark.postgres
BASE = 'http://mesflow-test-api:8080'


def _create_user(db, role, password='Test@123456'):
    username = f'sctest-{role}-{uuid.uuid4().hex[:10]}'
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) "
            "VALUES(%s,%s,%s,%s,TRUE,FALSE) RETURNING id",
            (username, role, generate_password_hash(password), role))
        user_id = cur.fetchone()['id']
    return username, password, user_id


def _login(username, password):
    s = requests.Session()
    r = s.post(f'{BASE}/api/auth/login', json={'username': username, 'password': password}, timeout=15)
    assert r.status_code == 200, f'login failed for {username}: {r.text}'
    return s


@pytest.fixture()
def super_admin(db):
    username, password, user_id = _create_user(db, 'super_admin')
    session = _login(username, password)
    yield {'session': session, 'username': username, 'user_id': user_id}
    with db.cursor() as cur:
        cur.execute('DELETE FROM users WHERE id=%s', (user_id,))


def test_super_admin_sees_every_new_page_admin_gets_403(super_admin, api):
    for path in ('/api/system-health', '/api/system-health/errors', '/api/system-health/services',
                 '/api/system-health/diagnostics', '/api/system-health/audit'):
        r_super = super_admin['session'].get(f'{BASE}{path}', timeout=15)
        assert r_super.status_code == 200, f'{path}: {r_super.text}'
        assert r_super.json()['ok'] is True
        r_admin = api.get(f'{BASE}{path}', timeout=15)
        assert r_admin.status_code == 403, f'plain admin unexpectedly allowed on {path}: {r_admin.text}'


def test_overview_reports_real_identity_fields(super_admin):
    r = super_admin['session'].get(f'{BASE}/api/system-health', timeout=15)
    body = r.json()
    assert body['environment'] == 'test'
    assert body['application_version']
    components = {c['component'] for c in body['components']}
    assert {'MESFLOW', 'POSTGRESQL'}.issubset(components)


def test_admin_cannot_grant_super_admin_but_super_admin_can(db, api, super_admin):
    target_username, _, target_id = _create_user(db, 'manager')
    try:
        # Plain admin (session-based 'api' fixture) must be rejected even
        # though it holds users.manage via the ordinary permission bypass.
        r = api.patch(f'{BASE}/api/users/{target_id}', json={'role': 'super_admin'}, timeout=15)
        assert r.status_code == 403, r.text

        with db.cursor() as cur:
            cur.execute('SELECT role FROM users WHERE id=%s', (target_id,))
            assert cur.fetchone()['role'] == 'manager'  # unchanged

        r = super_admin['session'].patch(f'{BASE}/api/users/{target_id}',
                                          json={'role': 'super_admin', 'reason': 'test grant'}, timeout=15)
        assert r.status_code == 200, r.text
        with db.cursor() as cur:
            cur.execute('SELECT role FROM users WHERE id=%s', (target_id,))
            assert cur.fetchone()['role'] == 'super_admin'

        audit = super_admin['session'].get(f'{BASE}/api/system-health/audit?limit=20', timeout=15).json()['items']
        assert any(a['action'] == 'SUPER_ADMIN_GRANTED' and a['target'] == target_username for a in audit)

        # Revoke back down -- also audited, also super-admin-only.
        r = api.patch(f'{BASE}/api/users/{target_id}', json={'role': 'manager'}, timeout=15)
        assert r.status_code == 403, r.text
        r = super_admin['session'].patch(f'{BASE}/api/users/{target_id}', json={'role': 'manager'}, timeout=15)
        assert r.status_code == 200, r.text
        audit = super_admin['session'].get(f'{BASE}/api/system-health/audit?limit=20', timeout=15).json()['items']
        assert any(a['action'] == 'SUPER_ADMIN_REVOKED' and a['target'] == target_username for a in audit)
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM users WHERE id=%s', (target_id,))


def test_cannot_demote_or_deactivate_the_last_active_super_admin(super_admin):
    me = super_admin['user_id']
    r = super_admin['session'].patch(f'{BASE}/api/users/{me}', json={'active': False}, timeout=15)
    # Blocked either by the last-super-admin guard or the pre-existing
    # cannot-lock-out-own-session guard -- either way it must NOT succeed.
    assert r.status_code == 409, r.text


def test_service_control_is_honest_when_deploy_agent_is_not_configured(super_admin):
    r = super_admin['session'].get(f'{BASE}/api/system-health/services', timeout=15)
    assert r.status_code == 200
    items = {i['id']: i for i in r.json()['items']}
    assert set(items) == {'mesflow_app', 'qa_center'}
    # compose.test.yml runs no Deploy Agent -- MESFLOW_DEPLOY_AGENT_URL is
    # unset, so this must report an honest UNKNOWN/unreachable state, never
    # a fabricated HEALTHY.
    for item in items.values():
        assert item['reachable'] is False
        assert item['status'] == 'UNKNOWN'

    r = super_admin['session'].post(f'{BASE}/api/system-health/services/mesflow_app/restart',
                                     json={'reason': 'integration test'}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body['ok'] is False  # never reports success when nothing actually restarted
    assert body['item']['result'] == 'DEPLOY_AGENT_UNREACHABLE'
    assert body['item']['error'] == 'DEPLOY_AGENT_NOT_CONFIGURED'

    r = super_admin['session'].post(f'{BASE}/api/system-health/services/mesflow_app/restart', json={}, timeout=15)
    assert r.status_code == 400 and r.json()['error'] == 'REASON_REQUIRED'

    r = super_admin['session'].post(f'{BASE}/api/system-health/services/not-a-real-service/restart',
                                     json={'reason': 'x'}, timeout=15)
    assert r.status_code == 404 and r.json()['error'] == 'UNKNOWN_SERVICE'

    audit = super_admin['session'].get(f'{BASE}/api/system-health/audit?limit=20', timeout=15).json()['items']
    assert any(a['action'] == 'RESTART_SERVICE' and a['target'] == 'mesflow_app' for a in audit)


def test_diagnostics_are_read_only_and_return_structured_result(db, super_admin):
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM work_sessions')
        before = cur.fetchone()['n']
    r = super_admin['session'].post(f'{BASE}/api/system-health/diagnostics/POSTGRESQL', timeout=15)
    assert r.status_code == 200
    data = r.json()['item']['data_json']
    assert data.get('connection') == 'OK'
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM work_sessions')
        assert cur.fetchone()['n'] == before  # diagnostics never mutate business data

    r = super_admin['session'].post(f'{BASE}/api/system-health/diagnostics/not-a-real-check', timeout=15)
    assert r.status_code == 404


def test_system_errors_are_independent_of_ng_quantity_and_session_exceptions(db, super_admin):
    """spec section 8: NG count and Session Exceptions must never leak into
    the System Errors feed -- it only ever reads action_logs ERROR/FAILED
    and kiosk_events ERROR/CRITICAL rows, neither of which has any notion
    of NG quantity or session-exception state."""
    marker = f'sc-error-test-{uuid.uuid4().hex[:8]}'
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO action_logs(trace_id,method,path,http_status,duration_ms,outcome,error_type,error_message) "
            "VALUES(%s,'GET','/api/does-not-exist',500,5,'ERROR','TestError',%s)",
            (marker, marker))
    try:
        items = super_admin['session'].get(f'{BASE}/api/system-health/errors?limit=500', timeout=15).json()['items']
        assert any(marker in (x.get('message') or '') for x in items)
        for x in items:
            assert x['component'] in ('MESFLOW', 'KIOSK')
            assert 'ng_quantity' not in x and 'exception_type' not in x and 'defect_qty' not in x
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM action_logs WHERE trace_id=%s', (marker,))
