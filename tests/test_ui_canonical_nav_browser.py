"""UI consolidation P1 -- canonical navigation in a real browser.

Renders the real templates/app.html (Jinja) + real static JS in Chromium with
every /api/* call stubbed, so the sidebar/tab/URL behavior of app.js +
core/canonical-nav.js is exercised without a database. Business screens may
render empty/error states against the stubs -- only navigation is asserted.

Skips cleanly when Python Playwright or its Chromium build is unavailable.
"""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
jinja2 = pytest.importorskip("jinja2")

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "app" / "mesflow" / "web"
INVENTORY = json.loads((ROOT / "docs" / "ui-inventory.json").read_text(encoding="utf-8"))
ORIGIN = "http://mesflow.test"
SYSTEM_PAGES = {p["id"] for p in INVENTORY["sidebarDestinations"] if p["permission"]["kind"] == "super_admin_role"}
CONTENT_TYPES = {".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".json": "application/json"}


def _render_app_html(user):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(WEB / "templates")))
    return env.get_template("app.html").render(
        version="test", username=user["username"], role=user["role"],
        session_user_id=1, permissions=user["permissions"],
    )


@pytest.fixture
def browser():
    """One Chromium per test (fresh localStorage, no shared flag state).

    Default launch first. Sandboxed dev shells (no zygote/GPU process) crash
    Chromium at startup unless it runs single-process -- and a single-process
    browser dies as soon as any context closes, which is why tests never
    close their context and the whole browser is torn down here instead."""
    with sync_api.sync_playwright() as p:
        errors = []
        for args in ([], ["--no-zygote", "--disable-gpu", "--single-process"]):
            b = None
            try:
                b = p.chromium.launch(args=args)
                b.new_context().new_page().set_content("<b>ok</b>")
            except Exception as exc:  # pragma: no cover - environment dependent
                errors.append(f"{args}: {str(exc).splitlines()[0]}")
                if b:
                    try:
                        b.close()
                    except Exception:
                        pass
                continue
            yield b
            b.close()
            return
        pytest.skip("chromium unavailable: " + " | ".join(errors))


def _open(browser, query, user=None, viewport=(1366, 768), context=None):
    user = user or {"username": "admin", "role": "admin", "permissions": []}
    html = _render_app_html(user)
    ctx = context or browser.contexts[0]
    ctx.pages[0].set_viewport_size({"width": viewport[0], "height": viewport[1]})

    def handle(route):
        path = urlparse(route.request.url).path
        if path.startswith("/static/"):
            f = WEB / path.lstrip("/")
            if f.is_file():
                return route.fulfill(body=f.read_bytes(), content_type=CONTENT_TYPES.get(f.suffix, "application/octet-stream"))
            return route.fulfill(status=404, body="")
        if path.startswith("/api/"):
            return route.fulfill(status=200, content_type="application/json", body='{"items":[]}')
        return route.fulfill(status=200, content_type="text/html", body=html)

    ctx.route("**/*", handle)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(f"{ORIGIN}/app{query}")
    page.wait_for_function("document.body.dataset.page!==undefined")
    return page


def _q(page):
    return {k: v[0] for k, v in parse_qs(urlparse(page.url).query).items()}


def _sidebar_pages(page):
    return page.eval_on_selector_all("#nav [data-page]", "els=>els.map(e=>e.dataset.page)")


def test_default_without_flag_is_the_legacy_sidebar(browser):
    page = _open(browser, "")
    expected = [p["id"] for p in INVENTORY["sidebarDestinations"] if p["id"] not in SYSTEM_PAGES]
    assert _sidebar_pages(page) == expected
    assert page.locator("#nav [data-canonical-screen]").count() == 0
    assert page.locator("#canonicalTabs").count() == 0
    assert page.locator("#canonicalHelpAction").count() == 0
    assert page.evaluate("document.body.dataset.uiRefactor") is None
    assert _q(page) == {"page": "overview"}


def test_super_admin_default_sidebar_is_all_25_legacy_entries(browser):
    page = _open(browser, "", {"username": "root", "role": "super_admin", "permissions": []})
    assert _sidebar_pages(page) == [p["id"] for p in INVENTORY["sidebarDestinations"]]


