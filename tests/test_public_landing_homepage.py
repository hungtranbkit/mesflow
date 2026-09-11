"""Public landing page at "/" for anonymous visitors.

The whole point of this feature's shape is that it is OFF unless a deployment
deliberately ships a landing bundle. These tests pin both halves:

  * with no bundle, "/" behaves exactly as it always did (redirect to /login
    when signed out, to /app when signed in) — an existing install upgrading to
    this version must not change behaviour,
  * with a bundle, an anonymous visitor gets the page and a signed-in one still
    goes to the workspace.

Guarded, not decorative: point `landing_dir` at a directory with no index.html
and `test_directory_without_index_is_treated_as_absent` fails; let /assets/
escape the landing directory and `test_asset_route_cannot_escape_the_landing_dir`
fails.
"""
import dataclasses

import pytest

from mesflow.web import app as app_module


@pytest.fixture
def landing_bundle(tmp_path):
    root = tmp_path / 'landing'
    (root / 'assets').mkdir(parents=True)
    (root / 'index.html').write_text('<!doctype html><title>MESFlow</title>', encoding='utf-8')
    (root / 'assets' / 'index-abc123.css').write_text('body{}', encoding='utf-8')
    (tmp_path / 'secret.txt').write_text('must never be served', encoding='utf-8')
    return root


def _client(monkeypatch, *, landing_dir='', signed_in=False):
    monkeypatch.setattr(app_module, 'settings',
                        dataclasses.replace(app_module.settings, landing_dir=str(landing_dir)))
    # validate_and_touch() returns None when the session is valid.
    monkeypatch.setattr(app_module.session_policy, 'validate_and_touch',
                        lambda *a, **k: None if signed_in else 'NO_SESSION')
    application = app_module.create_app()
    application.config.update(TESTING=True)
    return application.test_client()


def test_without_a_bundle_root_still_redirects_to_login(monkeypatch):
    r = _client(monkeypatch).get('/')
    assert r.status_code == 302
    assert '/login' in r.headers['Location']


def test_without_a_bundle_signed_in_still_goes_to_the_app(monkeypatch):
    r = _client(monkeypatch, signed_in=True).get('/')
    assert r.status_code == 302
    assert '/app' in r.headers['Location']


def test_directory_without_index_is_treated_as_absent(monkeypatch, tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    r = _client(monkeypatch, landing_dir=empty).get('/')
    assert r.status_code == 302, 'a directory with no index.html must not enable the feature'
    assert '/login' in r.headers['Location']


def test_anonymous_visitor_gets_the_landing_page(monkeypatch, landing_bundle):
    r = _client(monkeypatch, landing_dir=landing_bundle).get('/')
    assert r.status_code == 200
    assert b'MESFlow' in r.data
    assert r.headers.get('Cache-Control') == 'no-cache'


def test_signed_in_user_still_goes_to_the_workspace(monkeypatch, landing_bundle):
    """The landing page must never get between a user and their work."""
    r = _client(monkeypatch, landing_dir=landing_bundle, signed_in=True).get('/')
    assert r.status_code == 302
    assert '/app' in r.headers['Location']


def test_assets_are_served_and_fingerprint_cached(monkeypatch, landing_bundle):
    c = _client(monkeypatch, landing_dir=landing_bundle)
    r = c.get('/assets/index-abc123.css')
    assert r.status_code == 200
    assert 'immutable' in r.headers.get('Cache-Control', '')


def test_assets_404_when_no_bundle_is_shipped(monkeypatch):
    assert _client(monkeypatch).get('/assets/index-abc123.css').status_code == 404


def test_asset_route_cannot_escape_the_landing_dir(monkeypatch, landing_bundle):
    c = _client(monkeypatch, landing_dir=landing_bundle)
    for attempt in ('../secret.txt', '..%2fsecret.txt', '....//secret.txt'):
        r = c.get(f'/assets/{attempt}')
        assert r.status_code in (403, 404), f'{attempt} leaked: {r.status_code}'
        assert b'must never be served' not in r.data


def test_login_and_app_routes_are_untouched(monkeypatch, landing_bundle):
    """The landing page must not shadow the real entry points."""
    c = _client(monkeypatch, landing_dir=landing_bundle)
    assert c.get('/login').status_code == 200
    # /app is behind the session guard; signed out it redirects, never 404s.
    assert c.get('/app').status_code in (200, 302)
