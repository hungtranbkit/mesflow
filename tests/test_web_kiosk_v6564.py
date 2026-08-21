from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_kiosk_assets_and_route_exist():
    app=(ROOT/'app/mesflow/web/app.py').read_text()
    kiosk=(ROOT/'app/mesflow/web/kiosk.py').read_text()
    html=(ROOT/'app/mesflow/web/templates/kiosk.html').read_text()
    js=(ROOT/'app/mesflow/web/static/kiosk.js').read_text()
    assert 'register_blueprint(kiosk_bp)' in app
    assert "@bp.get('/kiosk')" in kiosk
    assert '/api/kiosk-web/scan' in kiosk
    assert '/api/kiosk-web/start' in kiosk
    assert '/api/kiosk-web/finish/' in kiosk
    assert 'QUÉT THẺ NHÂN VIÊN' in html
    assert "WF|EMP|" in kiosk and "WF|OP|" in kiosk
    assert "state === 'operation'" in js

def test_kiosk_demo_initializes_without_secure_context_random_uuid():
    html=(ROOT/'app/mesflow/web/templates/kiosk.html').read_text()
    js=(ROOT/'app/mesflow/web/static/kiosk.js').read_text()
    assert 'function newDeviceUuid()' in js
    assert 'globalThis.crypto?.randomUUID' in js
    assert 'crypto.randomUUID()' not in js.replace('globalThis.crypto.randomUUID()', '')
    assert 'data-testid="kiosk-demo-toggle"' in html
    assert 'data-testid="kiosk-demo-panel"' in html
    assert 'data-testid="kiosk-demo-content"' in html
    assert "demoToggle.setAttribute('aria-expanded','true')" in js
    assert "demoToggle.setAttribute('aria-expanded','false')" in js
