"""AUTOLOGIN task (2026-09-04): /api/auth/test-auto-login persona
quick-switch (requirement #4) and the existing default (persona-less)
behavior stays a pure regression -- every one of the dozens of e2e specs
already calling this endpoint with no body must keep working unchanged.

Runs only where MESFLOW_ENV is non-production (this isolated stack sets
MESFLOW_ENV=test), so the environment guard is already open without
needing MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION -- that flag's own logic
is covered separately, DB-free, in test_autologin_guard_unit.py.
"""
import os
import uuid

import pytest
import requests
from werkzeug.security import generate_password_hash

pytestmark = pytest.mark.postgres

BASE_URL = os.environ.get('MESFLOW_BASE_URL', 'http://mesflow-test-api:8080').rstrip('/')
PERSONAS = ('admin', 'manager', 'supervisor', 'operator', 'viewer')


@pytest.fixture(scope='module', autouse=True)
def ensure_persona_users(db):
    """The 5 canonical persona-named accounts this feature resolves
    `?persona=<role>` against. 'admin' already exists (compose.test.yml's
    own bootstrap); the other 4 are created here if missing, matching the
    exact same literal-username-equals-role convention already used in
    every real MESFlow deployment's seed data (checked directly: local DEV
    and demo DBs both already have users named manager/supervisor/operator/
    viewer)."""
    for role in PERSONAS:
        if role == 'admin':
            continue
        db.execute(
            "INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) "
            "VALUES(%s,%s,%s,%s,TRUE,FALSE) ON CONFLICT (username) DO NOTHING",
            (role, role, generate_password_hash(f'unused-{uuid.uuid4().hex}'), role),
        )


def _fresh_session():
    """A brand-new, unauthenticated session -- deliberately not the shared
    `api` fixture, since that's already logged in as admin and this test
    needs to observe test-auto-login's own session bootstrap in isolation."""
    return requests.Session()


def test_default_persona_less_call_is_unchanged_regression():
    """The exact call shape every existing e2e spec uses -- no body at
    all. Must still resolve to MESFLOW_TEST_AUTO_LOGIN_USERNAME (admin,
    per compose.test.yml) exactly as before this task."""
    s = _fresh_session()
    r = s.post(f'{BASE_URL}/api/auth/test-auto-login', timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['ok'] is True
    assert body['user']['username'] == 'admin'
    assert body['user']['role'] == 'admin'
    me = s.get(f'{BASE_URL}/api/auth/me', timeout=10)
    assert me.json()['user']['role'] == 'admin'


@pytest.mark.parametrize('persona', PERSONAS)
def test_persona_switch_logs_in_as_that_role(persona):
    s = _fresh_session()
    r = s.post(f'{BASE_URL}/api/auth/test-auto-login', json={'persona': persona}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['user']['username'] == persona
    assert body['user']['role'] == persona
    me = s.get(f'{BASE_URL}/api/auth/me', timeout=10)
    assert me.status_code == 200
    assert me.json()['user']['role'] == persona


def test_persona_switch_via_query_param_also_works():
    """login.js passes it in the JSON body, but the route accepts a query
    param too (documented, used for a plain `curl`/manual check)."""
    s = _fresh_session()
    r = s.post(f'{BASE_URL}/api/auth/test-auto-login?persona=viewer', timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()['user']['role'] == 'viewer'


def test_invalid_persona_rejected():
    s = _fresh_session()
    r = s.post(f'{BASE_URL}/api/auth/test-auto-login', json={'persona': 'super_admin'}, timeout=10)
    # super_admin is deliberately excluded from quick-switching (see app.py) --
    # even though it's a real role, it's not in the fixed 5-persona allowlist.
    assert r.status_code == 400, r.text
    assert r.json()['error'] == 'AUTO_LOGIN_INVALID_PERSONA'
    me = s.get(f'{BASE_URL}/api/auth/me', timeout=10)
    assert me.status_code == 401  # the rejected attempt must not have logged anyone in


def test_login_page_reflects_noauto_override():
    s = _fresh_session()
    normal = s.get(f'{BASE_URL}/login', timeout=10)
    assert 'data-test-auto-login="1"' in normal.text
    manual = s.get(f'{BASE_URL}/login?noauto=1', timeout=10)
    assert 'data-test-auto-login="0"' in manual.text
