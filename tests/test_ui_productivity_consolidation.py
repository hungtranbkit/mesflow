"""UI consolidation P3 -- one canonical Năng suất screen.

employee-productivity, kpi-employees and kpi-operations collapse into the
canonical `productivity` screen with exactly two tabs, "Nhân viên" and
"Operation". Legacy page IDs stay addressable (kpi-employees as an alias),
backend routes are untouched, and the Nhân viên tab keeps its filters,
filter-recalculated KPIs, Excel export and the "NV xác nhận" column.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/mesflow/web/static"
NAV = STATIC / "core/canonical-nav.js"
APP_JS = STATIC / "app.js"
EMP_JS = STATIC / "pages/employee-productivity.js"
OPS_JS = STATIC / "pages/productivity-operations.js"
APP_HTML = ROOT / "app/mesflow/web/templates/app.html"
ANALYTICS = ROOT / "app/mesflow/web/analytics.py"
EXCEL = ROOT / "app/mesflow/web/productivity_excel.py"

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is required for canonical navigation contract tests")


def _node(expr: str):
    script = (
        "const N=require('./app/mesflow/web/static/core/canonical-nav.js');"
        "let out=null;" + expr + "process.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def _ops_module(expr: str):
    """Evaluate pages/productivity-operations.js in a bare VM (no DOM)."""
    script = (
        "const vm=require('vm');const fs=require('fs');"
        "const ctx={registerPage:()=>{},console};vm.createContext(ctx);"
        f"vm.runInContext(fs.readFileSync({json.dumps(str(OPS_JS))},'utf8'),ctx);"
        f"const out=vm.runInContext({json.dumps(expr)},ctx);"
        "process.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


# ------------------------------------------------------------ canonical screen
@needs_node
def test_productivity_is_one_screen_with_nhan_vien_and_operation_tabs():
    got = _node("const s=N.getScreen('productivity');out=s.tabs.map(t=>[t.id,t.label,t.page]);")
    assert got == [
        ["employees", "Nhân viên", "employee-productivity"],
        ["operations", "Operation", "kpi-operations"],
    ]


@needs_node
@pytest.mark.parametrize(
    "query,tab,page",
    [
        ("page=employee-productivity", "employees", "employee-productivity"),
        ("page=kpi-employees", "employees", "employee-productivity"),
        ("page=kpi-operations", "operations", "kpi-operations"),
        ("page=productivity", "employees", "employee-productivity"),
        ("page=productivity&tab=operations", "operations", "kpi-operations"),
        ("screen=productivity&tab=operations", "operations", "kpi-operations"),
        ("screen=kpi-employees", "employees", "employee-productivity"),
    ],
)
def test_legacy_and_canonical_urls_land_on_the_productivity_tab(query: str, tab: str, page: str):
    got = _node(f"out=N.resolveLocation(new URLSearchParams('ui_refactor=1&{query}&from=2026-09-01'),()=>true);")
    assert (got["screen"], got["tab"], got["page"]) == ("productivity", tab, page)


@needs_node
def test_canonical_url_keeps_unrelated_params_and_marks_active_tab():
    got = _node("out=N.serialize('kpi-operations','ui_refactor=1&page=employee-productivity&screen=productivity&tab=employees&po_id=7');")
    params = dict(p.split("=", 1) for p in got.split("&"))
    assert params == {"ui_refactor": "1", "page": "kpi-operations", "screen": "productivity", "tab": "operations", "po_id": "7"}


@needs_node
def test_kpi_employees_alias_never_removes_access():
    # A role without session.view could open kpi-employees before; refactor
    # mode must keep rendering it rather than a permission error.
    got = _node(
        "const can=p=>p!=='employee-productivity';"
        "out={alias:N.renderTarget('kpi-employees',can),full:N.renderTarget('kpi-employees',()=>true),"
        "screens:N.visibleScreens(can).map(s=>s.id)};"
    )
    assert got["alias"] == "kpi-employees"
    assert got["full"] == "employee-productivity"
    # Operation tab is a previously hidden page: it must not surface the
    # screen for a role that never saw Năng suất in the sidebar.
    assert "productivity" not in got["screens"]


# ------------------------------------------------------------ Operation tab
def test_operation_tab_is_a_real_renderer_not_a_raw_table_dump():
    app = APP_JS.read_text(encoding="utf-8")
    assert "renderSimple('KPI Operation'" not in app
    src = OPS_JS.read_text(encoding="utf-8")
    assert "registerPage('kpi-operations'" in src
    assert "api('/api/kpi/operations?limit=1000')" in src
    assert "MFUI.filterBar(" in src
    assert "drawKpis(kpoSummary(rows))" in src  # KPIs from the FILTERED rows
    html = APP_HTML.read_text(encoding="utf-8")
    assert html.index('src="/static/app.js') < html.index('src="/static/pages/productivity-operations.js')


@needs_node
def test_operation_percentages_follow_the_active_filters():
    items = [
        {"code": "OP10", "name": "Cắt", "po_code": "PO-A", "status": "DONE", "plan_qty": 100, "done_qty": 100, "defect_qty": 0, "session_count": 3},
        {"code": "OP20", "name": "Hàn", "po_code": "PO-A", "status": "RUNNING", "plan_qty": 100, "done_qty": 40, "defect_qty": 10, "session_count": 2},
        {"code": "OP10", "name": "Cắt", "po_code": "PO-B", "status": "RUNNING", "plan_qty": 50, "done_qty": 5, "defect_qty": 5, "session_count": 1},
    ]
    got = _ops_module(
        f"const items={json.dumps(items)};"
        "({all:kpoSummary(kpoFilterRows(items,{})),"
        "poA:kpoSummary(kpoFilterRows(items,{po:'PO-A'})),"
        "running:kpoSummary(kpoFilterRows(items,{status:'RUNNING'})),"
        "search:kpoFilterRows(items,{search:'hàn'}).map(x=>x.code),"
        "none:kpoSummary(kpoFilterRows(items,{po:'PO-Z'}))})"
    )
    assert got["all"]["operation_count"] == 3
    assert got["all"]["completion_percent"] == pytest.approx(145 / 250 * 100)
    assert got["all"]["yield_percent"] == pytest.approx(145 / 160 * 100)
    assert got["poA"]["completion_percent"] == pytest.approx(140 / 200 * 100)
    assert got["poA"]["session_count"] == 5
    assert got["running"]["yield_percent"] == pytest.approx(45 / 60 * 100)
    assert got["search"] == ["OP20"]
    assert got["none"]["completion_percent"] is None
    assert got["none"]["yield_percent"] is None


# ------------------------------------------------------------ Nhân viên tab
def test_employee_tab_keeps_filters_kpis_export_and_nv_xac_nhan():
    js = EMP_JS.read_text(encoding="utf-8")
    assert "registerPage('employee-productivity'" in js
    for control in ("epFrom", "epTo", "epSearch", "epDept"):
        assert f'id="{control}"' in js
    assert "drawKpis(summaryForVisibleRows(rows));" in js
    # Excel and print share ONE filter serializer (hotfix 380).
    query = js.split("const reportQuery = () => {", 1)[1].split("};", 1)[0]
    for key in ("'from'", "'to'", "'search'", "'department'", "'sort'", "'dir'"):
        assert f"q.set({key}" in query
    export = js.split("const exportExcel = () => {", 1)[1].split("};", 1)[0]
    assert "const q = reportQuery();" in export
    assert "/api/reports/employee-productivity/export.xlsx" in export
    assert '"NV xác nhận"' in EXCEL.read_text(encoding="utf-8")


def test_employee_filters_survive_a_tab_switch():
    js = EMP_JS.read_text(encoding="utf-8")
    assert "const epFilterMemory = {" in js
    assert "epFilterMemory.from || epMonthStartHcm()" in js
    assert "epFilterMemory.to || epTodayHcm()" in js
    assert "value=\"${esc(epFilterMemory.search)}\"" in js
    assert "currentDept = deptSel.value || epFilterMemory.dept" in js
    ops = OPS_JS.read_text(encoding="utf-8")
    assert "const kpoFilterMemory = {" in ops


def test_backend_productivity_and_kpi_routes_are_unchanged():
    src = ANALYTICS.read_text(encoding="utf-8")
    for route in (
        "@bp.get('/reports/employee-productivity')",
        "@bp.get('/reports/employee-productivity/export.xlsx')",
        "@bp.get('/reports/employee-productivity/<int:employee_id>')",
        "@bp.get('/kpi/employees')",
        "@bp.get('/kpi/operations')",
        "@bp.get('/wallboard/employee-productivity')",
    ):
        assert route in src


# ------------------------------------------------------------ golden reference
UI_JS = STATIC / "core/ui.js"
UI_CSS = STATIC / "ui.css"
GOLDEN_PRIMITIVES = ("screenTabs", "bindScreenTabs", "reportBar", "kpiCards", "tableHead", "meter")


def test_golden_reference_primitives_are_exported_from_mfui():
    src = UI_JS.read_text(encoding="utf-8")
    export = next(l for l in src.splitlines() if l.strip().startswith("return {statusBadge"))
    names = {n.strip() for n in export.strip()[len("return {"):].rstrip("};").split(",")}
    assert set(GOLDEN_PRIMITIVES) <= names


def test_both_productivity_tabs_are_built_from_the_shared_primitives():
    for path, active in ((EMP_JS, "employee-productivity"), (OPS_JS, "kpi-operations")):
        src = path.read_text(encoding="utf-8")
        assert 'class="page-shell mf-report" data-report="productivity"' in src
        assert f"MFUI.screenTabs({{ screen: 'productivity', active: '{active}', canOpen: canOpenPage }})" in src
        assert "MFUI.bindScreenTabs(content, openPage)" in src
        for primitive in ("MFUI.reportBar(", "MFUI.filterBar(", "MFUI.kpiCards(", "MFUI.tableHead(", "MFUI.loadingState(", "MFUI.emptyState(", "MFUI.errorState("):
            assert primitive in src, (path.name, primitive)
        assert "mf-table-panel" in src and "mf-table" in src
    # Exactly one primary action on the screen: Xuất Excel.
    emp = EMP_JS.read_text(encoding="utf-8")
    bar = emp.split("MFUI.reportBar(", 1)[1].split("})}", 1)[0]
    assert bar.count("btn primary") == 1 and 'id="epExport"' in bar


@needs_node
def test_productivity_owns_its_tabs_so_the_shell_strip_stays_hidden():
    got = _node("const s=N.getScreen('productivity');out={kind:s.kind,inline:s.inlineTabs};")
    assert got == {"kind": "report", "inline": True}
    assert "tabs.length<2||screen?.inlineTabs" in NAV.read_text(encoding="utf-8")


def test_golden_reference_css_layer_is_scoped_and_tokenized():
    css = UI_CSS.read_text(encoding="utf-8")
    layer = css.split("GOLDEN VISUAL REFERENCE", 1)[1]
    for selector in (".mf-report{", ".mf-report-bar{", ".mf-kpis{", ".mf-kpi{", ".mf-table th{", ".mf-table th.num,.mf-table td.num{text-align:right}", ".mf-badge{", ".mf-meter{"):
        assert selector in layer, selector
    assert "position:sticky;top:0" in layer  # sticky table header on desktop
    assert "@media(max-width:700px)" in layer and "@media(max-width:1100px)" in layer
    for token in ("--table-head-h", "--table-row-hover", "--table-sticky-max", "--meter-track", "--meter-fill"):
        # Declared once, inside the single token :root block (see
        # test_ui_design_tokens_single_source.py), not in the component layer.
        assert css.count(f"\n  {token}:") == 1 and f"{token}:" not in layer, token
