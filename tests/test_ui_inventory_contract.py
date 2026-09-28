"""UI consolidation P0 -- frozen UI inventory and route/permission/deep-link baseline.

docs/ui-inventory.json is the machine-readable inventory of every addressable
admin SPA page ID, its renderer, its permission and its visibility, plus the
standalone surfaces and the viewport baseline list
(docs/UI_CONSOLIDATION_REFACTOR_PLAN.md, P0 / WP-00).

These tests are INTENTIONALLY brittle: adding, removing or renaming a page ID
in app.js / pages/*.js, moving it in or out of the sidebar, or changing its
permission must fail here until the inventory is updated in the same change.
That is what makes a screen-count change a deliberate decision rather than a
side effect.
"""
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.static

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "app" / "mesflow" / "web"
STATIC = WEB / "static"
INVENTORY = json.loads((ROOT / "docs" / "ui-inventory.json").read_text(encoding="utf-8"))
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
APP_HTML = (WEB / "templates" / "app.html").read_text(encoding="utf-8")

SIDEBAR = INVENTORY["sidebarDestinations"]
HIDDEN = INVENTORY["hiddenSpaPages"]
RESOURCE_FALLBACK = INVENTORY["resourceFallbackPages"]["ids"]
STANDALONE = INVENTORY["standaloneSurfaces"]


def _menu_block():
    start = APP_JS.index("const menu=[")
    end = APP_JS.index("\n];\n", start)
    return APP_JS[start:end]


def _open_page_line():
    return next(line for line in APP_JS.splitlines() if line.startswith("  if(id==='overview')return renderOverview();"))


def _source_sidebar_ids():
    return re.findall(r"page:'([a-z0-9-]+)'", _menu_block())


def _source_branch_ids():
    return re.findall(r"if\(id==='([a-z0-9-]+)'\)return", _open_page_line())


def _source_registered_ids():
    ids = set()
    for path in (STATIC / "pages").glob("*.js"):
        text = path.read_text(encoding="utf-8")
        ids.update(re.findall(r"registerPage\('([a-z0-9-]+)'", text))
        if "registerPage(PAGE_ID" in text:
            ids.update(re.findall(r"const PAGE_ID\s*=\s*'([a-z0-9-]+)'", text))
    return ids


def _source_resource_ids():
    block = APP_JS[: APP_JS.index("};\nconst PAGE_PERMISSION")]
    return set(re.findall(r"^\s*'?([a-z0-9-]+)'?:\{title:", block, re.M))


def _page_permission():
    raw = re.search(r"const PAGE_PERMISSION=\{(.*?)\};", APP_JS).group(1)
    return dict(re.findall(r"'?([a-z0-9-]+)'?:'([a-z_.]+)'", raw))


def _super_admin_pages():
    raw = re.search(r"const SUPER_ADMIN_PAGES=new Set\(\[(.*?)\]\)", APP_JS).group(1)
    return set(re.findall(r"'([a-z0-9-]+)'", raw))


# --------------------------------------------------------------------- counts

def test_inventory_counts_are_frozen():
    assert len(SIDEBAR) == 25
    assert len(HIDDEN) == 9
    assert len(STANDALONE) == 4


def test_inventory_ids_are_unique():
    ids = [p["id"] for p in SIDEBAR + HIDDEN] + RESOURCE_FALLBACK
    assert len(ids) == len(set(ids))
    assert len({s["id"] for s in STANDALONE}) == len(STANDALONE)


# --------------------------------------------- source <-> inventory agreement

def test_sidebar_ids_match_legacy_menu_exactly_in_order():
    assert _source_sidebar_ids() == [p["id"] for p in SIDEBAR]


def test_every_addressable_page_id_is_inventoried():
    """Fails when a page ID is added to or removed from the app without the
    inventory being updated."""
    source_ids = set(_source_sidebar_ids()) | set(_source_branch_ids()) | _source_registered_ids()
    resource_only = _source_resource_ids() - source_ids
    inventoried = {p["id"] for p in SIDEBAR + HIDDEN}
    assert source_ids == inventoried
    assert resource_only == set(RESOURCE_FALLBACK)


