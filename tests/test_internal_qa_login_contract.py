from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]

def test_internal_qa_uses_real_password_auth_not_a_silent_bypass():
    """Internal QA traffic on the trusted mesflow-edge network (Host header
    is mesflow-app/mesflow, never forwarded through nginx) is detected only
    to decide whether the session cookie may be non-secure over plain
    internal HTTP (settings.internal_http_session) -- it must never
    silently authenticate a request without real credentials. The old
    settings.internal_qa_auto_login login-bypass code path was removed;
    per AGENTS.md, QA must use real auth unless a test explicitly targets
    auth-bypass behavior."""
    a=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    ast.parse(a)
    assert 'host in {"mesflow-app","mesflow","mesflow-demo-app"} and not forwarded_proto' in a
    assert 'settings.internal_http_session and _is_direct_internal_qa_request()' in a
    block=a[a.index("class LocalhostAwareSessionInterface"):a.index("def create_app")]
    assert 'internal_qa_auto_login' not in block  # no auto-login bypass wired into the session/cookie path

def test_public_global_auto_login_default_off():
    c=(ROOT/"compose.yml").read_text(encoding="utf-8")
    assert 'MESFLOW_TEST_AUTO_LOGIN: ${MESFLOW_TEST_AUTO_LOGIN:-0}' in c
    # MESFLOW_INTERNAL_QA_AUTO_LOGIN is retained only as a defense-in-depth
    # production-preflight guard (scripts/production-preflight.sh) even
    # though the Flask app itself no longer wires it to any bypass -- its
    # default must stay 0/off either way.
    assert 'MESFLOW_INTERNAL_QA_AUTO_LOGIN: ${MESFLOW_INTERNAL_QA_AUTO_LOGIN:-0}' in c
