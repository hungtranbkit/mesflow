"""/kiosk-mobile is a SIGNED-IN surface; /kiosk stays open. Both, proved here.

Two things are being locked down, and they pull in opposite directions -- which
is exactly why they need to be asserted together in one file:

  * the fixed station keeps working with no account and no cookie (a workshop
    machine has neither, and taking that away locks the shop floor out -- it
    already happened once, see the HISTORY note on kiosk_public in web/auth.py);
  * the phone does NOT. A phone leaves the building, and its URL gets forwarded
    in a chat group.

The gate that matters is the SERVER one. Hiding a button in the phone's
JavaScript protects nothing, and neither does the User-Agent string: it is free
text the caller picks. test_no_access_decision_reads_the_user_agent below fails
the build if anyone ever tries.

In-process (create_app() + test_client(), same pattern as
test_autologin_guard_unit.py) -- no PostgreSQL. Every case here answers before
a DB query would run: an anonymous call is refused by the decorator, and the
signed-in cases use 'admin', whose permission check short-circuits in
_has_permission() without consulting RBAC.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from mesflow.core import session_policy
from mesflow.web import app as app_module
from mesflow.web import auth as auth_module

APP_DIR = Path(__file__).resolve().parents[1] / 'app/mesflow/web'
KIOSK_PY = (APP_DIR / 'kiosk.py').read_text(encoding='utf-8')
AUTH_PY = (APP_DIR / 'auth.py').read_text(encoding='utf-8')
KIOSK_HTML = (APP_DIR / 'templates/kiosk.html').read_text(encoding='utf-8')
KIOSK_JS = (APP_DIR / 'static/kiosk.js').read_text(encoding='utf-8')

# Everything the phone can call that is not a bare version string.
MOBILE_WRITE_ROUTES = [
    ('post', '/api/kiosk-mobile/scan'),
    ('post', '/api/kiosk-mobile/start'),
    ('post', '/api/kiosk-mobile/finish/1'),
    ('post', '/api/kiosk-mobile/heartbeat'),
    ('get', '/api/kiosk-mobile/demo-data'),
]


@pytest.fixture
def client():
    app = app_module.create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _sign_in(client, role='admin'):
    with client.session_transaction() as sess:
        sess.update(session_policy.session_fields_for_login(1, 'tester', role))


# --------------------------------------------------------------------------
# 1. Anonymous
# --------------------------------------------------------------------------
def test_anonymous_phone_is_sent_to_login_and_back_to_kiosk_mobile(client):
    """A person holding a phone must land on the login FORM and return here.

    A JSON 401 would be a dead end on a phone: there is no page to read it and
    nowhere to type a password. The round trip is the requirement, so ?next is
    asserted literally, not just "it redirected somewhere".
    """
    response = client.get('/kiosk-mobile')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    assert 'next=%2Fkiosk-mobile' in response.headers['Location'] \
        or 'next=/kiosk-mobile' in response.headers['Location']


@pytest.mark.parametrize('method,path', MOBILE_WRITE_ROUTES)
def test_anonymous_is_refused_by_the_server_not_by_the_page(client, method, path):
    """THE case: a POST straight at the URL, with no browser involved at all.

    curl does not run the page's JavaScript, so anything the front end hides is
    irrelevant here. 401 must come from the decorator.
    """
    response = getattr(client, method)(path, json={})
    assert response.status_code == 401, f'{path} answered {response.status_code}'
    assert response.get_json()['error'] in ('AUTH_REQUIRED', 'SESSION_EXPIRED')


def test_a_convincing_iphone_user_agent_buys_nothing(client):
    """User-Agent is attacker-controlled free text -- one curl flag away."""
    response = client.post(
        '/api/kiosk-mobile/scan', json={'qr': 'WF|EMP|X'},
        headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) '
                               'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile Safari/604.1'})
    assert response.status_code == 401


def test_a_kiosk_device_token_does_not_open_the_phone_surface(client):
    """The station's OPTIONAL device token is not a login.

    /api/kiosk-web/* accepts one; /api/kiosk-mobile/* must not, or the phone
    surface would inherit the station's anonymous posture through the back door
    the moment someone copied a token out of a terminal's localStorage.
    """
    response = client.post('/api/kiosk-mobile/scan', json={'qr': 'WF|EMP|X'},
                           headers={'X-Kiosk-Token': 'whatever'})
    assert response.status_code == 401


# --------------------------------------------------------------------------
# 2. Signed in
# --------------------------------------------------------------------------
def test_signed_in_phone_gets_the_page_pointed_at_its_own_api(client):
    _sign_in(client)
    response = client.get('/kiosk-mobile')
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'data-kiosk-api="/api/kiosk-mobile"' in body
    assert 'data-kiosk-surface="mobile"' in body
    # The camera layer is the whole point of this surface -- same markup, same
    # module, no second implementation.
    assert 'kiosk-camera.js' in body
    assert 'id="camera-result-raw"' in body


def test_camera_stays_permitted_on_the_new_path(client):
    """Permissions-Policy camera=() would break getUserMedia on iPhone Safari
    silently -- the browser reports no error the page can see. /kiosk-mobile
    must land on the same camera=(self) branch /kiosk does."""
    _sign_in(client)
    for path in ('/kiosk', '/kiosk-mobile'):
        policy = client.get(path).headers['Permissions-Policy']
        assert 'camera=(self)' in policy, f'{path} -> {policy}'
    # ...and nowhere else.
    assert 'camera=()' in client.get('/login').headers['Permissions-Policy']


def test_the_phone_installs_from_its_own_manifest(client):
    """Sharing /kiosk.webmanifest would make "Add to Home Screen" open /kiosk --
    the PUBLIC page -- from an icon the user believes is their signed-in one."""
    manifest = client.get('/kiosk-mobile.webmanifest').get_json()
    assert manifest['start_url'] == '/kiosk-mobile'
    assert manifest['scope'] == '/kiosk-mobile'
    assert client.get('/kiosk.webmanifest').get_json()['start_url'] == '/kiosk'


# --------------------------------------------------------------------------
# 3. No regression on the station
# --------------------------------------------------------------------------
def test_the_fixed_station_is_still_open_and_still_calls_its_own_api(client):
    response = client.get('/kiosk')
    assert response.status_code == 200, 'the workshop machine has no account'
    body = response.get_data(as_text=True)
    assert 'data-kiosk-api="/api/kiosk-web"' in body
    assert 'data-kiosk-surface="station"' in body


def test_the_station_page_has_no_phone_camera_entry_point_at_all(client):
    """Not hidden -- ABSENT.

    The fixed station scans with a USB/GM65 gun wired to it. A "Camera điện
    thoại" button there is a road nobody needs and everybody presses once, and
    on a desktop with no camera pressing it only produces an error message.

    `hidden`, `display:none` or a JS guard would all leave the button in the
    DOM: still focusable by keyboard, still clickable from DevTools, still
    something a future reader has to reason about. So the markup is not
    RENDERED for this surface, and kiosk-camera.js is not even fetched.
    """
    body = client.get('/kiosk').get_data(as_text=True)
    for absent in ('camera-toggle', 'kiosk-camera-toggle', 'Camera điện thoại',
                   'camera-layer', 'camera-result', 'kiosk-camera.js'):
        assert absent not in body, f'/kiosk still ships {absent!r}'


def test_the_phone_page_still_has_every_one_of_them(client):
    """The other half of the pair: this removal is about WHERE the camera
    lives, not about dropping it. A test that only proves absence would stay
    green if the camera disappeared from both surfaces."""
    _sign_in(client)
    body = client.get('/kiosk-mobile').get_data(as_text=True)
    for present in ('camera-toggle', 'kiosk-camera-toggle', 'Camera điện thoại',
                    'camera-layer', 'camera-result', 'kiosk-camera.js'):
        assert present in body, f'/kiosk-mobile lost {present!r}'


def test_the_station_page_still_carries_the_scanner_path_untouched(client):
    """What must NOT change while the camera goes away: the USB/GM65 path.
    scanner-input is where a scanner gun types, and the demo panel and the
    numeric keypad are the station's own affordances."""
    body = client.get('/kiosk').get_data(as_text=True)
    for present in ('id="scanner-input"', 'kiosk-demo-toggle', 'qty-keypad',
                    '/static/kiosk.js', '/static/op-policy.js', '/static/core/net.js'):
        assert present in body, f'/kiosk lost {present!r}'


def test_the_station_scan_endpoint_still_answers_an_anonymous_caller(client):
    """400 (not 401): it got PAST auth and into validation, which is the proof.
    An empty qr is rejected before any DB query, so this needs no Postgres."""
    response = client.post('/api/kiosk-web/scan', json={})
    assert response.status_code == 400
    assert response.get_json()['error_code'] == 'SCN-001'


# --------------------------------------------------------------------------
# 4. One implementation, two doors
# --------------------------------------------------------------------------
def test_mobile_routes_delegate_instead_of_reimplementing():
    """Every mobile route body is a call to the SAME _*_response() the public
    route calls. A second copy of a business rule is a second thing to forget
    to fix; the decorator is the only thing allowed to differ."""
    for route, handler in (
        ('/api/kiosk-mobile/scan', '_scan_response()'),
        ('/api/kiosk-mobile/start', '_start_response()'),
        ('/api/kiosk-mobile/finish/<int:session_id>', '_finish_response(session_id)'),
        ('/api/kiosk-mobile/heartbeat', '_heartbeat_response()'),
        ('/api/kiosk-mobile/demo-data', '_demo_data_response()'),
    ):
        block = KIOSK_PY[KIOSK_PY.index(f"'{route}'"):]
        block = block[:block.index('\n\n\n')] if '\n\n\n' in block else block
        assert '@kiosk_mobile_required' in block, f'{route} is not gated'
        assert f'return {handler}' in block, f'{route} must delegate to {handler}'


def test_no_access_decision_reads_the_user_agent():
    """Not a style rule. A User-Agent check reads like security and is not:
    `curl -H 'User-Agent: iPhone'` defeats it, and having one invites someone
    later to relax a real gate because "only phones reach this anyway"."""
    for name, source in (('kiosk.py', KIOSK_PY), ('auth.py', AUTH_PY)):
        code = '\n'.join(line for line in source.splitlines()
                         if not line.lstrip().startswith('#'))
        assert 'User-Agent' not in code and 'user_agent' not in code, \
            f'{name} makes a decision from the User-Agent string'


def test_the_permission_is_the_one_an_admin_already_administers():
    assert auth_module.KIOSK_MOBILE_PERMISSION == 'kiosk.view'
    from mesflow.db.repositories import rbac
    granted = {role for role, permission in rbac.SEED_ROLE_PERMISSIONS
               if permission == 'kiosk.view'}
    assert {'admin', 'manager', 'supervisor', 'operator'} <= granted
    assert 'viewer' not in granted, 'a read-only account must not run a station'


def test_the_page_never_hardcodes_one_api_prefix():
    """The prefix comes from the SERVER, written into the page it rendered.
    Deriving it in the browser (location.pathname, a UA sniff) would put a
    security-shaped decision on the untrusted side of the wire."""
    assert "document.body.dataset.kioskApi" in KIOSK_JS
    code = '\n'.join(line for line in KIOSK_JS.splitlines()
                     if not line.lstrip().startswith('//'))
    assert not re.search(r"['\"`]/api/kiosk-web/", code), \
        'kiosk.js still pins /api/kiosk-web/ -- the mobile page would call the public API'
    assert 'data-kiosk-api' in KIOSK_HTML