def test_hidden_pages_are_not_in_legacy_sidebar():
    menu_ids = set(_source_sidebar_ids())
    for page in HIDDEN:
        assert page["id"] not in menu_ids
        assert page["visibility"] == "hidden"
    for page in SIDEBAR:
        assert page["visibility"] == "sidebar"


def test_every_page_renderer_is_dispatched_and_defined():
    line = _open_page_line()
    for page in SIDEBAR + HIDDEN:
        source = (STATIC / page["source"]).read_text(encoding="utf-8")
        if page["renderer"] == "registerPage":
            assert re.search(rf"registerPage\('{page['id']}'|registerPage\(PAGE_ID", source), page["id"]
            continue
        assert re.search(rf"(function {page['renderer']}\b|\b{page['renderer']}=)", source), page["id"]
        assert f"if(id==='{page['id']}')return {page['renderer']}(" in line, page["id"]


def test_overview_renderer_stays_in_pages_overview_js():
    overview = next(p for p in SIDEBAR if p["id"] == "overview")
    assert overview["renderer"] == "renderOverview"
    assert overview["source"] == "pages/overview.js"
    assert "/static/pages/overview.js" in APP_HTML


# --------------------------------------------------------- permission baseline

def test_permission_matrix_matches_app_js():
    perms = _page_permission()
    super_admin = _super_admin_pages()
    for page in SIDEBAR + HIDDEN:
        expected = page["permission"]
        if page["id"] in super_admin:
            assert expected == {"kind": "super_admin_role"}, page["id"]
        elif page["id"] in perms:
            assert expected == {"kind": "permission", "code": perms[page["id"]]}, page["id"]
        else:
            assert expected == {"kind": "authenticated"}, page["id"]
    inventoried = {p["id"] for p in SIDEBAR + HIDDEN}
    assert set(perms) <= inventoried
    assert super_admin <= inventoried


def test_permission_gate_is_single_canopenpage():
    assert "const canOpenPage=(page)=>SUPER_ADMIN_PAGES.has(page)?isSuperAdmin():(!PAGE_PERMISSION[page]||hasPermission(PAGE_PERMISSION[page]));" in APP_JS
    assert "if(!canOpenPage(id)){content.innerHTML='<div class=\"empty danger\"><b>Không có quyền truy cập</b>" in APP_JS
    # Legacy sidebar still hides what the role cannot open.
    assert "if(!canOpenPage(group.page))continue;" in APP_JS
    assert "if(item.page&&!canOpenPage(item.page))continue;" in APP_JS


# ------------------------------------------------------------ deep-link baseline

def test_deep_link_baseline_is_wired():
    assert "bootParams.get('page')||'overview'" in APP_HTML
    assert "bootParams.get('session')" in APP_HTML
    assert "deepLinkPo&&initialPage==='production-orders'" in APP_HTML
    assert "bootParams.get('roles')&&initialPage==='users'" in APP_HTML
    assert "bootParams.get('guide')==='esp-kiosk'" in APP_HTML
    assert "{historyMode:'replace'}" in APP_HTML
    assert "window.addEventListener('popstate'" in APP_JS
    assert "params.get('page')||'overview'" in APP_JS
    for param in ("session", "po_id", "roles", "guide", "date", "tab", "ui_refactor"):
        assert param in INVENTORY["globalDeepLinkParams"]


# --------------------------------------------------------- standalone surfaces

def test_standalone_surfaces_still_exist():
    for surface in STANDALONE:
        source = (ROOT / surface["source"]).read_text(encoding="utf-8")
        route = re.sub(r"<([a-z_]+)>", r"<int:\1>", surface["route"])
        assert f"'{route}'" in source, surface["id"]
        assert f"'{surface['template']}'" in source, surface["id"]
        assert (WEB / "templates" / surface["template"]).exists()


# ------------------------------------------------------------ viewport baseline

def test_viewport_baselines_are_recorded():
    assert [(v["width"], v["height"]) for v in INVENTORY["viewportBaselines"]] == [
        (1366, 768), (1920, 1080), (390, 844), (430, 932),
    ]
