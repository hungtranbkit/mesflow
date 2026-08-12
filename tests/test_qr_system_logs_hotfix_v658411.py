from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def text(path): return (ROOT/path).read_text(encoding='utf-8')

def test_qr_page_uses_local_dom_refs_and_normalizes_response():
    js=text('app/mesflow/web/static/pages/qr-print.js')
    assert "const $=id=>document.getElementById(id)" in js
    assert "raw?.results" in js
    assert "Không thể hiển thị danh sách QR" in js

def test_system_logs_isolated_module_and_no_dom_id_globals():
    js=text('app/mesflow/web/static/pages/system-logs.js')
    assert "const $=id=>document.getElementById(id)" in js
    assert "refs.q.value" in js
    assert "Không thể tải Nhật ký hệ thống" in js
    assert "if(slQ.value)" not in js

def test_template_loads_system_logs_module():
    html=text('app/mesflow/web/templates/app.html')
    assert '/static/pages/system-logs.js' in html
