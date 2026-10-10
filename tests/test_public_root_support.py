"""Public support must not weaken the authenticated MES boundary."""
from pathlib import Path
import importlib.util

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    from mesflow.web.app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_anonymous_root_and_welcome_serve_same_support_without_session(client):
    root = client.get('/')
    assert root.status_code == 200
    assert b'id="support-launch"' in root.data
    assert b'/login?noauto=1' in root.data
    assert root.data == client.get('/welcome').data
    assert 'Set-Cookie' not in root.headers


def test_business_app_and_api_still_require_authentication(client):
    response = client.get('/app')
    assert response.status_code == 302
    assert response.headers['Location'] == '/login'
    assert client.get('/api/production-orders').status_code == 401
    assert client.get('/login?noauto=1').status_code == 200


def test_public_root_does_not_modify_an_existing_session(client):
    with client.session_transaction() as session:
        session['user_id'] = 123
        session['username'] = 'session-preservation-probe'
    assert client.get('/').status_code == 200
    with client.session_transaction() as session:
        assert session['user_id'] == 123
        assert session['username'] == 'session-preservation-probe'


def test_support_contains_only_public_copy_and_no_data_channels():
    html = (ROOT / 'app/mesflow/web/templates/welcome.html').read_text()
    script = html.split('<script>')[1].split('</script>')[0]
    for forbidden in ('XMLHttpRequest', 'WebSocket', 'sendBeacon',
                      'localStorage', 'sessionStorage', 'document.cookie',
                      'innerHTML', 'api_key', 'DATABASE_URL'):
        assert forbidden not in script
    assert 'FAQ dự phòng' in html
    assert "credentials:'omit'" in script
    assert "JSON.stringify({topics:[reply.id]})" in script
    assert script.count('fetch(') == 1
    assert 'maxlength="300"' in html


def test_nginx_patch_preserves_all_existing_proxy_and_auth_routes():
    spec = importlib.util.spec_from_file_location('root_nginx', ROOT / 'scripts/prepare-public-root-nginx.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = ('http { server { listen 80 default_server;\n' + module.MARKER +
                'location / { proxy_pass http://mesflow_backend; } }\n'
                'server { listen 443 ssl default_server;\n' + module.MARKER +
                'location / { proxy_pass http://mesflow_backend; } } }')
    patched = module.prepare(original)
    assert patched.replace(module.HTTP, '').replace(module.HTTPS, '') == original
    assert patched.count('location = / {') == 2
    assert 'limit_except GET { deny all; }' in patched
    with pytest.raises(ValueError):
        module.prepare(patched)
    with pytest.raises(ValueError):
        module.prepare('unrecognized configuration')
