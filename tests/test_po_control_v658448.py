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
    assert version=='65.8.44.8'
    assert "__version__ = '65.8.44.8'" in (ROOT/'app/mesflow/__init__.py').read_text()
    assert json.loads((ROOT/'release.json').read_text())['version']=='65.8.44.8'
    assert 'image: mesflow-app:65.8.44.8' in (ROOT/'compose.yml').read_text()
