from pathlib import Path
import json, ast
ROOT=Path(__file__).resolve().parents[1]
EXPECTED="65.8.44.31"

def test_release_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    assert EXPECTED in (ROOT/"app"/"mesflow"/"__init__.py").read_text()
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"image: mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()

def test_auto_login_fail_closed():
    cfg=(ROOT/"app"/"mesflow"/"core"/"config.py").read_text()
    app=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text()
    ast.parse(cfg); ast.parse(app)
    assert '_bool("MESFLOW_TEST_AUTO_LOGIN", "0")' in cfg
    assert '_bool("MESFLOW_LOCAL_AUTO_LOGIN", "0")' in cfg
    assert '_bool("MESFLOW_INTERNAL_QA_AUTO_LOGIN", "0")' in cfg
    assert 'AUTO_LOGIN_DISABLED_PRODUCTION' in app

def test_sensitive_diagnostics_require_admin():
    app=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text()
    assert "@app.get('/api/system/monitoring')\n    @admin_required" in app
    assert "@app.get('/api/system/auth-health')\n    @admin_required" in app

def test_no_insecure_compose_password_fallback():
    c=(ROOT/"compose.yml").read_text()
    assert "MesflowChangeMe2026" not in c
    assert "POSTGRES_PASSWORD is required" in c
    assert "DATABASE_URL is required" in c

def test_tutorial_uses_password_login():
    s=(ROOT/"tests"/"e2e"/"tutorial-video.spec.js").read_text()
    assert "/api/auth/login" in s
    assert "/api/auth/test-auto-login" not in s
    assert "MESFLOW_TUTORIAL_PASSWORD" in s

def test_playwright_patched():
    p=json.loads((ROOT/"package.json").read_text())
    assert p["devDependencies"]["@playwright/test"]=="1.62.1"
