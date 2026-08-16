"""System log/audit separation (reports/SYSTEM_LOG_AUDIT_SEPARATION.md):
MESFlow's Business Audit Trail (/api/audit-logs) keeps its own dedicated
permission, filters correctly, and login/security events are captured as
BUSINESS_AUDIT rows -- never a password.
"""
import uuid
import pytest
from werkzeug.security import generate_password_hash

pytestmark = pytest.mark.postgres
BASE = 'http://mesflow-test-api:8080'


def _create_user(db, role, password='Test@123456'):
    u = f'v72-{role}-{uuid.uuid4()}'
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,%s,%s,%s,TRUE,FALSE) RETURNING id",
            (u, role, generate_password_hash(password), role))
        uid = cur.fetchone()['id']
    return u, password, uid


def test_login_success_creates_business_audit_row_without_password(db, api):
    row = db.execute("SELECT * FROM audit_logs WHERE action='LOGIN_SUCCESS' ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    assert 'Admin@123456' not in (row['details_json'] or '')


def test_login_failed_creates_business_audit_row(db):
    import requests
    s = requests.Session()
    r = s.post(f'{BASE}/api/auth/login', json={'username': 'admin', 'password': 'definitely-wrong-password'})
    assert r.status_code == 401
    row = db.execute(
        "SELECT * FROM audit_logs WHERE action='LOGIN_FAILED' AND actor_username='admin' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert 'definitely-wrong-password' not in (row['details_json'] or '')


def test_business_audit_endpoint_requires_business_audit_view_permission(db):
    import requests
    # operator role: not granted business_audit.view in the seed migration
    u, p, uid = _create_user(db, 'operator')
    try:
        s = requests.Session()
        assert s.post(f'{BASE}/api/auth/login', json={'username': u, 'password': p}).status_code == 200
        r = s.get(f'{BASE}/api/audit-logs')
        assert r.status_code == 403
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM users WHERE id=%s', (uid,))


def test_business_audit_endpoint_allows_manager_and_supervisor(db):
    import requests
    for role in ('manager', 'supervisor'):
        u, p, uid = _create_user(db, role)
        try:
            s = requests.Session()
            assert s.post(f'{BASE}/api/auth/login', json={'username': u, 'password': p}).status_code == 200
            r = s.get(f'{BASE}/api/audit-logs')
            assert r.status_code == 200, f'{role}: {r.text}'
        finally:
            with db.cursor() as cur:
                cur.execute('DELETE FROM users WHERE id=%s', (uid,))


def test_business_audit_filters_by_action_and_time_range(api):
    r = api.get(f'{BASE}/api/audit-logs?action=LOGIN_SUCCESS&limit=5', timeout=10)
    assert r.status_code == 200, r.text
    items = r.json()['items']
    assert all(x['action'] == 'LOGIN_SUCCESS' for x in items)

    r2 = api.get(f'{BASE}/api/audit-logs?date_from=2099-01-01', timeout=10)
    assert r2.status_code == 200
    assert r2.json()['items'] == []  # future date range -> nothing


def test_business_audit_never_contains_technical_action_log_rows(api):
    """section 11: technical server/container errors must not pollute this
    screen -- confirmed by construction (audit_logs is a separate table
    from action_logs/error_traces, never fed from HTTP tracing)."""
    r = api.get(f'{BASE}/api/audit-logs?limit=200', timeout=10)
    actions = {x['action'] for x in r.json()['items']}
    # technical outcome/HTTP-status vocabulary from action_logs must never appear
    assert not (actions & {'ERROR', 'FAILED', 'SLOW', 'SUCCESS'})
