from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'app/mesflow/web/execution.py'

def test_legacy_identity_no_longer_verifies_token():
    text = SRC.read_text(encoding='utf-8')
    block = text[text.index('def _legacy_kiosk_identity'):text.index("@bp.post('/kiosk/bind')")]
    assert 'verify_token(' not in block
    assert 'verify_token_any(' not in block
    assert "SELECT * FROM kiosk_identities WHERE device_uuid=%s" in block
    assert "status='ACTIVE'" in block

def test_session_start_uses_relaxed_identity_resolver():
    text = SRC.read_text(encoding='utf-8')
    block = text[text.index("@bp.post('/session/group/start')"):text.index("@bp.post('/session/group/finish')")]
    assert '_legacy_kiosk_identity(body)' in block
