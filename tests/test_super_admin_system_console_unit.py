"""SUPER_ADMIN / IT System Console: static contracts + RBAC matrix.

RBAC checks below are in-process (mesflow.web.app.create_app() + Flask
test_client() + client.session_transaction() to plant a session, exactly
tests/test_template_create_real.py's authenticated_client() pattern) and
never touch PostgreSQL -- super_admin_required()/_require_valid_session()
short-circuit on the session role before any query runs, so every 403 case
here is real signal, not a DB-availability artifact. Positive-path (DB-
backed) behavior is covered separately in
tests/integration/test_super_admin_system_console.py.
"""
from pathlib import Path

from mesflow.core import session_policy
from mesflow.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]

NEW_ROUTES = [
    ('GET', '/api/system-health'),
    ('GET', '/api/system-health/errors'),
    ('GET', '/api/system-health/services'),
    ('POST', '/api/system-health/services/mesflow_app/restart'),
    ('GET', '/api/system-health/diagnostics'),
    ('POST', '/api/system-health/diagnostics/MESFLOW'),
    ('GET', '/api/system-health/audit'),
    ('GET', '/api/system-health/logs?source=mesflow'),
]

NON_SUPER_ADMIN_ROLES = ['admin', 'manager', 'supervisor', 'operator', 'viewer']


def _client_as(role):
    app = create_app()
    app.config.update(TESTING=True)
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(session_policy.session_fields_for_login(1, f'test-{role}', role))
    return client


def _call(client, method, path):
    if method == 'GET':
        return client.get(path)
    return client.post(path, json={})


def test_every_new_route_rejects_every_non_super_admin_role():
    for role in NON_SUPER_ADMIN_ROLES:
        client = _client_as(role)
        for method, path in NEW_ROUTES:
            resp = _call(client, method, path)
            assert resp.status_code == 403, f'{role} got {resp.status_code} (expected 403) on {method} {path}'
            body = resp.get_json()
            assert body is not None and body.get('ok') is False


def test_super_admin_role_is_not_rejected_by_the_gate():
    """Confirms the gate itself would let super_admin through (i.e. the 403s
    above are a real role check, not every request failing for an unrelated
    reason like a missing route). Some of these still fail past the gate in
    a DB-less environment (fetch_all with no connection) -- this only
    asserts we are NOT looking at the 403/FORBIDDEN the tests above check
    for, proving admin/manager/supervisor/operator are excluded specifically
    because they are not super_admin, not because the route rejects everyone.
    """
    client = _client_as('super_admin')
    for method, path in NEW_ROUTES:
        resp = _call(client, method, path)
        assert resp.status_code != 403, f'super_admin unexpectedly got 403 on {method} {path}'


def test_migration_is_additive_and_chained():
    t = (ROOT / 'app/migrations/versions/0043_super_admin_role.py').read_text()
    assert 'down_revision = "0042_session_review_and_exclusion"' in t
    assert "INSERT INTO rbac_roles" in t and "'super_admin'" in t
    assert 'op.create_table(\n        "system_audit_log"' in t
    assert 'op.drop_table("users")' not in t
    assert 'UPDATE users' not in t


def test_super_admin_required_has_no_admin_bypass():
    t = (ROOT / 'app/mesflow/web/auth.py').read_text()
    assert 'def super_admin_required(fn):' in t
    # The one property the whole feature depends on: this decorator must
    # check the literal role, never call _has_permission()/RBACRepository
    # (which is where the 'admin' blanket bypass lives).
    body = t.split('def super_admin_required(fn):', 1)[1].split('\ndef ', 1)[0]
    assert '"""' in body
    code = body.split('"""', 2)[2]  # drop the leading docstring; everything after is real code
    assert '_has_permission(' not in code
    assert "session.get('role')" in code and "!='super_admin'" in code


def test_admin_still_gets_ordinary_permissions_via_has_permission():
    t = (ROOT / 'app/mesflow/web/auth.py').read_text()
    assert "role in ('admin','super_admin')" in t


def test_users_route_blocks_ordinary_admin_from_granting_super_admin():
    t = (ROOT / 'app/mesflow/web/users.py').read_text()
    assert "role == 'super_admin' and _acting_role() != 'super_admin'" in t
    assert 'was_super_admin or becomes_super_admin' in t
    assert '_active_super_admin_count' in t
    assert "'super_admin'" in (ROOT / 'app/mesflow/web/users.py').read_text()


def test_bootstrap_is_env_gated_not_a_public_api():
    t = (ROOT / 'app/mesflow/cli.py').read_text()
    assert 'def seed_super_admin():' in t
    assert "MESFLOW_SUPER_ADMIN_USERNAME" in t and "MESFLOW_SUPER_ADMIN_PASSWORD" in t
    assert "'seed-super-admin':seed_super_admin" in t
    # Never reachable as an HTTP route -- confirm no web/*.py defines a
    # matching endpoint for it.
    for py in (ROOT / 'app/mesflow/web').glob('*.py'):
        assert 'seed_super_admin' not in py.read_text()
    entry = (ROOT / 'scripts/docker-entrypoint.sh').read_text()
    assert 'seed-super-admin' in entry


def test_service_allowlist_excludes_database_and_never_takes_raw_ids():
    t = (ROOT / 'app/mesflow/services/system_operations_service.py').read_text()
    assert "'mesflow_app'" in t and "'qa_center'" in t
    assert "'postgres'" not in t.replace('postgres-alpine', '')  # no postgres/db entry in the allowlist
    assert 'SERVICE_ALLOWLIST' in t


def test_frontend_gates_system_console_by_literal_super_admin_role():
    t = (ROOT / 'app/mesflow/web/static/app.js').read_text()
    assert 'const isSuperAdmin=' in t
    assert "SUPER_ADMIN_PAGES.has(page)?isSuperAdmin()" in t
    assert 'system-overview' in t and 'system-services' in t and 'system-audit' in t


def test_secrets_are_never_returned_as_configured_values():
    # settings.internal_api_token is only ever used to BUILD an outgoing
    # request header (X-MESFlow-Internal-Token: settings.internal_api_token)
    # -- it must never appear as a value being jsonify()'d back to the
    # browser, and no *_password/*_secret setting is read by these modules
    # at all.
    for relpath in ('app/mesflow/web/system_health.py', 'app/mesflow/services/system_operations_service.py'):
        t = (ROOT / relpath).read_text()
        for bad in ('admin_password', 'secret_key', 'database_url'):
            assert bad not in t
        for line in t.splitlines():
            if 'internal_api_token' in line:
                assert 'X-MESFlow-Internal-Token' in line, f'unexpected internal_api_token usage: {line!r}'
