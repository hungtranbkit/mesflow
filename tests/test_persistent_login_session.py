"""Login must survive a refresh, a browser close, a restart and a deploy.

ROOT CAUSES, measured on the running app before this change — not guessed:

  1. The cookie had no Max-Age and no Expires:
         Set-Cookie: session=...; HttpOnly; Path=/; SameSite=Lax
     Flask only emits a lifetime for a PERMANENT session, and nothing ever set
     `session.permanent`. So it was a browser-session cookie: closing the
     browser deleted it, and no server-side TTL could change that.
  2. The absolute ceiling was 12 hours and the idle window 60 minutes, so even
     a continuously working user was pushed back to the login page twice a day.
  3. There was no revocation at all. A changed password updated password_hash
     and nothing else; every previously issued cookie kept working until it
     expired on its own.

What was already fine and is deliberately unchanged: the signing key comes from
MESFLOW_SECRET_KEY and production refuses the placeholder (config.py), and the
session is a signed cookie with no server-side store — so restart and image
redeploy were already survivable as long as the key is stable. Those are pinned
here so a future change cannot quietly regress them.

NEGATIVE PROOF: drop `session.permanent` and test_cookie_is_persistent_not_browser_session
fails; drop the epoch check and test_password_change_invalidates_existing_sessions
fails; shorten the defaults back and test_default_lifetimes_are_long_enough fails.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from mesflow.core import session_policy
from mesflow.core.config import settings


# --------------------------------------------------------------- unit level

def test_auth_epoch_changes_with_the_password_active_and_session_version():
    a = session_policy.auth_epoch('hash-one', True, 0)
    assert a == session_policy.auth_epoch('hash-one', True, 0), 'must be stable for the same state'
    assert a != session_policy.auth_epoch('hash-two', True, 0), 'password change must change the epoch'
    assert a != session_policy.auth_epoch('hash-one', False, 0), 'deactivation must change the epoch'
    assert a != session_policy.auth_epoch('hash-one', True, 1), 'logout must change the epoch'


def test_auth_epoch_leaks_neither_the_hash_nor_the_secret():
    secret = settings.secret_key
    epoch = session_policy.auth_epoch('super-secret-hash-value', True)
    assert 'super-secret-hash-value' not in epoch
    assert secret not in epoch
    assert len(epoch) == 16 and all(c in '0123456789abcdef' for c in epoch)


def test_default_lifetimes_are_long_enough_for_a_working_week():
    """14-30 days, per the requirement."""
    assert settings.session_absolute_hours >= 14 * 24, settings.session_absolute_hours
    assert settings.session_absolute_hours <= 31 * 24, 'an unbounded ceiling is not the ask'
    assert settings.session_idle_minutes >= 14 * 24 * 60, settings.session_idle_minutes


def test_kiosk_idle_window_was_not_widened():
    """Convenience for an office browser must not weaken a shared terminal."""
    assert settings.kiosk_session_idle_minutes <= 30, settings.kiosk_session_idle_minutes


def test_login_fields_carry_the_epoch():
    fields = session_policy.session_fields_for_login(1, 'admin', 'admin', epoch='deadbeefdeadbeef')
    assert fields['auth_epoch'] == 'deadbeefdeadbeef'
    assert fields['login_at'] and fields['last_activity_at'] and fields['absolute_expires_at']


# ---------------------------------------------------------- request level

@pytest.fixture
def app(monkeypatch):
    from mesflow.web import app as app_module
    application = app_module.create_app()
    application.config.update(TESTING=True)
    return application


def _set_session(client, **extra):
    fields = session_policy.session_fields_for_login(1, 'admin', 'admin', epoch=extra.pop('epoch', ''))
    fields.update(extra)
    with client.session_transaction() as sess:
        sess.update(fields)


def test_cookie_is_persistent_not_browser_session(app, monkeypatch):
    """The defect that caused "closing the browser logs me out"."""
    from mesflow.web import app as app_module
    monkeypatch.setattr(app_module, 'UserRepository', lambda: _FakeUsers('hash-one', True))
    monkeypatch.setattr(app_module, 'RBACRepository', lambda: _FakeRBAC())
    monkeypatch.setattr(app_module, 'AuditRepository', lambda: _FakeAudit())
    monkeypatch.setattr(app_module, 'check_password_hash', lambda *a: True)
    client = app.test_client()
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'x'})
    assert r.status_code == 200, r.data
    cookie = r.headers.get('Set-Cookie', '')
    assert 'Expires=' in cookie or 'Max-Age=' in cookie, (
        'session cookie has no lifetime -- the browser will delete it on close. '
        f'Got: {cookie}'
    )
    assert 'HttpOnly' in cookie
    assert 'Path=/' in cookie
    assert 'SameSite=Lax' in cookie


def test_kiosk_login_stays_a_browser_session_cookie(app, monkeypatch):
    """A shared walk-up terminal must not leave a durable cookie behind."""
    from mesflow.web import app as app_module
    monkeypatch.setattr(app_module, 'UserRepository', lambda: _FakeUsers('hash-one', True))
    monkeypatch.setattr(app_module, 'RBACRepository', lambda: _FakeRBAC())
    monkeypatch.setattr(app_module, 'AuditRepository', lambda: _FakeAudit())
    monkeypatch.setattr(app_module, 'check_password_hash', lambda *a: True)
    r = app.test_client().post('/api/auth/login', json={'username': 'admin', 'password': 'x', 'kiosk_mode': True})
    cookie = r.headers.get('Set-Cookie', '')
    assert 'Expires=' not in cookie and 'Max-Age=' not in cookie, cookie


def test_secure_flag_follows_the_cookie_secure_setting(monkeypatch):
    from mesflow.web import app as app_module
    monkeypatch.setattr(app_module, 'settings', dataclasses.replace(settings, cookie_secure=True))
    application = app_module.create_app()
    assert application.config['SESSION_COOKIE_SECURE'] is True
    assert application.config['SESSION_COOKIE_HTTPONLY'] is True
    assert application.config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    assert application.config['PERMANENT_SESSION_LIFETIME'] == timedelta(hours=settings.session_absolute_hours)


# ------------------------------------------------------------- revocation

class _FakeUsers:
    def __init__(self, password_hash, active, session_epoch=0):
        self._u = {'id': 1, 'username': 'admin', 'role': 'admin', 'active': active,
                   'password_hash': password_hash, 'must_change_password': False,
                   'session_epoch': session_epoch}
        self.bumped = 0

    def bump_session_epoch(self, _id):
        self.bumped += 1
        self._u['session_epoch'] += 1

    def get_by_id(self, _id):
        return dict(self._u)

    def get_by_username(self, _n):
        return dict(self._u)


class _FakeRBAC:
    def permissions_for_role(self, _r):
        return []


class _FakeAudit:
    def log(self, *a, **k):
        return None


def _validate_with(monkeypatch, stored_epoch, current_hash, active=True, session_epoch=0):
    from mesflow.web import app as app_module
    monkeypatch.setattr('mesflow.db.repositories.user_repository.UserRepository',
                        lambda: _FakeUsers(current_hash, active, session_epoch))
    application = app_module.create_app()
    application.config.update(TESTING=True)
    client = application.test_client()
    _set_session(client, epoch=stored_epoch)
    with application.test_request_context('/'):
        from flask import session as flask_session
        flask_session.update(session_policy.session_fields_for_login(1, 'admin', 'admin', epoch=stored_epoch))
        return session_policy.validate_and_touch()


def test_unchanged_password_keeps_the_session(monkeypatch):
    epoch = session_policy.auth_epoch('hash-one', True, 0)
    assert _validate_with(monkeypatch, epoch, 'hash-one') is None


def test_logout_elsewhere_invalidates_this_session(monkeypatch):
    """A cookie captured before logout must stop validating.

    The stateless cookie cannot be taken back on its own; users.session_epoch
    (migration 0050) is what makes the revocation possible.
    """
    epoch = session_policy.auth_epoch('hash-one', True, 0)
    assert _validate_with(monkeypatch, epoch, 'hash-one', session_epoch=1) == 'SESSION_REVOKED'


def test_password_change_invalidates_existing_sessions(monkeypatch):
    epoch = session_policy.auth_epoch('hash-one', True, 0)
    assert _validate_with(monkeypatch, epoch, 'hash-two-after-change') == 'SESSION_REVOKED'


def test_deactivating_the_account_invalidates_existing_sessions(monkeypatch):
    epoch = session_policy.auth_epoch('hash-one', True, 0)
    assert _validate_with(monkeypatch, epoch, 'hash-one', active=False) == 'SESSION_REVOKED'


def test_a_database_error_does_not_log_everyone_out(monkeypatch):
    """Fail open on infrastructure, closed on a real mismatch.

    A transient DB blip logging out every user at once is the exact failure
    this work exists to remove.
    """
    from mesflow.web import app as app_module

    class _Boom:
        def get_by_id(self, _id):
            raise RuntimeError('db down')

    monkeypatch.setattr('mesflow.db.repositories.user_repository.UserRepository', lambda: _Boom())
    application = app_module.create_app()
    with application.test_request_context('/'):
        from flask import session as flask_session
        flask_session.update(session_policy.session_fields_for_login(
            1, 'admin', 'admin', epoch=session_policy.auth_epoch('hash-one', True, 0)))
        assert session_policy.validate_and_touch() is None


def test_sessions_issued_before_this_field_are_not_force_logged_out(monkeypatch):
    """Deploying this change must not log the whole factory out."""
    from mesflow.web import app as app_module
    application = app_module.create_app()
    with application.test_request_context('/'):
        from flask import session as flask_session
        fields = session_policy.session_fields_for_login(1, 'admin', 'admin')
        assert 'auth_epoch' not in fields
        flask_session.update(fields)
        assert session_policy.validate_and_touch() is None


# ---------------------------------------------------------------- expiry

def test_expired_absolute_is_refused(monkeypatch):
    from mesflow.web import app as app_module
    application = app_module.create_app()
    with application.test_request_context('/'):
        from flask import session as flask_session
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        fields = session_policy.session_fields_for_login(1, 'admin', 'admin')
        fields['absolute_expires_at'] = past.isoformat()
        flask_session.update(fields)
        assert session_policy.validate_and_touch() == 'SESSION_EXPIRED_ABSOLUTE'


def test_missing_fields_fail_closed(monkeypatch):
    from mesflow.web import app as app_module
    application = app_module.create_app()
    with application.test_request_context('/'):
        from flask import session as flask_session
        flask_session.update({'user_id': 1, 'username': 'admin', 'role': 'admin'})
        assert session_policy.validate_and_touch() == 'SESSION_MISSING_FIELDS'


def test_tampered_cookie_is_rejected_by_the_signature(app, monkeypatch):
    """A forged cookie must never reach the policy layer at all."""
    from mesflow.web import app as app_module
    monkeypatch.setattr(app_module, 'UserRepository', lambda: _FakeUsers('hash-one', True))
    monkeypatch.setattr(app_module, 'RBACRepository', lambda: _FakeRBAC())
    monkeypatch.setattr(app_module, 'AuditRepository', lambda: _FakeAudit())
    monkeypatch.setattr(app_module, 'check_password_hash', lambda *a: True)
    client = app.test_client()
    client.post('/api/auth/login', json={'username': 'admin', 'password': 'x'})
    client.set_cookie('session', 'this.is.not.a.valid.signed.cookie')
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302 and '/login' in r.headers['Location']


# ------------------------------------------------- restart / redeploy

def test_a_cookie_from_one_app_instance_works_on_a_fresh_one(monkeypatch):
    """Restart and image redeploy must not log anyone out.

    Two separate create_app() instances stand in for "before" and "after" a
    container recreate: nothing about the session lives in the process, so a
    cookie minted by one must authenticate against the other. What makes that
    true is the signing key coming from MESFLOW_SECRET_KEY rather than being
    generated per boot -- the property this asserts.

    Verified additionally against a real container recreate on the lane stack:
    the same cookie still redirected "/" to /app afterwards.
    """
    from mesflow.web import app as app_module
    users = _FakeUsers('hash-one', True)
    monkeypatch.setattr(app_module, 'UserRepository', lambda: users)
    monkeypatch.setattr('mesflow.db.repositories.user_repository.UserRepository', lambda: users)
    monkeypatch.setattr(app_module, 'RBACRepository', lambda: _FakeRBAC())
    monkeypatch.setattr(app_module, 'AuditRepository', lambda: _FakeAudit())
    monkeypatch.setattr(app_module, 'check_password_hash', lambda *a: True)

    before = app_module.create_app(); before.config.update(TESTING=True)
    client = before.test_client()
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'x'}).status_code == 200
    cookie = client.get_cookie('session')
    assert cookie is not None

    after = app_module.create_app(); after.config.update(TESTING=True)
    fresh = after.test_client()
    fresh.set_cookie('session', cookie.value)
    response = fresh.get('/', follow_redirects=False)
    assert response.status_code == 302, response.status_code
    assert '/app' in response.headers['Location'], (
        'a cookie minted before the restart no longer authenticates -- the '
        'signing key is not stable across boots'
    )


def test_signing_key_is_not_generated_per_boot():
    """The failure mode this whole area is most sensitive to.

    A random per-boot key would invalidate every cookie on every restart and
    deploy. It comes from the environment, and production refuses the
    placeholder value outright (config.py).
    """
    import inspect
    from mesflow.core import config as config_module
    source = inspect.getsource(config_module)
    assert 'MESFLOW_SECRET_KEY' in source
    for generator in ('token_hex', 'token_urlsafe', 'uuid4()', 'os.urandom'):
        assert generator not in source.split('secret_key')[1][:400], (
            f'secret_key looks generated with {generator} -- it must come from config'
        )
    assert 'MESFLOW_SECRET_KEY must be configured for production' in source
