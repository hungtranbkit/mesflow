from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "mesflow" / "web" / "static"


def test_shared_ui_foundation_exposes_required_primitives():
    source = (STATIC / "core" / "ui.js").read_text(encoding="utf-8")
    for primitive in (
        "pageShell", "pageHeader", "openDrawer", "openModal", "confirmDialog",
        "filterBar", "statusBadge", "loadingState", "emptyState", "errorState",
    ):
        assert primitive in source


def test_shared_drawer_has_keyboard_history_focus_and_standard_sizes():
    source = (STATIC / "core" / "ui.js").read_text(encoding="utf-8")
    css = (STATIC / "ui.css").read_text(encoding="utf-8")
    assert "Escape" in source
    assert "popstate" in source
    assert "history.back" in source
    assert "origin.focus" in source
    for size in ("--ui-drawer-sm", "--ui-drawer-md", "--ui-drawer-lg", "--ui-drawer-xl"):
        assert size in css


def test_session_management_uses_shared_vertical_slice():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    session = (STATIC / "pages" / "session-detail.js").read_text(encoding="utf-8")
    assert "MFUI.pageShell({id:'sessionManagementPage'" in app
    assert "MFUI.filterBar" in app
    assert "SessionDetailDrawer.open" in app
    assert "MFUI.openDrawer" in session
    assert "MFUI.loadingState" in session
    assert "MFUI.errorState" in session


def test_navigation_supports_url_and_refresh_state():
    nav = (STATIC / "core" / "nav.js").read_text(encoding="utf-8")
    template = (ROOT / "app" / "mesflow" / "web" / "templates" / "app.html").read_text(encoding="utf-8")
    assert "sessionStorage" in nav
    assert "setPageUrl" in nav
    assert "setQuery" in nav
    assert "bootParams.get('page')" in template
    assert "/static/core/ui.js" in template


def test_foundation_keeps_business_and_kiosk_boundaries_unchanged():
    source = (STATIC / "core" / "ui.js").read_text(encoding="utf-8")
    assert "/api/" not in source
    assert "fetch(" not in source
    assert "good_qty" not in source
    assert "repairable" not in source.lower()
