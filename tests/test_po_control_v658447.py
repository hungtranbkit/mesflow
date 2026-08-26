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

def test_production_control_data_is_surfaced_in_current_ui():
    # RETIRED test_po_control_frontend_contract (Codex audit Blocker 4,
    # category REAL BUG -- dead code, evidence below): the standalone "PO
    # Control" page (pages/po-control.js) still exists as a FILE but is
    # NOT included in app.html's <script> tags at all -- confirmed by
    # grepping app.html for every pages/*.js include. It is unreachable
    # dead code, not a wired page; there is no `page:'po-control'` menu
    # entry or `renderPoControl()` call anywhere in app.js either.
    #
    # This is not a lost user-facing feature: the same backend endpoint
    # this page called (/api/production-control) is still actively
    # consumed by the Overview dashboard (pages/overview.js) and the
    # Production Order detail view (app.js) -- the priority/control data
    # was consolidated into those two screens instead of a dedicated PO
    # Control page. Deleting the orphaned pages/po-control.js file is a
    # separate cleanup decision (out of scope for a test-suite fix) --
    # flagged in the audit report instead of silently deleted here.
    overview=(ROOT/'app/mesflow/web/static/pages/overview.js').read_text()
    app=(ROOT/'app/mesflow/web/static/app.js').read_text()
    html=(ROOT/'app/mesflow/web/templates/app.html').read_text()
    assert "'pages/po-control.js'" not in html and 'pages/po-control.js"' not in html
    assert "api('/api/production-control?limit=2000')" in overview
    assert "api('/api/production-control?limit=2000')" in app

def test_version_bumped():
    version=(ROOT/'VERSION.txt').read_text().strip()
    import json
    assert json.loads((ROOT/'release.json').read_text())['version']==version
    # __init__.py reads VERSION.txt at import time rather than embedding a
    # literal (see its own docstring) -- import and compare instead of
    # grepping for a string that no longer appears in source.
    import mesflow
    assert mesflow.__version__==version
