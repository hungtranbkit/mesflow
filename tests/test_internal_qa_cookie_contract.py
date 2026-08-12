from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]
def test_internal_qa_http_cookie_not_secure():
    text=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    ast.parse(text)
    block=text[text.index("class LocalhostAwareSessionInterface"):text.index("def create_app")]
    assert "qa_internal=settings.internal_qa_auto_login and _is_direct_internal_qa_request()" in block
    assert "if local_direct or qa_internal:" in block
    assert "return False" in block
    assert "return super().get_cookie_secure(app)" in block
def test_public_secure_policy_retained():
    text=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    assert "SESSION_COOKIE_SECURE=settings.cookie_secure" in text
