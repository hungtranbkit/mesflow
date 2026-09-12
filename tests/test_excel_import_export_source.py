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
    assert "@template_excel_bp.post('/preview-workbook')" in source
    assert 'register_blueprint(excel_io_bp)' in app
    assert 'register_blueprint(template_excel_bp)' in app
    assert 'register_blueprint(router_export_bp)' in app
    assert 'openpyxl==3.1.5' in req
    # openpyxl từ chối nhúng ảnh nếu thiếu Pillow, nên QR trên file router là
    # dependency của tính năng chứ không phải tuỳ chọn.
    assert 'Pillow==' in req
    router=(ROOT/'app/mesflow/web/router_export.py').read_text(encoding='utf-8')
    assert "@bp.get('/<int:po_id>/router.xlsx')" in router

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
    """Luồng nhập giờ có HAI bước: chọn file -> xem trước -> xác nhận.

    Bước xem trước được thêm vào vì file router sinh ra OP SETUP tự động: một
    file 44 sheet có thể đẻ ra hàng chục Operation phụ, và người bấm nút phải
    thấy trước khi nó xảy ra. Những bất biến CŨ vẫn phải đúng, chỉ là nay nằm
    ở hai hàm thay vì một:

      * xem trước gọi /api/templates/preview-workbook (không ghi CSDL);
      * xác nhận mới gọi /api/templates/import-workbook;
      * thành công thì ở lại trang Template và chọn sẵn Template vừa nhập --
        TUYỆT ĐỐI không nhảy sang Production Order;
      * thất bại thì giữ nguyên trang và luôn xoá input file.
    """
    js=_js()
    pick=_slice(js,'async function importTemplateExcel(){','\n// Người dùng đã tự tay')
    confirm=_slice(js,'function showTemplateImportPreview(file,data){','\nasync function loadTemplateImportHistory(')

    # Bước 1 chỉ xem trước -- không được nhập thẳng.
    assert "fetch('/api/templates/preview-workbook'" in pick
    assert 'import-workbook' not in pick, 'chọn file không được nhập luôn'
    assert 'showTemplateImportPreview(file,d)' in pick
    assert "b.textContent='Đang đọc file...'" in pick
    assert "b.textContent='Nhập từ Excel'" in pick
    assert "input.value=''" in pick

    # Bước 2 mới thực sự nhập, và ở lại đúng trang Template.
    assert "fetch('/api/templates/import-workbook'" in confirm
    assert 'await renderTemplates(d.template_id)' in confirm
    # Lựa chọn checkbox phải được gửi kèm, nếu không bước xem trước vô nghĩa.
    assert "fd.append('selection'" in confirm

    for fn in (pick, confirm):
        for forbidden in ('renderProductionOrders','productionOrderModal',
                          'instantiateTemplate','/api/operations/import'):
            assert forbidden not in fn, (
                f'{forbidden} must not be reachable from the Template import flow')


def test_setup_checkbox_defaults_to_checked_when_file_declares_setup():
    """OP SETUP phải được tick SẴN, và không thể tồn tại khi thiếu OP cha."""
    confirm=_slice(_js(),'function showTemplateImportPreview(file,data){',
                   '\nasync function loadTemplateImportHistory(')
    # Mặc định của hàng setup bám theo dữ liệu file (requires_setup), không
    # phải một hằng số -- và nó bắt đầu ở trạng thái đã tick.
    assert 'setup:!!op.requires_setup' in confirm
    assert 'class="tpl-pv-setup" checked' in confirm
    # Bỏ tick OP cha -> ô setup vừa tắt vừa khoá.
    assert 'setupBox.disabled=!st.op' in confirm
    assert 'setupBox.checked=st.op&&st.setup' in confirm
    # Chữ tiếng Việt người dùng đọc.
    for text in ('Tạo OP Setup','Thời gian setup:','SETUP'):
        assert text in confirm


def test_po_detail_has_a_visible_router_export_button():
    """Nút xuất file phải nằm thẳng trên thanh thao tác của PO, không giấu."""
    js=_js()
    toolbar=_slice(js,'<div class="po-detail-actions">','</div></div>')
    assert 'id="poExportRouter"' in toolbar
    assert 'Xuất Excel + QR' in toolbar
    # Và nó xuất ĐÚNG PO đang mở, lấy id từ state của màn chứ không từ bộ lọc.
    handler=_slice(js,'async function exportProductionOrderRouter(',
                   '\nwindow.openProductionOrder=async function')
    assert '/api/production-orders/${poId}/router.xlsx' in handler
    assert 'exportProductionOrderRouter(po.id,po.code,exportButton)' in js

def test_production_order_page_has_no_excel_import_entry_point():
    js=_js()
    po=_slice(js,'async function renderProductionOrders(){','\nwindow.openProductionOrder=async function')
    assert 'operationExcelImportModal' not in po
    assert 'importExcel' not in po
    assert 'Nhập Excel' not in po
    # The two supported PO actions stay.
    assert 'Tạo PO từ Template' in po
    assert 'Xuất Excel' in po
