from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]

def test_internal_qa_login():
    a=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text(encoding="utf-8")
    c=(ROOT/"app"/"mesflow"/"core"/"config.py").read_text(encoding="utf-8")
    ast.parse(a); ast.parse(c)
    assert 'host in {"mesflow-app","mesflow"} and not forwarded_proto' in a
    assert 'settings.internal_qa_auto_login and _is_direct_internal_qa_request()' in a
    assert 'internal_qa_auto_login: bool' in c

def test_public_global_auto_login_default_off():
    c=(ROOT/"compose.yml").read_text(encoding="utf-8")
    assert 'MESFLOW_TEST_AUTO_LOGIN: ${MESFLOW_TEST_AUTO_LOGIN:-0}' in c
    assert 'MESFLOW_INTERNAL_QA_AUTO_LOGIN: ${MESFLOW_INTERNAL_QA_AUTO_LOGIN:-1}' in c
