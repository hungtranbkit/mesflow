from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_session_filters_are_flat_visible_and_responsive():
    js = (ROOT / "app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "app/mesflow/web/static/ui.css").read_text(encoding="utf-8")
    session_source = js[js.index("async function renderSessionManagement"):js.index("async function renderRolePermissions")]

    for control in ('smDate', 'smPo', 'smPart', 'smOp', 'smEmp', 'smStatus', 'smSearch'):
        assert f'id="{control}"' in session_source
    assert 'Thêm bộ lọc' not in session_source
    assert 'session-more-filters' not in session_source
    assert '.session-manage-filter{display:grid' in css
    assert '@media(max-width:900px)' in css
    assert '@media(max-width:520px)' in css


def test_session_filter_frontend_normalizes_dependencies_and_guards_stale_requests():
    js = (ROOT / "app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    session_source = js[js.index("async function renderSessionManagement"):js.index("async function renderRolePermissions")]

    assert "let loadSequence=0" in session_source
    assert "if(sequence!==loadSequence)return null" in session_source
    assert "el('smPart').value='';el('smOp').value=''" in session_source
    assert "el('smOp').value='';refreshFiltered()" in session_source
    assert "normalized.po!==requested.po||normalized.part!==requested.part" in session_source
    assert "await loadSessions(false,{po:query.get('po')||'',part:query.get('part')||'',operation:query.get('operation')||''" in session_source
    for legacy_filter in ('smDate', 'smEmp', 'smStatus', 'smSearch'):
        assert legacy_filter in session_source


def test_backend_filter_catalog_uses_po_and_part_relationship_ids():
    source = (ROOT / "app/mesflow/db/repositories/analytics.py").read_text(encoding="utf-8")
    method = source[source.index("def recent_session_operations"):source.index("class KPIRepository")]

    assert "part_filter_sql=' WHERE production_order_id=%s' if po_id else ''" in method
    assert "if po_id: operation_filter_conditions.append('production_order_id=%s')" in method
    assert "if part_id: operation_filter_conditions.append('part_id=%s')" in method
    assert 'SELECT id,production_order_id,code,name FROM parts{part_filter_sql}' in method
    assert 'SELECT id,production_order_id,part_id,code,name FROM operations{operation_filter_sql}' in method
