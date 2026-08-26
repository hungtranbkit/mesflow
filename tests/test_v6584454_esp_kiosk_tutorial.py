from pathlib import Path

ROOT=Path(__file__).parents[1]


def test_version_and_runtime_tutorial_contract():
    expected=(ROOT/'VERSION.txt').read_text().strip()
    assert (ROOT/'VERSION.txt').read_text().strip()==expected
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==expected  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert expected in (ROOT/'release.json').read_text()
    assert f'mesflow-app:{expected}' in (ROOT/'compose.yml').read_text()
    app=(ROOT/'app/mesflow/web/app.py').read_text()
    js=(ROOT/'app/mesflow/web/static/app.js').read_text()
    assert "@app.get('/api/esp-kiosk-tutorial')" in app
    assert "@app.get('/esp-kiosk-tutorial/videos/<path:filename>')" in app
    assert "{label:'Hướng dẫn',page:'tutorials'}" in js
    assert "page:'esp-kiosk-tutorial'" not in js
    assert "renderEspKioskTutorial" in js
    assert "Cache-Control']='no-cache" in app
    assert "max-age=31536000, immutable" in app
    assert "'?v='+version" in app
    assert "x.title||'Video hướng dẫn'" in js
    assert "x.filename" not in js[js.index('async function renderEspKioskTutorial'):js.index('async function renderSimple')]
