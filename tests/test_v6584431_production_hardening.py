from pathlib import Path
import json, ast
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/"VERSION.txt").read_text().strip()

def test_release_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()

def test_auto_login_fail_closed():
    cfg=(ROOT/"app"/"mesflow"/"core"/"config.py").read_text()
    app=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text()
    ast.parse(cfg); ast.parse(app)
    assert '_bool("MESFLOW_TEST_AUTO_LOGIN", "0")' in cfg
    assert '_bool("MESFLOW_LOCAL_AUTO_LOGIN", "0")' in cfg
    assert '_bool("MESFLOW_INTERNAL_QA_AUTO_LOGIN", "0")' in cfg
    assert 'AUTO_LOGIN_DISABLED_PRODUCTION' in app


def test_auto_login_production_override_is_a_second_explicit_opt_in():
    """AUTOLOGIN task (2026-09-04): prodtest/demo run MESFLOW_ENV=production
    too (compose.yml hardcodes it), so allowing auto-login there needs a
    second, feature-scoped, default-off flag -- mirroring
    tutorial_data.py's MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION precedent --
    never satisfied by MESFLOW_TEST_AUTO_LOGIN alone, and never inferred
    from server_role."""
    cfg=(ROOT/"app"/"mesflow"/"core"/"config.py").read_text()
    app=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text()
    preflight=(ROOT/"scripts"/"production-preflight.sh").read_text()
    compose=(ROOT/"compose.yml").read_text()
    assert '_bool("MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION", "0")' in cfg
    assert 'def _auto_login_allowed():' in app
    assert 'return settings.environment!="production" or settings.test_auto_login_allow_production' in app
    assert 'MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION must be 0' in preflight
    assert 'MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION: ${MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION:-0}' in compose


def test_auto_login_persona_switch_is_a_fixed_allowlist():
    """Requirement #4/#7: persona quick-switch never accepts an arbitrary
    username -- only the 5 real non-super_admin RBAC roles, still through
    the same session_policy.start_session bootstrap, never a second bypass
    code path."""
    app=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text()
    assert "_AUTOLOGIN_PERSONAS=('admin','manager','supervisor','operator','viewer')" in app
    assert 'AUTO_LOGIN_INVALID_PERSONA' in app
    route=app[app.index("def test_auto_login():"):app.index("def login():")]
    assert route.count('session_policy.start_session(') == 1  # one bootstrap call, not a second path


def test_logout_avoids_autologin_loop():
    """Requirement #5: a deliberate logout must not bounce straight back
    into auto-login."""
    js=(ROOT/"app"/"mesflow"/"web"/"static"/"app.js").read_text()
    assert "location.href='/login?noauto=1'" in js
    app=(ROOT/"app"/"mesflow"/"web"/"app.py").read_text()
    assert "request.args.get('noauto')" in app

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
