from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_compose_binds_loopback_only():
    text=(ROOT/"compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8080:8080"' in text
    # Hardened since this test was written: local auto-login now defaults
    # OFF (opt-in only for local dev), not ON -- see MESFLOW_LOCAL_AUTO_LOGIN
    # in compose.yml and settings.local_auto_login in config.py.
    assert 'MESFLOW_LOCAL_AUTO_LOGIN: ${MESFLOW_LOCAL_AUTO_LOGIN:-0}' in text

def test_local_auto_login_direct_only():
    text=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    assert 'host in {"127.0.0.1","localhost","::1"} and not forwarded_proto' in text
    assert 'LocalhostAwareSessionInterface' in text
    # local_auto_login only relaxes the cookie-secure flag for direct
    # http://127.0.0.1:8080 dev traffic (never in production, never for
    # requests forwarded through nginx) -- it must never itself create an
    # authenticated session. The explicit test_auto_login() endpoint (gated
    # separately by settings.test_auto_login) is the only thing that logs a
    # session in without a real password.
    assert 'settings.environment != "production" and settings.local_auto_login and _is_direct_local_request()' in text

def test_public_secure_cookie_behavior_retained():
    text=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    assert 'return super().get_cookie_secure(app)' in text
