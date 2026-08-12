from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_version():
    assert tuple(map(int,(ROOT/'VERSION.txt').read_text().strip().split('.'))) >= (65,8,33)

def test_kiosk_error_codes_and_help():
    js=(ROOT/'app/mesflow/web/static/kiosk.js').read_text()
    html=(ROOT/'app/mesflow/web/templates/kiosk.html').read_text()
    api=(ROOT/'app/mesflow/web/kiosk.py').read_text()
    for code in ('SCN-001','SCN-002','EMP-001','OP-001','PO-001','NET-001','SYS-500'):
        assert code in js or code in api
    assert 'error-code' in html and 'error-action' in html
    assert 'error_code=' in api and 'action=' in api

def test_hcm_timezone_is_explicit():
    app=(ROOT/'app/mesflow/web/static/app.js').read_text()
    kiosk=(ROOT/'app/mesflow/web/static/kiosk.js').read_text()
    conn=(ROOT/'app/mesflow/db/connection.py').read_text()
    compose=(ROOT/'compose.yml').read_text()
    assert "Asia/Ho_Chi_Minh" in app
    assert "timeZone:'Asia/Ho_Chi_Minh'" in kiosk
    assert "SET TIME ZONE 'UTC'" in conn
    assert 'MESFLOW_TIMEZONE' in compose
    assert '+07:00' in app
