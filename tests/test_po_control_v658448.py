from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]

def test_po_control_po_filter_and_kpi_layout():
    page=(ROOT/'app/mesflow/web/static/pages/po-control.js').read_text(encoding='utf-8')
    css=(ROOT/'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')
    for token in ['pcPoFilter','Tất cả PO','pc-kpis','pc-kpi','selectedPo=e.target.value']:
        assert token in page or token in css
    assert '<strong>${N(x[1])}</strong>' in page
    assert '.pc-kpi strong' in css

def test_runtime_versions_all_match_658448():
    version=(ROOT/'VERSION.txt').read_text().strip()
    # __init__.py reads VERSION.txt at import time rather than embedding a
    # literal (see its own docstring) -- import and compare instead of
    # grepping for a string that no longer appears in source.
    import mesflow
    assert mesflow.__version__==version
    assert json.loads((ROOT/'release.json').read_text())['version']==version
    assert f'mesflow-app:{version}' in (ROOT/'compose.yml').read_text()
