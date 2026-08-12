from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_compose_binds_loopback_only():
    text=(ROOT/"compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:8080:8080"' in text
    assert 'MESFLOW_LOCAL_AUTO_LOGIN: ${MESFLOW_LOCAL_AUTO_LOGIN:-1}' in text

def test_local_auto_login_direct_only():
    text=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    assert 'host in {"127.0.0.1","localhost","::1"} and not forwarded_proto' in text
    assert 'settings.test_auto_login or (settings.local_auto_login and _is_direct_local_request())' in text
    assert 'LocalhostAwareSessionInterface' in text

def test_public_secure_cookie_behavior_retained():
    text=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    assert 'return super().get_cookie_secure(app)' in text
