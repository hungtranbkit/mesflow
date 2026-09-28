from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAV = ROOT / "app/mesflow/web/static/core/canonical-nav.js"
SYSTEM_JS = ROOT / "app/mesflow/web/static/pages/system-console.js"
APP_JS = ROOT / "app/mesflow/web/static/app.js"

SYSTEM_TABS = [
    ("overview", "system-overview"),
    ("errors", "system-errors"),
    ("logs", "system-logs-it"),
    ("services", "system-services"),
    ("diagnostics", "system-diagnostics"),
    ("audit", "system-audit"),
]

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is required for canonical navigation contract tests")


def _node(expr: str):
    script = (
        "const N=require('./app/mesflow/web/static/core/canonical-nav.js');"
        "let out=null;"
        + expr
        + "process.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


@needs_node
def test_system_is_one_lazy_console_with_six_tabs():
    got = _node(
        "const s=N.getScreen('system');"
        "out={kind:s.kind,lazy:s.lazy,tabs:s.tabs.map(t=>[t.id,t.page])};"
    )
    assert got == {
        "kind": "console",
        "lazy": True,
        "tabs": [list(x) for x in SYSTEM_TABS],
    }


@needs_node
@pytest.mark.parametrize("tab,page", SYSTEM_TABS)
def test_every_legacy_system_url_deep_links_to_correct_console_tab(tab: str, page: str):
    got = _node(
        f"out=N.resolveLocation(new URLSearchParams('ui_refactor=1&page={page}&keep=1'),()=>true);"
    )
    assert got["screen"] == "system"
    assert got["tab"] == tab
    assert got["page"] == page


@needs_node
def test_system_console_visibility_stays_super_admin_gated():
    system_pages = [page for _, page in SYSTEM_TABS]
    got = _node(
        f"const allowed=new Set({json.dumps(system_pages)});"
        "out={"
        "none:N.visibleScreens(()=>false).map(s=>s.id),"
        "superScreens:N.visibleScreens(p=>allowed.has(p)).map(s=>s.id),"
        "superTabs:N.visibleTabs('system',p=>allowed.has(p)).map(t=>t.id)"
        "};"
    )
    assert "system" not in got["none"]
    assert "system" in got["superScreens"]
    assert got["superTabs"] == [tab for tab, _ in SYSTEM_TABS]


def test_system_console_tabs_are_lazy_and_reuse_existing_renderers():
    nav = NAV.read_text()
    # P2 intentionally keeps the existing renderers. A tab click calls openPage
    # only for the selected legacy page; canonical navigation never calls the
    # system-health APIs itself or pre-renders other tabs.
    assert "kind:'console',lazy:true" in nav
    assert "deps.openPage(btn.dataset.page)" in nav
    assert "/api/system-health" not in nav

    source = SYSTEM_JS.read_text()
    expected_renderers = [
        "renderSystemOverview",
        "renderSystemErrors",
        "renderSystemLogsIT",
        "renderSystemServices",
        "renderSystemDiagnostics",
        "renderSystemAudit",
    ]
    for name in expected_renderers:
        assert f"async function {name}()" in source


def test_system_console_keeps_restart_and_diagnostics_actions():
    source = SYSTEM_JS.read_text()
    assert "/api/system-health/services/${encodeURIComponent(id)}/restart" in source
    assert "method:'POST'" in source
    assert "/api/system-health/diagnostics/${encodeURIComponent(id)}" in source
    assert "/api/system-health/diagnostics" in source


def test_client_and_api_super_admin_contract_remain_in_place():
    app = APP_JS.read_text()
    expected_pages = [page for _, page in SYSTEM_TABS]
    assert "const SUPER_ADMIN_PAGES=new Set(" in app
    for page in expected_pages:
        assert f"'{page}'" in app
    assert "SUPER_ADMIN_PAGES.has(page)?isSuperAdmin()" in app


def test_p2_marks_active_system_console_state_for_ui_contract():
    nav = NAV.read_text()
    assert "doc.body.dataset.canonicalScreen=mapped.screen" in nav
    assert "doc.body.dataset.canonicalTab=mapped.tab" in nav
    assert "doc.body.dataset.canonicalConsole=mapped.screen" in nav
    assert "canonical-console-tabs" in nav
