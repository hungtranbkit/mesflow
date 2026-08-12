from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WEB=(ROOT/'app/mesflow/web/execution.py').read_text()
REPO=(ROOT/'app/mesflow/db/repositories/execution.py').read_text()

def test_legacy_auth_prefers_device_uuid_and_falls_back():
    assert "request.headers.get('X-Device-UUID')" in WEB
    assert "request.headers.get('X-Device-ID')" in WEB
    assert "identity=_legacy_kiosk_identity(body)" in WEB
    assert "device=str(identity['device_uuid'])" in WEB

def test_connect_alias_and_stable_bind_identity():
    assert "@bp.post('/kiosk/connect')" in WEB
    assert "data.get('device_uuid') or data.get('device_id')" in REPO
