"""Showcase boundary: public marketing + demo must stay isolated from MES writes."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app/mesflow/web/app.py").read_text(encoding="utf-8")
WELCOME = (ROOT / "app/mesflow/web/templates/welcome.html").read_text(encoding="utf-8")
DEMO = (ROOT / "app/mesflow/web/templates/demo_showcase.html").read_text(encoding="utf-8")


def _route_block(route: str, next_route: str) -> str:
    start = APP.index(route)
    end = APP.index(next_route, start)
    return APP[start:end]


def test_welcome_and_demo_are_explicit_public_routes():
    block = _route_block("@app.get('/welcome')", "@app.get('/')")
    assert "@app.get('/demo')" in block
    assert "validate_and_touch" not in block
    assert "@admin_required" not in block
    assert "test_auto_login" not in block


def test_landing_puts_try_demo_above_the_fold_and_names_safety():
    assert 'href="/demo"' in WELCOME
    assert "Dùng thử demo" in WELCOME
    assert "không kết nối production" in WELCOME
    assert "không có thao tác ghi" in WELCOME or "Không gọi API ghi dữ liệu" in WELCOME


def test_demo_is_client_only_and_has_no_business_api_calls():
    lowered = DEMO.lower()
    assert "demo mode" in lowered
    assert "đặt lại demo" in lowered
    assert "bắt đầu tại đây" in lowered
    assert "fetch(" not in lowered
    assert "xmlhttprequest" not in lowered
    assert "/api/" not in lowered
    assert "database_url" not in lowered
    assert "auto-login" not in lowered
    assert "admin@" not in lowered


def test_demo_reset_only_resets_browser_session_state():
    assert "sessionStorage.removeItem('mesflow-demo-step')" in DEMO
    assert "sessionStorage.removeItem('mesflow-demo-scan')" in DEMO
    assert "localStorage" not in DEMO


def test_demo_has_customer_quick_tour_surfaces():
    for label in ("Tổng quan", "Kiosk flow", "Ngoại lệ", "Năng suất"):
        assert label in DEMO
    assert re.search(r"1/4.+Tổng quan", DEMO)
