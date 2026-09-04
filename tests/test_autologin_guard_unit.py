"""AUTOLOGIN task (2026-09-04): _auto_login_allowed() and the
/api/auth/test-auto-login guard, in-process (mesflow.web.app.create_app()
+ Flask test_client(), same pattern as test_super_admin_system_console_unit.py)
-- no PostgreSQL. Every case here short-circuits on settings before any DB
query would run, so a real Postgres would never even be reached; that
positive (DB-backed) path -- persona lookup actually finding a user -- is
covered in tests/integration/test_autologin_persona.py instead.
"""
import dataclasses

from mesflow.web import app as app_module


def _client_with(**overrides):
    monkey_settings = dataclasses.replace(app_module.settings, **overrides)
    return monkey_settings


def test_non_production_default_off_flag_still_refused(monkeypatch):
    # environment != production, but MESFLOW_TEST_AUTO_LOGIN itself is off
    # (the default) -- must stay refused. This is the flag's own default-off
    # requirement (#1), independent of the environment guard.
    monkeypatch.setattr(app_module, 'settings', _client_with(environment='local', test_auto_login=False))
    app = app_module.create_app()
    app.config.update(TESTING=True)
    r = app.test_client().post('/api/auth/test-auto-login')
    assert r.status_code == 403
    assert r.get_json()['error'] == 'AUTO_LOGIN_DISABLED'


def test_non_production_enabled_flag_passes_the_guard(monkeypatch):
    # environment != production (e.g. local/test/sandbox) is always allowed
    # once the flag itself is on -- no override needed. Uses a username
    # that doesn't exist so this never touches Postgres, only exercises the
    # guard (a 503 here proves we got PAST the environment/flag checks and
    # into the DB-lookup step, which is exactly what this test verifies).
    monkeypatch.setattr(app_module, 'settings', _client_with(
        environment='local', test_auto_login=True, test_auto_login_username='no-such-user-xyz'))
    app = app_module.create_app()
    app.config.update(TESTING=True)
    r = app.test_client().post('/api/auth/test-auto-login')
    assert r.status_code == 503
    assert r.get_json()['error'] == 'AUTO_LOGIN_USER_NOT_FOUND'


def test_production_without_override_is_refused_even_with_flag_on(monkeypatch):
    # The exact scenario requirement #2 is about: MESFLOW_ENV=production
    # (real production, or prodtest/demo that forgot the override) with
    # MESFLOW_TEST_AUTO_LOGIN=1 -- must refuse, fail-closed, never reach
    # the DB.
    monkeypatch.setattr(app_module, 'settings', _client_with(
        environment='production', test_auto_login=True, test_auto_login_allow_production=False))
    app = app_module.create_app()
    app.config.update(TESTING=True)
    r = app.test_client().post('/api/auth/test-auto-login')
    assert r.status_code == 403
    assert r.get_json()['error'] == 'AUTO_LOGIN_DISABLED_PRODUCTION'


def test_production_with_explicit_override_passes_the_guard(monkeypatch):
    # prodtest/demo's actual intended configuration: MESFLOW_ENV=production
    # (compose.yml hardcodes it) but MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1
    # explicitly set too -- the guard must let this through (again proven by
    # reaching the DB-lookup 503, not by a 403).
    monkeypatch.setattr(app_module, 'settings', _client_with(
        environment='production', test_auto_login=True, test_auto_login_allow_production=True,
        test_auto_login_username='no-such-user-xyz'))
    app = app_module.create_app()
    app.config.update(TESTING=True)
    r = app.test_client().post('/api/auth/test-auto-login')
    assert r.status_code == 503
    assert r.get_json()['error'] == 'AUTO_LOGIN_USER_NOT_FOUND'


def test_invalid_persona_rejected_before_any_db_lookup(monkeypatch):
    monkeypatch.setattr(app_module, 'settings', _client_with(environment='local', test_auto_login=True))
    app = app_module.create_app()
    app.config.update(TESTING=True)
    r = app.test_client().post('/api/auth/test-auto-login', json={'persona': 'root'})
    assert r.status_code == 400
    body = r.get_json()
    assert body['error'] == 'AUTO_LOGIN_INVALID_PERSONA'
    assert set(body['allowed']) == {'admin', 'manager', 'supervisor', 'operator', 'viewer'}


def test_login_page_noauto_query_param_suppresses_auto_trigger(monkeypatch):
    monkeypatch.setattr(app_module, 'settings', _client_with(environment='local', test_auto_login=True))
    app = app_module.create_app()
    app.config.update(TESTING=True)
    client = app.test_client()
    normal = client.get('/login')
    assert b'data-test-auto-login="1"' in normal.data
    manual = client.get('/login?noauto=1')
    assert b'data-test-auto-login="0"' in manual.data
