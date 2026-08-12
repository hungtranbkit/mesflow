from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

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
    js=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    for text in ('Xuất Excel','Nhập Excel','Tạo từ Excel','/api/operations/import','/api/templates/import-workbook'):
        assert text in js
