"""UI consolidation P1 -- canonical navigation contract (core/canonical-nav.js).

The resolve/serialize/permission logic is exercised in a real Node process
against the real module, with the REAL permission gate lifted verbatim from
app.js (PAGE_PERMISSION / SUPER_ADMIN_PAGES / hasPermission / canOpenPage), so
a Python re-implementation can never pass while the JS disagrees.

The flag-off / flag-on DOM behavior is covered in a real browser by
tests/test_ui_canonical_nav_browser.py.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "app" / "mesflow" / "web"
STATIC = WEB / "static"
MODULE = STATIC / "core" / "canonical-nav.js"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
APP_HTML = (WEB / "templates" / "app.html").read_text(encoding="utf-8")
INVENTORY = json.loads((ROOT / "docs" / "ui-inventory.json").read_text(encoding="utf-8"))

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")

EXPECTED_SCREENS = [
    "overview", "planning", "templates", "operations-sessions", "quality", "productivity",
    "kiosk-admin", "master-data", "trace-logs", "admin", "system",
]
EXPECTED_TABS = {
    "overview": [("realtime", "overview"), ("daily", "dashboard")],
    "planning": [("orders", "production-orders"), ("schedule", "production-schedule")],
    "templates": [("templates", "templates")],
    "operations-sessions": [("all", "session-management"), ("exceptions", "session-exceptions")],
    "quality": [("rework", "rework-queue"), ("qc", "qc")],
    "productivity": [("employees", "employee-productivity"), ("operations", "kpi-operations")],
    "kiosk-admin": [("stations", "kiosk-management"), ("events", "kiosk-events")],
    "master-data": [("employees", "employees"), ("qr", "qr-print"), ("equipment", "equipment")],
    "trace-logs": [("trace", "production-trace"), ("business", "business-audit"), ("application", "system-logs")],
    "admin": [("users", "users"), ("calendar", "working-calendar")],
    "system": [("overview", "system-overview"), ("errors", "system-errors"), ("logs", "system-logs-it"),
               ("services", "system-services"), ("diagnostics", "system-diagnostics"), ("audit", "system-audit")],
}
# Every legacy page listed in the plan's compatibility table (section 4) plus
# the aliases named in the P1 task.
PLAN_ALIASES = {
    "dashboard": ("overview", "daily"),
    "session-management": ("operations-sessions", "all"),
    "session-exceptions": ("operations-sessions", "exceptions"),
    "sessions": ("operations-sessions", "all"),
    "rework-queue": ("quality", "rework"),
    "qc": ("quality", "qc"),
    "employee-productivity": ("productivity", "employees"),
    "kpi-employees": ("productivity", "employees"),
    "kpi-operations": ("productivity", "operations"),
    "kiosk-management": ("kiosk-admin", "stations"),
    "kiosk-events": ("kiosk-admin", "events"),
    "production-trace": ("trace-logs", "trace"),
    "business-audit": ("trace-logs", "business"),
    "system-logs": ("trace-logs", "application"),
    "production-orders": ("planning", "orders"),
    "production-schedule": ("planning", "schedule"),
    "employees": ("master-data", "employees"),
    "qr-print": ("master-data", "qr"),
    "equipment": ("master-data", "equipment"),
    "users": ("admin", "users"),
    "working-calendar": ("admin", "calendar"),
}


def _permission_prelude():
    start = APP_JS.index("const PAGE_PERMISSION=")
    end = APP_JS.index("\n", APP_JS.index("const canOpenPage="))
    return APP_JS[start:end]


def _node(body, user=None):
    """Run `body` (must end by assigning `out`) with the module as `N` and the
    real app.js permission gate bound to MESFLOW_USER=user."""
    script = (
        "globalThis.window={MESFLOW_USER:" + json.dumps(user or {"role": "admin", "permissions": []}) + "};\n"
        + _permission_prelude() + "\n"
        + "const N=require(" + json.dumps(str(MODULE)) + ");\nlet out;\n"
        + body + "\nprocess.stdout.write(JSON.stringify(out));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _resolve(query, user=None):
    return _node(f"out=N.resolveLocation(new URLSearchParams({json.dumps(query)}),canOpenPage);", user)


# ------------------------------------------------------------- screen/tab map

@needs_node
def test_exactly_eleven_canonical_screens_in_order():
    assert _node("out=N.SCREENS.map(s=>s.id);") == EXPECTED_SCREENS


@needs_node
def test_canonical_tab_mapping_is_exact():
    got = _node("out=Object.fromEntries(N.SCREENS.map(s=>[s.id,s.tabs.map(t=>[t.id,t.page])]));")
    assert {k: [tuple(t) for t in v] for k, v in got.items()} == EXPECTED_TABS


@needs_node
def test_every_plan_legacy_page_aliases_to_its_canonical_tab():
    got = _node("out=Object.fromEntries(" + json.dumps(list(PLAN_ALIASES)) + ".map(p=>[p,N.legacyToCanonical(p)]));")
    for page, (screen, tab) in PLAN_ALIASES.items():
        assert got[page]["screen"] == screen and got[page]["tab"] == tab, page
    assert got["sessions"]["alias"] is True
    assert got["kpi-employees"]["alias"] is True


@needs_node
def test_every_inventoried_page_is_mapped_or_explicitly_unmapped():
    """No legacy page may silently fall out of refactor mode."""
    pages = [p["id"] for p in INVENTORY["sidebarDestinations"] + INVENTORY["hiddenSpaPages"]]
    got = _node("out={mapped:Object.fromEntries(" + json.dumps(pages) + ".map(p=>[p,N.legacyToCanonical(p)])),unmapped:Object.keys(N.UNMAPPED_LEGACY)};")
    for entry in INVENTORY["sidebarDestinations"] + INVENTORY["hiddenSpaPages"]:
        mapped = got["mapped"][entry["id"]]
        if entry["canonical"] is None:
            assert mapped is None and entry["id"] in got["unmapped"], entry["id"]
        else:
            assert mapped == entry["canonical"], entry["id"]
    assert set(got["unmapped"]) == {"tutorials", "notifications", "audit", "monitoring", "daily-dashboard-kiosk"}


@needs_node
def test_help_and_notifications_are_not_primary_destinations():
    ids = _node("out=N.visibleScreens(canOpenPage).map(s=>s.id).concat(N.SCREENS.flatMap(s=>s.tabs.map(t=>t.page)));")
    assert "tutorials" not in ids and "notifications" not in ids


@needs_node
def test_monitoring_is_not_aliased_to_super_admin_system_screen():
    # monitoring has no page permission; system-overview is Super Admin only.
    assert _resolve("page=monitoring") == {"screen": None, "tab": None, "page": "monitoring", "alias": False}


# -------------------------------------------------- Overview / session guards

@needs_node
def test_overview_guard_realtime_tab_still_renders_legacy_overview():
    assert _resolve("page=overview") == {"screen": "overview", "tab": "realtime", "page": "overview", "alias": False}
    assert _resolve("screen=overview&tab=realtime")["page"] == "overview"
    assert _resolve("")["page"] == "overview"  # bare URL still lands on Overview
    assert _resolve("page=dashboard") == {"screen": "overview", "tab": "daily", "page": "dashboard", "alias": False}
    # Overview renderer is untouched and still the one openPage dispatches to.
    assert "if(id==='overview')return renderOverview();" in APP_JS
    assert "canonical" not in (STATIC / "pages" / "overview.js").read_text(encoding="utf-8").lower()


@needs_node
def test_session_alias_guard():
    assert _resolve("page=sessions") == {"screen": "operations-sessions", "tab": "all", "page": "session-management", "alias": True}
    assert _resolve("page=session-exceptions&session=42")["tab"] == "exceptions"
    # Role WITHOUT session.view keeps the legacy raw `sessions` page it could
    # always open -- refactor mode never takes access away.
    restricted = {"role": "viewer", "permissions": ["overview.view"]}
    assert _resolve("page=sessions", restricted)["page"] == "sessions"


# ----------------------------------------------------- URL serialize/resolve

@needs_node
def test_every_tab_round_trips_through_the_url():
    rows = _node(
        "out=N.SCREENS.flatMap(s=>s.tabs.map(t=>{const q=N.serialize(t.page,'session=7&po_id=3&roles=1&ui_refactor=1');"
        "return {screen:s.id,tab:t.id,page:t.page,q,r:N.resolveLocation(new URLSearchParams(q),canOpenPage),"
        "bare:N.resolveLocation(new URLSearchParams({screen:s.id,tab:t.id}),canOpenPage)}}));"
    )
    assert len(rows) == sum(len(t) for t in EXPECTED_TABS.values()) == 27
    for row in rows:
        params = dict(p.split("=", 1) for p in row["q"].split("&"))
        assert params["page"] == row["page"] and params["screen"] == row["screen"] and params["tab"] == row["tab"]
        # legacy deep-link params survive untouched
        assert params["session"] == "7" and params["po_id"] == "3" and params["roles"] == "1" and params["ui_refactor"] == "1"
        assert (row["r"]["screen"], row["r"]["tab"], row["r"]["page"]) == (row["screen"], row["tab"], row["page"])
        assert (row["bare"]["screen"], row["bare"]["tab"], row["bare"]["page"]) == (row["screen"], row["tab"], row["page"])


@needs_node
def test_page_param_wins_over_dashboard_owned_tab_param():
    # Dashboard theo ngày writes its own tab=people|output into the same URL.
    got = _resolve("page=dashboard&screen=overview&tab=people&date=2026-09-01")
    assert (got["screen"], got["tab"], got["page"]) == ("overview", "daily", "dashboard")


@needs_node
def test_canonical_only_and_invalid_tab_urls_fall_back_to_first_permitted_tab():
    assert _resolve("screen=quality&tab=nope")["page"] == "rework-queue"
    assert _resolve("page=planning")["page"] == "production-orders"
    assert _resolve("page=planning&tab=schedule")["page"] == "production-schedule"
    assert _resolve("screen=kpi-employees")["page"] == "employee-productivity"


@needs_node
def test_unmapped_page_keeps_tutorials_tab_param():
    q = _node("out=N.serialize('tutorials','page=quality&screen=quality&tab=video');")
    params = dict(p.split("=", 1) for p in q.split("&"))
    assert params == {"page": "tutorials", "tab": "video"}


# ------------------------------------------------------ permission filtering

@needs_node
def test_permission_filtering_uses_legacy_page_permissions():
    admin = _node("out=N.visibleScreens(canOpenPage).map(s=>s.id);", {"role": "admin", "permissions": []})
    assert admin == EXPECTED_SCREENS[:-1]  # admin blanket pass never covers System
    superadmin = _node("out=N.visibleScreens(canOpenPage).map(s=>s.id);", {"role": "super_admin", "permissions": []})
    assert superadmin == EXPECTED_SCREENS

    rework_only = {"role": "operator", "permissions": ["rework.view"]}
    got = _node("out={screens:N.visibleScreens(canOpenPage).map(s=>s.id),quality:N.visibleTabs('quality',canOpenPage).map(t=>t.id),"
                "trace:N.visibleTabs('trace-logs',canOpenPage).map(t=>t.id)};", rework_only)
    assert got["screens"] == ["quality"]
    assert got["quality"] == ["rework", "qc"]
    assert got["trace"] == []


@needs_node
def test_hidden_legacy_tabs_never_add_a_screen_on_their_own():
    # qc / kpi-operations / kiosk-events carry no page permission, so any
    # logged-in user could already open them by URL -- but they were never in
    # the sidebar, so they must not make Quality/Productivity/Kiosk appear.
    got = _node("out=N.visibleScreens(canOpenPage).map(s=>s.id);", {"role": "viewer", "permissions": []})
    assert got == []


@needs_node
def test_restricted_trace_role_only_sees_its_tabs():
    user = {"role": "auditor", "permissions": ["business_audit.view"]}
    got = _node("out={s:N.visibleScreens(canOpenPage).map(s=>s.id),t:N.visibleTabs('trace-logs',canOpenPage).map(t=>t.id),"
                "target:N.renderTarget('trace-logs',canOpenPage)};", user)
    assert got == {"s": ["trace-logs"], "t": ["business"], "target": "business-audit"}


# ------------------------------------------------------------------ the flag

@needs_node
def test_flag_param_persists_and_can_be_cleared():
    got = _node(
        "const m=new Map();const st={getItem:k=>m.has(k)?m.get(k):null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)};"
        "out=[N.readFlag('',st),N.readFlag('?ui_refactor=1',st),N.readFlag('?page=users',st),N.readFlag('?ui_refactor=0',st),N.readFlag('',st),"
        "N.readFlag('?ui_refactor=1',{setItem(){throw new Error('private')},getItem(){throw new Error('private')}})];"
    )
    assert got == [False, True, True, False, False, True]


@needs_node
def test_module_is_inert_outside_a_browser():
    assert _node("out=N.enabled;") is False


# ---------------------------------------------- default legacy nav unchanged

def test_app_js_only_touches_nav_behind_the_flag():
    assert "const canonicalNav=window.MFCanonicalNav?.enabled?window.MFCanonicalNav:null;" in APP_JS
    assert "if(canonicalNav)canonicalNav.mount({nav,canOpenPage,openPage,navIcon,closeMobileSidebar});\nelse for(const group of menu){" in APP_JS
    assert "  if(canonicalNav){setActive(canonicalNav.activeButton(id));canonicalNav.afterActive(id)}\n  else setActive(btn||document.querySelector(`[data-page=\"${id}\"]`));" in APP_JS
    assert "{historyMode='push'}={}){if(canonicalNav)id=canonicalNav.renderTarget(id,canOpenPage);if(!canOpenPage(id)){" in APP_JS
    assert "AppNav.setPageUrl(id,{replace:historyMode==='replace'||samePage});if(canonicalNav)canonicalNav.syncUrl(id)}" in APP_JS
    assert "const id=canonicalNav?canonicalNav.resolveLocation(params,canOpenPage).page:(params.get('page')||'overview');" in APP_JS
    # Every canonicalNav use in app.js is one of the guarded hooks above.
    assert APP_JS.count("canonicalNav.") == 6
    # The legacy 25-entry menu definition is untouched (P0 inventory test
    # checks the IDs; this pins that nothing else rewrote the loop).
    assert APP_JS.count("for(const group of menu){") == 1


def test_template_loads_module_before_app_js_and_keeps_legacy_boot():
    assert APP_HTML.index("/static/core/canonical-nav.js") < APP_HTML.index("/static/app.js")
    assert "window.MFCanonicalNav?.enabled?MFCanonicalNav.resolveLocation(bootParams,canOpenPage).page:(bootParams.get('page')||'overview')" in APP_HTML


def test_tab_strip_reuses_shared_mf_tabs_and_legacy_renderers():
    source = MODULE.read_text(encoding="utf-8")
    assert "'mf-tabs canonical-tabs'" in source
    assert 'class="mf-tab' in source
    # Tabs open through the existing openPage() -- never a renderer of their own.
    assert "deps.openPage(btn.dataset.page)" in source
    assert not re.search(r"\brender(?!Target|Tabs)[A-Z]\w*\(", source)
    assert not re.search(r"\bapi\(|fetch\(", source)
