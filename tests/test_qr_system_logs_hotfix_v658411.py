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
    # DOM-ref object was later renamed from `refs` to `r` -- same pattern,
    # same isolation guarantee (local object, not a global keyed by DOM id).
    assert "r.q.value" in js
    # The one generic message was later split into more specific per-tab
    # messages (Action Log vs Error Trace) -- still local, still no global.
    assert "Không thể tải Action Log" in js
    assert "if(slQ.value)" not in js

def test_template_loads_system_logs_module():
    html=text('app/mesflow/web/templates/app.html')
    assert '/static/pages/system-logs.js' in html
