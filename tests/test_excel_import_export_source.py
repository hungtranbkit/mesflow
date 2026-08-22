from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def _js():
    return (ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')

def _slice(source,start_marker,end_marker):
    """Isolate one top-level function's body by its start/end markers, the
    same way the source is organized (one function per statement)."""
    assert start_marker in source, f'marker not found: {start_marker}'
    after=source.split(start_marker,1)[1]
    assert end_marker in after, f'end marker not found: {end_marker}'
    return start_marker+after.split(end_marker,1)[0]

def test_excel_backend_routes_and_dependency_present():
    source=(ROOT/'app/mesflow/web/excel_io.py').read_text(encoding='utf-8')
    app=(ROOT/'app/mesflow/web/app.py').read_text(encoding='utf-8')
    req=(ROOT/'requirements.txt').read_text(encoding='utf-8')
    assert "@bp.get('/export.xlsx')" in source
    assert "@bp.post('/import')" in source
    assert "@template_excel_bp.post('/import-workbook')" in source
    assert "@template_excel_bp.get('/<int:template_id>/export-workbook')" in source
    assert 'register_blueprint(excel_io_bp)' in app
    assert 'register_blueprint(template_excel_bp)' in app
    assert 'openpyxl==3.1.5' in req

def test_excel_ui_buttons_present():
    js=_js()
    for text in ('Xuất Excel','Nhập từ Excel','/api/operations/import','/api/templates/import-workbook'):
        assert text in js
    # Regression guard: the import button must never be mislabeled "Tạo từ
    # Excel" (looked like a PO-creation action and caused the reported
    # confusion) -- see fix/template-excel-import-location.
    assert 'Tạo từ Excel' not in js

def test_template_page_is_the_only_excel_import_entry_point():
    """Template must be the only screen offering 'import quy trình từ Excel'."""
    js=_js()
    tpl=_slice(js,'async function renderTemplates(selectId=null){','async function importTemplateExcel(){')
    assert 'Nhập từ Excel' in tpl
    assert 'tplImportFile' in tpl
    assert 'importTemplateExcel' in tpl

def test_template_import_flow_stays_on_template_and_selects_result():
    js=_js()
    fn=_slice(js,'async function importTemplateExcel(){','\nasync function saveTemplateOld(){')
    # Standard workbook contract: POST /api/templates/import-workbook.
    assert "fetch('/api/templates/import-workbook'" in fn
    # Success re-renders the Template page with the freshly imported
    # template pre-selected -- it must never navigate to Production Order.
    assert 'await renderTemplates(d.template_id)' in fn
    for forbidden in ('renderProductionOrders','productionOrderModal','instantiateTemplate','/api/operations/import'):
        assert forbidden not in fn, f'{forbidden} must not be reachable from the Template import flow'
    # UX copy (was previously wrong: loading said "Đang import...", and the
    # button was left mislabeled "Tạo từ Excel" after the request finished).
    assert "b.textContent='Đang nhập...'" in fn
    assert "b.textContent='Nhập từ Excel'" in fn
    # Failure keeps the user on the page (no navigation call in the catch
    # branch) and surfaces the error; the file input is always cleared.
    assert "catch(e){alert(e.message)}finally{" in fn
    assert "input.value=''" in fn

def test_production_order_page_has_no_excel_import_entry_point():
    js=_js()
    po=_slice(js,'async function renderProductionOrders(){','\nwindow.openProductionOrder=async function')
    assert 'operationExcelImportModal' not in po
    assert 'importExcel' not in po
    assert 'Nhập Excel' not in po
    # The two supported PO actions stay.
    assert 'Tạo PO từ Template' in po
    assert 'Xuất Excel' in po
