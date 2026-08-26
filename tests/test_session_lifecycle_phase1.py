"""Fix Plan Phase 1 -- login session idle/absolute expiry.

Pure unit tests against mesflow.core.session_policy directly (Flask test
request context, no DB, no HTTP server) -- fast, deterministic, and able to
control the wall clock precisely via monkeypatching session_policy._now(),
which integration/E2E tests covering this same behavior in real time cannot
do without sleeping for real minutes/hours.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from mesflow.core import session_policy

pytestmark = pytest.mark.unit


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = 'test-only-secret'
    return app


def _freeze(monkeypatch, moment: datetime):
    monkeypatch.setattr(session_policy, '_now', lambda: moment)


def test_new_login_is_valid_immediately(app, monkeypatch):
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'alice', 'operator')
        assert session_policy.validate_and_touch() is None


def test_idle_timeout_expires_and_clears_session(app, monkeypatch):
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'alice', 'operator')
        # Default idle window is 60 minutes -- 61 minutes of total silence
        # (no intervening validate_and_touch calls) must expire it.
        _freeze(monkeypatch, t0 + timedelta(minutes=61))
        from flask import session
        assert session.get('user_id') == 1  # sanity: cookie itself untouched by monkeypatch
        reason = session_policy.validate_and_touch()
        assert reason == 'SESSION_EXPIRED_IDLE'
        assert session.get('user_id') is None  # cleared


def test_absolute_timeout_expires_even_with_continuous_activity(app, monkeypatch):
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'alice', 'operator')
        # Touch the session every 30 minutes (well within the idle window)
        # all the way up to just past the 12h absolute ceiling.
        moment = t0
        for _ in range(24):
            moment = moment + timedelta(minutes=30)
            _freeze(monkeypatch, moment)
            reason = session_policy.validate_and_touch()
            if moment - t0 >= timedelta(hours=12):
                assert reason == 'SESSION_EXPIRED_ABSOLUTE'
                break
            assert reason is None
        else:
            pytest.fail('loop never reached the absolute ceiling')


def test_request_before_deadline_refreshes_idle_window(app, monkeypatch):
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'alice', 'operator')
        # 59 minutes in (still within the 60m idle window) -- a real request
        # arrives and must refresh last_activity_at.
        _freeze(monkeypatch, t0 + timedelta(minutes=59))
        assert session_policy.validate_and_touch() is None
        # Another 59 minutes from THAT touch (118 total from login) must
        # still be valid -- proves the idle window really did reset, not
        # just tolerate a slightly later absolute check.
        _freeze(monkeypatch, t0 + timedelta(minutes=118))
        assert session_policy.validate_and_touch() is None


def test_absolute_timeout_is_not_refreshed_by_activity(app, monkeypatch):
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'alice', 'operator')
        # Continuous activity every 30 minutes (never idle) all the way up
        # to the door of the 12h absolute ceiling.
        moment = t0
        while moment + timedelta(minutes=30) < t0 + timedelta(hours=12):
            moment += timedelta(minutes=30)
            _freeze(monkeypatch, moment)
            assert session_policy.validate_and_touch() is None
        # One more minute (well within the idle window that just got
        # refreshed) must still expire on the absolute ceiling -- activity
        # must never push it back.
        _freeze(monkeypatch, t0 + timedelta(hours=12, minutes=1))
        assert session_policy.validate_and_touch() == 'SESSION_EXPIRED_ABSOLUTE'


def test_logout_clears_session_immediately(app, monkeypatch):
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'alice', 'operator')
        session_policy.clear_session()
        assert session_policy.validate_and_touch() == 'NOT_LOGGED_IN'


def test_session_created_before_this_policy_existed_fails_closed(app, monkeypatch):
    """A session dict with user_id but none of the new expiry fields (either
    a cookie signed before this deploy, or some future code path that sets
    session['user_id'] directly without going through start_session()) must
    not get an implicit unlimited grace period."""
    from flask import session
    with app.test_request_context():
        session['user_id'] = 1
        session['username'] = 'alice'
        session['role'] = 'operator'
        reason = session_policy.validate_and_touch()
        assert reason == 'SESSION_MISSING_FIELDS'
        assert session.get('user_id') is None


def test_timezone_of_the_server_clock_does_not_change_the_outcome(app, monkeypatch):
    """The same instant expressed in two different tzinfo offsets must
    produce identical expiry decisions -- proves comparisons are done on
    absolute instants (via astimezone(UTC)), not on naive wall-clock math
    that a server-local timezone change could silently skew."""
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    hcm = timezone(timedelta(hours=7))
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'alice', 'operator')
        same_instant_in_hcm = (t0 + timedelta(minutes=61)).astimezone(hcm)
        _freeze(monkeypatch, same_instant_in_hcm)
        assert session_policy.validate_and_touch() == 'SESSION_EXPIRED_IDLE'


def test_kiosk_mode_uses_the_shorter_kiosk_idle_window(app, monkeypatch):
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'kiosk-op', 'operator', kiosk_mode=True)
        # Default kiosk idle window is 15 minutes -- 16 minutes of silence
        # must expire it, well before the normal 60-minute window would.
        _freeze(monkeypatch, t0 + timedelta(minutes=16))
        assert session_policy.validate_and_touch() == 'SESSION_EXPIRED_IDLE'


def test_session_status_is_read_only_and_never_touches_activity(app, monkeypatch):
    t0 = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    with app.test_request_context():
        _freeze(monkeypatch, t0)
        session_policy.start_session(1, 'alice', 'operator')
        _freeze(monkeypatch, t0 + timedelta(minutes=30))
        status = session_policy.session_status()
        assert status['login_at'] is not None
        assert status['idle_expires_at'] is not None
        from flask import session
        # last_activity_at must be untouched by session_status() -- still
        # the login-time value, not the 30-minutes-later read time.
        assert session.get('last_activity_at') == t0.isoformat()
