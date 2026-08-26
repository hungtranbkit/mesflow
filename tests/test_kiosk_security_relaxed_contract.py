from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'app/mesflow/web/execution.py'

def test_legacy_identity_no_longer_verifies_token():
    text = SRC.read_text(encoding='utf-8')
    block = text[text.index('def _legacy_kiosk_identity'):text.index("@bp.post('/kiosk/bind')")]
    assert 'verify_token(' not in block
    assert 'verify_token_any(' not in block
    assert "SELECT * FROM kiosk_identities WHERE device_uuid=%s" in block
    # Fix Plan Phase 10 (security fix, superseding this test's OLD
    # assertion): the resolver used to have a real bug here -- a literal
    # `UPDATE kiosk_identities SET status='ACTIVE',...` that silently
    # re-enabled an admin-DISABLED/PENDING kiosk identity on its own next
    # request, so /kiosk-management's disable action did nothing. That SQL
    # is gone; a non-ACTIVE identity now REJECTS (PermissionDeniedError,
    # 403) instead of being silently reactivated. Kiosk tokens are still
    # not required for legacy/ESP32 execution APIs (unchanged, separate
    # decision) -- only the silent-reactivation behavior was the bug.
    assert "SET status='ACTIVE'" not in block
    assert 'PermissionDeniedError' in block
    assert "status != 'ACTIVE'" in block

def test_legacy_identity_gates_autobind_behind_explicit_config_default_off():
    """Fix Plan Phase 10: an unrecognized device_uuid used to auto-bind as
    ACTIVE unconditionally, no admin approval -- now gated behind
    MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND, defaulting OFF (core/config.py)."""
    text = SRC.read_text(encoding='utf-8')
    block = text[text.index('def _legacy_kiosk_identity'):text.index("@bp.post('/kiosk/bind')")]
    assert 'allow_legacy_kiosk_autobind' in block
    from pathlib import Path as _P
    config_text = (_P(__file__).resolve().parents[1] / 'app/mesflow/core/config.py').read_text(encoding='utf-8')
    assert 'MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND", "0"' in config_text

def test_session_start_uses_relaxed_identity_resolver():
    text = SRC.read_text(encoding='utf-8')
    block = text[text.index("@bp.post('/session/group/start')"):text.index("@bp.post('/session/group/finish')")]
    assert '_legacy_kiosk_identity(body)' in block


def test_active_kiosk_rebind_requires_current_token_by_default():
    """Codex audit follow-up: an already-ACTIVE identity used to be
    rebindable (token rotated) via /kiosk/bind|connect using nothing but its
    own public device_uuid -- no proof of possessing its current token. Now
    gated behind MESFLOW_ALLOW_LEGACY_UNAUTHENTICATED_REBIND, defaulting
    OFF, same pattern as the autobind gate above."""
    text = SRC.read_text(encoding='utf-8')
    block = text[text.index("def legacy_kiosk_bind"):text.index("@bp.post('/station/heartbeat')")]
    assert 'allow_legacy_unauthenticated_rebind' in block
    assert 'token_hash' in block and 'PermissionDeniedError' in block
    from pathlib import Path as _P
    config_text = (_P(__file__).resolve().parents[1] / 'app/mesflow/core/config.py').read_text(encoding='utf-8')
    assert 'MESFLOW_ALLOW_LEGACY_UNAUTHENTICATED_REBIND", "0"' in config_text
