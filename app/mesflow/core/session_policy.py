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

from datetime import datetime, timedelta, timezone

from flask import session

from mesflow.core.config import settings

UTC = timezone.utc


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


def session_fields_for_login(user_id: int, username: str, role: str, *, kiosk_mode: bool = False) -> dict:
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
    return {
        'user_id': user_id, 'username': username, 'role': role, 'kiosk_mode': bool(kiosk_mode),
        'login_at': _iso(now), 'last_activity_at': _iso(now),
        'absolute_expires_at': _iso(now + timedelta(hours=settings.session_absolute_hours)),
    }


def start_session(user_id: int, username: str, role: str, *, kiosk_mode: bool = False) -> None:
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
    session.update(session_fields_for_login(user_id, username, role, kiosk_mode=kiosk_mode))


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

    session['last_activity_at'] = _iso(now)
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
