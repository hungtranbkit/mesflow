from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]
def test_internal_qa_http_cookie_not_secure():
    text=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    ast.parse(text)
    block=text[text.index("class LocalhostAwareSessionInterface"):text.index("def create_app")]
    # settings.internal_qa_auto_login was retired from this code path;
    # settings.internal_http_session is the current, correctly-scoped flag
    # (cookie transport policy only, never an auth bypass -- see
    # test_internal_qa_login_contract.py).
    assert "settings.internal_http_session and _is_direct_internal_qa_request()" in block
    assert "return False" in block
    assert "return super().get_cookie_secure(app)" in block
def test_public_secure_policy_retained():
    text=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    assert "SESSION_COOKIE_SECURE=settings.cookie_secure" in text
