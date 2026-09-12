"""The public Kiosk boundary, asserted from source -- no DB, no live stack.

Business owner decision (2026-09-12): the Kiosk web surface is a PUBLIC
operational surface. A workshop machine opens /kiosk directly, has never
logged in, has no session cookie, and must keep working across a reload;
the operator is identified by the employee badge they scan.

The risk this file exists to contain is the OTHER half of that decision:
"open the kiosk" must never quietly become "open the app". So every check
below is paired -- one that the kiosk surface is reachable anonymously, one
that a named management surface still is not.

The live end-to-end proof is tests/integration/
test_p0_scan_auth_and_support_op_rollups.py; this file is the fast guard
that fails in CI without Postgres.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.static

APP = Path(__file__).resolve().parents[1] / 'app/mesflow/web'
AUTH = (APP / 'auth.py').read_text(encoding='utf-8')
KIOSK = (APP / 'kiosk.py').read_text(encoding='utf-8')
KIOSK_BOARD = (APP / 'kiosk_board.py').read_text(encoding='utf-8')
APP_PY = (APP / 'app.py').read_text(encoding='utf-8')

# The public kiosk surface, exhaustively. Anything not on this list is not
# part of the boundary, and adding to it is a deliberate security decision.
PUBLIC_KIOSK_ROUTES = {
    "@bp.get('/kiosk')",
    "@bp.get('/kiosk/employee-productivity')",
    "@bp.get('/api/kiosk-web/health')",
    "@bp.post('/api/kiosk-web/heartbeat')",
    "@bp.post('/api/kiosk-web/scan')",
    "@bp.post('/api/kiosk-web/start')",
    "@bp.post('/api/kiosk-web/finish/<int:session_id>')",
}

GATED_DECORATORS = ('@login_required', '@admin_required', '@super_admin_required',
                    '@roles_required', '@permission_required', '@production_client_required')


def _decorators_after(text: str, route: str) -> list[str]:
    """Every decorator line between a route decorator and its def."""
    lines = text[text.index(route):].splitlines()
    out = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith('def '):
            return out
        if stripped.startswith('@'):
            out.append(stripped)
    raise AssertionError(f'no def found after {route}')


def test_every_public_kiosk_route_carries_no_login_gate():
    for route in sorted(PUBLIC_KIOSK_ROUTES):
        decorators = _decorators_after(KIOSK, route)
        for gate in GATED_DECORATORS:
            assert not any(d.startswith(gate) for d in decorators), \
                f'{route} is on the public kiosk surface but carries {gate}'


def test_the_three_write_routes_are_marked_public_not_merely_undecorated():
    """Requirement 5: one explicit boundary, not scattered missing decorators.

    An undecorated route is indistinguishable from a forgotten one. @kiosk_public
    makes the whole surface a single greppable list and is the thing a future
    audit reads as intent.
    """
    for route in ("@bp.post('/api/kiosk-web/scan')",
                  "@bp.post('/api/kiosk-web/start')",
                  "@bp.post('/api/kiosk-web/finish/<int:session_id>')"):
        assert '@kiosk_public' in _decorators_after(KIOSK, route), \
            f'{route} must be explicitly marked @kiosk_public'


def test_kiosk_public_allows_anonymous_but_still_rejects_a_revoked_token():
    """An OPTIONAL device token that is presented must still be a valid one --
    otherwise disabling a kiosk in /kiosk-management would silently downgrade
    that machine to anonymous instead of cutting it off."""
    block = AUTH[AUTH.index('def kiosk_public'):AUTH.index('def production_client_required')]
    assert 'X-Kiosk-Token' in block
    assert 'verify_token_any' in block
    assert "if token:" in block, 'a missing token must fall through, not fail'
    # No session/login check anywhere in the decorator.
    assert '_require_valid_session' not in block
    assert 'validate_and_touch' not in block
    assert "session.get('user_id')" not in block


def test_the_employee_roster_stays_signed_in_only():
    """demo-data dumps every badge QR -- a credential. A real terminal never
    calls it (the scanner types into the input), so it is not part of the
    minimum the kiosk needs to operate."""
    assert '@login_required' in _decorators_after(KIOSK, "@bp.get('/api/kiosk-web/demo-data')")


def test_the_control_room_board_apis_were_not_opened():
    """The kiosk DASHBOARD is a page inside the authenticated /app SPA
    (dashboard.view), not a public URL, so its APIs stay gated. The public
    wall display is /kiosk/employee-productivity, which already had its own
    public read-only endpoint."""
    for route in ("@bp.get('/kiosk-board')",
                  "@bp.get('/kiosk-board/activity')",
                  "@bp.get('/kiosk-board/po-options')"):
        assert '@login_required' in _decorators_after(KIOSK_BOARD, route), \
            f'{route} must stay signed-in only'


def test_admin_and_dashboard_pages_still_redirect_an_anonymous_browser():
    for endpoint in ('def admin_page', 'def app_page'):
        block = APP_PY[APP_PY.index(endpoint):]
        block = block[:block.index('@app.', 10)] if '@app.' in block[10:] else block
        assert 'validate_and_touch' in block and 'login_page' in block, \
            f'{endpoint} must keep redirecting an unauthenticated browser to /login'


def test_no_route_module_grew_a_blanket_auth_bypass():
    """The fix must not have been implemented as a global before_request hole."""
    for text in (APP_PY, KIOSK, AUTH):
        assert not re.search(r'before_request.*(?:kiosk|public|allowlist)', text, re.IGNORECASE)
    assert 'def kiosk_public' in AUTH, 'the boundary lives in auth.py, in one place'
    # It is applied to the kiosk blueprint only.
    users = [path.name for path in APP.glob('*.py')
             if 'kiosk_public' in path.read_text(encoding='utf-8') and path.name != 'auth.py']
    assert users == ['kiosk.py'], f'@kiosk_public leaked outside the kiosk surface: {users}'


def test_the_kiosk_screen_never_tells_a_worker_to_log_in():
    """Requirement 4, from the operator's side: a kiosk browser that has never
    logged in (or whose cookie expired) must not be shown a login prompt."""
    js = (APP / 'static/kiosk.js').read_text(encoding='utf-8')
    assert 'đăng nhập trên máy này' not in js
    assert "location.href='/login'" not in js and 'location.href = "/login"' not in js
    html = (APP / 'templates/kiosk.html').read_text(encoding='utf-8')
    assert '/login' not in html
