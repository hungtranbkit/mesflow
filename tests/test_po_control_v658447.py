from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_po_control_backend_contract():
    repo=(ROOT/'app/mesflow/db/repositories/analytics.py').read_text()
    web=(ROOT/'app/mesflow/web/analytics.py').read_text()
    assert 'def production_control' in repo
    assert "@bp.get('/production-control')" in web
    for token in ['priority_score','priority_reasons','recommended_action','wip_qty','schedule_gap_percent','control_state']:
        assert token in repo
    assert "input_available_qty" in repo
    assert "PREDECESSOR" in repo
    assert "CHỜ ĐẦU VÀO" in repo
    assert "LÀM NGAY" in repo

def test_po_control_frontend_contract():
    app=(ROOT/'app/mesflow/web/static/app.js').read_text()
    html=(ROOT/'app/mesflow/web/templates/app.html').read_text()
    page=(ROOT/'app/mesflow/web/static/pages/po-control.js').read_text()
    assert "page:'po-control'" in app
    assert "renderPoControl()" in app
    assert 'pages/po-control.js' in html
    for token in ['Ưu tiên Operation theo PO','WIP đầu vào','Ưu tiên cao nhất','Deadline gần nhất','Tiến độ thấp nhất','Dòng vật tư']:
        assert token in page
    assert "setInterval(load,15000)" in page

def test_version_bumped():
    assert '65.8.44.8' in (ROOT/'release.json').read_text()
    assert "65.8.44.8" in (ROOT/'app/mesflow/__init__.py').read_text()
