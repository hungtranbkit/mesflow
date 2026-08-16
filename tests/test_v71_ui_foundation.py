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
    # Session Management builds its shell inline (not via MFUI.pageShell,
    # whose header is always-on and duplicated the page title already shown
    # by the outer workspace-header -- real defect reported live). Since the
    # UI Template Standard's Golden Reference migration (real structural
    # convergence, not just a shared class name on divergent containers),
    # it uses the same .page-shell/.page-header/.content-panel geometry as
    # Production Order and Session Exception Center -- verified pixel-equal
    # via getBoundingClientRect() across all three, not just class presence.
    assert 'id="sessionManagementPage"' in app
    assert '"page-shell"' in app
    assert '"page-header"' in app
    assert '"content-panel"' in app
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
