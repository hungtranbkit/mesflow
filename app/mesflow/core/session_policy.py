"""Central login-session expiry policy.

Before this module, every auth decorator (mesflow.web.auth) only checked
`session.get('user_id')` -- there was no idle timeout, no absolute timeout,
no server-side expiry validation at all. The Flask session itself is a
client-side signed cookie (see web/app.py's `LocalhostAwareSessionInterface`,
a `SecureCookieSessionInterface` subclass) with no `PERMANENT_SESSION_LIFETIME`
set, so a browser that never closes kept the session alive indefinitely.

Design: rather than adding a server-side session store (a much bigger,
riskier change for a problem the signed cookie already solves), the expiry
fields themselves live INSIDE the signed session cookie
(`login_at`/`last_activity_at`/`absolute_expires_at`), validated against the
server's own clock on every request. A tampered value fails the cookie's
HMAC signature before Flask ever hands it to this module, and a value this
module never wrote (a session created before this policy existed, or one an
older code path still sets directly) is treated as already-expired -- fail
closed, not an implicit unlimited grace period.

Being a signed cookie, not a server-side table, this is naturally
restart-safe (nothing server-side to lose) and needs no cleanup job.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

from flask import session

from mesflow.core.config import settings

UTC = timezone.utc

logger = logging.getLogger(__name__)


def auth_epoch(password_hash: str, active: bool, session_epoch: int = 0) -> str:
    """A short, opaque stamp of the credential state a session was issued under.

    A signed cookie cannot be revoked server-side on its own: it stays valid
    until it expires, so before this existed a changed password left every old
    cookie working. This closes that without a migration and without a session
    table -- the credential state IS the version. Change the password and the
    hash changes; deactivate the account and `active` changes; either way every
    session issued under the old state stops validating.

    `session_epoch` (users.session_epoch, migration 0050) is the part a manual
    logout bumps: a password change moves the hash, but logging out does not,
    so without an explicit version a copy of the cookie taken before logout
    kept working. Measured, not assumed.

    Keyed with the app secret and truncated, so the cookie carries no material
    derived from the password hash that would be useful off-server, and the
    value is meaningless to anyone who cannot already forge the cookie
    signature. Never logged.
    """
    message = f'{password_hash}:{bool(active)}:{int(session_epoch or 0)}'.encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()[:16]


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # A naive timestamp could never have been written by this module
        # (start_session always writes an aware UTC isoformat) -- treat as
        # untrusted/corrupt rather than guessing a timezone for it.
        return None
    return parsed.astimezone(UTC)


def _idle_window_minutes(kiosk_mode: bool) -> int:
    return settings.kiosk_session_idle_minutes if kiosk_mode else settings.session_idle_minutes


def epoch_for_user(user: dict) -> str:
    """Build the credential stamp from a user row.

    A helper rather than three call sites reaching into the row themselves:
    the auto-login route must not handle password material at all (guarded by
    tests/test_autologin_session_timeline_v65813.py, which asserts the string
    "password_hash" never appears in that route), and login code has no reason
    to know how the stamp is composed.
    """
    return auth_epoch(str(user.get('password_hash') or ''), bool(user.get('active')),
                      user.get('session_epoch') or 0)


def session_fields_for_login(user_id: int, username: str, role: str, *, kiosk_mode: bool = False,
                             epoch: str = '') -> dict:
    """Pure computation of what a fresh login writes into the session --
    factored out of start_session() so a test helper using Flask's
    `client.session_transaction()` (a bare dict-like session object, NOT
    reachable through the `flask.session` proxy this module normally
    writes through -- that proxy requires an active request context,
    which session_transaction()'s special block deliberately isn't one)
    can populate a realistic logged-in session without duplicating this
    module's field set and risking it drifting from what a real login
    actually writes. Real request-handling code should call start_session()
    below, not this directly."""
    now = _now()
    fields = {
        'user_id': user_id, 'username': username, 'role': role, 'kiosk_mode': bool(kiosk_mode),
        'login_at': _iso(now), 'last_activity_at': _iso(now),
        'absolute_expires_at': _iso(now + timedelta(hours=settings.session_absolute_hours)),
    }
    if epoch:
        fields['auth_epoch'] = epoch
    return fields


def start_session(user_id: int, username: str, role: str, *, kiosk_mode: bool = False,
                  epoch: str = '') -> None:
    """Call exactly once, right after password verification succeeds.

    kiosk_mode picks a separate (default shorter) idle window for a
    shared/walk-up terminal login -- a normal office login and a kiosk
    terminal login should not share one timeout: a supervisor's browser
    tab realistically sits idle between checks, while a shared terminal
    left logged in is a real handover/security risk that should time out
    fast. The caller decides kiosk_mode (e.g. the login request body
    carries it from a kiosk-specific login page); this module never
    guesses it from the route.
    """
    session.update(session_fields_for_login(user_id, username, role, kiosk_mode=kiosk_mode, epoch=epoch))
    # Flask only sends Max-Age/Expires for a PERMANENT session. Without this the
    # cookie dies the moment the browser closes, which no server-side TTL can
    # fix. Kiosk stays non-permanent on purpose: a shared walk-up terminal must
    # not keep a cookie on disk after the operator leaves.
    session.permanent = not bool(kiosk_mode)


def clear_session() -> None:
    session.clear()


def validate_and_touch() -> str | None:
    """Validate the CURRENT request's session against idle + absolute expiry.

    Returns None if the session is valid (and, as a side effect, refreshes
    last_activity_at -- so this must only be called once expiry has been
    confirmed acceptable, never speculatively). Returns a reason code and
    clears the session if invalid:

      'NOT_LOGGED_IN'          -- no user_id in session at all
      'SESSION_MISSING_FIELDS' -- user_id present but login_at/last_activity_at/
                                   absolute_expires_at missing or unparseable
                                   (a session from before this policy existed,
                                   or written by a code path that bypassed
                                   start_session()) -- fails closed
      'SESSION_EXPIRED_ABSOLUTE' -- past login_at + MESFLOW_SESSION_ABSOLUTE_HOURS,
                                     regardless of activity
      'SESSION_EXPIRED_IDLE'     -- past last_activity_at + idle window

    Absolute expiry is checked BEFORE idle expiry and is never refreshed by
    activity (§ "absolute timeout không được refresh" in the fix plan) --
    an idle-refreshed session still dies at the hard ceiling.
    """
    if not session.get('user_id'):
        return 'NOT_LOGGED_IN'

    absolute_expires_at = _parse(session.get('absolute_expires_at'))
    last_activity_at = _parse(session.get('last_activity_at'))
    if absolute_expires_at is None or last_activity_at is None:
        session.clear()
        return 'SESSION_MISSING_FIELDS'

    now = _now()
    if now >= absolute_expires_at:
        session.clear()
        return 'SESSION_EXPIRED_ABSOLUTE'

    idle_minutes = _idle_window_minutes(bool(session.get('kiosk_mode')))
    if now >= last_activity_at + timedelta(minutes=idle_minutes):
        session.clear()
        return 'SESSION_EXPIRED_IDLE'

    revoked = _revocation_reason()
    if revoked:
        session.clear()
        return revoked

    session['last_activity_at'] = _iso(now)
    return None


def _revocation_reason() -> str | None:
    """Has the credential this session was issued under changed since?

    Returns a reason code to invalidate, or None to keep the session.

    Fails OPEN on an infrastructure error and CLOSED on an actual mismatch.
    That asymmetry is deliberate: a transient database blip must not log every
    user in the factory out at once -- that is the very failure this work
    exists to stop -- while a real password change or deactivation must take
    effect. A session issued before this field existed carries no auth_epoch
    and is left alone rather than force-logging everyone out on deploy; it
    picks the field up at its next login.
    """
    expected = session.get('auth_epoch')
    if not expected:
        return None
    try:
        from mesflow.db.repositories.user_repository import UserRepository
        user = UserRepository().get_by_id(int(session['user_id']))
    except Exception:
        logger.warning('session revocation check skipped: user lookup failed')
        return None
    if not user:
        return 'SESSION_USER_GONE'
    if not user.get('active'):
        return 'SESSION_REVOKED'
    current = auth_epoch(str(user.get('password_hash') or ''), True, user.get('session_epoch') or 0)
    if not hmac.compare_digest(str(expected), current):
        return 'SESSION_REVOKED'
    return None


def session_status() -> dict:
    """Read-only introspection (e.g. for a /me-style endpoint or a test) --
    never mutates, never touches last_activity_at."""
    login_at = _parse(session.get('login_at'))
    last_activity_at = _parse(session.get('last_activity_at'))
    absolute_expires_at = _parse(session.get('absolute_expires_at'))
    idle_minutes = _idle_window_minutes(bool(session.get('kiosk_mode')))
    idle_expires_at = last_activity_at + timedelta(minutes=idle_minutes) if last_activity_at else None
    return {
        'login_at': login_at.isoformat() if login_at else None,
        'last_activity_at': last_activity_at.isoformat() if last_activity_at else None,
        'absolute_expires_at': absolute_expires_at.isoformat() if absolute_expires_at else None,
        'idle_expires_at': idle_expires_at.isoformat() if idle_expires_at else None,
        'kiosk_mode': bool(session.get('kiosk_mode')),
    }