def test_flag_shows_eleven_canonical_screens_and_persists(browser):
    page = _open(browser, "?ui_refactor=1", {"username": "root", "role": "super_admin", "permissions": []})
    screens = page.eval_on_selector_all("#nav [data-canonical-screen]", "els=>els.map(e=>e.dataset.canonicalScreen)")
    assert screens == ["overview", "planning", "templates", "operations-sessions", "quality", "productivity",
                       "kiosk-admin", "master-data", "trace-logs", "admin", "system"]
    assert page.locator("#nav .sidebar-group").count() == 0
    assert page.locator("#canonicalHelpAction").is_visible()
    assert _q(page)["screen"] == "overview" and _q(page)["tab"] == "realtime"
    # Persisted: a later visit without the param stays in refactor mode...
    page.goto(f"{ORIGIN}/app?page=users")
    page.wait_for_function("document.body.dataset.page==='users'")
    assert page.locator("#nav [data-canonical-screen]").count() == 11
    assert _q(page)["screen"] == "admin" and _q(page)["tab"] == "users"
    # ...until explicitly switched off.
    page.goto(f"{ORIGIN}/app?ui_refactor=0")
    page.wait_for_function("document.body.dataset.page==='overview'")
    assert page.locator("#nav [data-canonical-screen]").count() == 0
    assert "users" in _sidebar_pages(page)


def test_admin_flag_hides_super_admin_system_screen(browser):
    page = _open(browser, "?ui_refactor=1")
    screens = page.eval_on_selector_all("#nav [data-canonical-screen]", "els=>els.map(e=>e.dataset.canonicalScreen)")
    assert len(screens) == 10 and "system" not in screens


def test_restricted_role_sees_only_screens_it_could_already_open(browser):
    user = {"username": "qa", "role": "operator", "permissions": ["rework.view", "business_audit.view"]}
    page = _open(browser, "?ui_refactor=1&page=rework-queue", user)
    screens = page.eval_on_selector_all("#nav [data-canonical-screen]", "els=>els.map(e=>e.dataset.canonicalScreen)")
    assert screens == ["quality", "trace-logs"]
    tabs = page.eval_on_selector_all("#canonicalTabs [data-canonical-tab]", "els=>els.map(e=>e.dataset.canonicalTab)")
    assert tabs == ["rework", "qc"]
    # Unauthorized tab is blocked by the unchanged legacy gate.
    page.goto(f"{ORIGIN}/app?screen=trace-logs&tab=trace")
    page.wait_for_selector("#content .empty.danger")
    assert "Không có quyền truy cập" in page.inner_text("#content")


def test_legacy_deep_link_resolves_and_keeps_query_params(browser):
    page = _open(browser, "?ui_refactor=1&page=sessions&session=987654&foo=bar")
    page.wait_for_function("document.body.dataset.page==='session-management'")
    q = _q(page)
    assert (q["page"], q["screen"], q["tab"]) == ("session-management", "operations-sessions", "all")
    assert q["session"] == "987654" and q["foo"] == "bar"
    assert page.locator('#nav [data-canonical-screen="operations-sessions"].active').count() == 1
    assert page.eval_on_selector("#canonicalTabs .mf-tab.active", "e=>e.dataset.canonicalTab") == "all"


def test_tab_switch_updates_url_back_forward_and_reload(browser):
    page = _open(browser, "?ui_refactor=1&page=production-orders")
    page.wait_for_function("document.body.dataset.page==='production-orders'")
    page.click('#canonicalTabs [data-canonical-tab="schedule"]')
    page.wait_for_function("document.body.dataset.page==='production-schedule'")
    assert (_q(page)["screen"], _q(page)["tab"], _q(page)["page"]) == ("planning", "schedule", "production-schedule")
    page.go_back()
    page.wait_for_function("document.body.dataset.page==='production-orders'")
    assert _q(page)["tab"] == "orders"
    assert page.eval_on_selector("#canonicalTabs .mf-tab.active", "e=>e.dataset.canonicalTab") == "orders"
    page.go_forward()
    page.wait_for_function("document.body.dataset.page==='production-schedule'")
    page.reload()
    page.wait_for_function("document.body.dataset.page==='production-schedule'")
    assert (_q(page)["screen"], _q(page)["tab"]) == ("planning", "schedule")
    assert page.eval_on_selector("#canonicalTabs .mf-tab.active", "e=>e.dataset.canonicalTab") == "schedule"


def test_canonical_only_url_and_sidebar_click(browser):
    page = _open(browser, "?ui_refactor=1&screen=master-data&tab=qr")
    page.wait_for_function("document.body.dataset.page==='qr-print'")
    assert _q(page)["page"] == "qr-print"
    page.click('#nav [data-canonical-screen="kiosk-admin"]')
    page.wait_for_function("document.body.dataset.page==='kiosk-management'")
    assert (_q(page)["screen"], _q(page)["tab"]) == ("kiosk-admin", "stations")


@pytest.mark.parametrize("viewport", [tuple(v.values())[1:] for v in INVENTORY["viewportBaselines"]])
def test_canonical_shell_has_no_horizontal_page_overflow(browser, viewport):
    page = _open(browser, "?ui_refactor=1&page=employees", viewport=viewport)
    page.wait_for_function("document.body.dataset.page==='employees'")
    assert page.locator("#canonicalTabs").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
