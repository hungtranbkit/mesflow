from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPO=(ROOT/'app/mesflow/db/repositories/execution.py').read_text()
WEB=(ROOT/'app/mesflow/web/execution.py').read_text()

def test_repo_can_resolve_active_identity_by_token_hash():
    assert 'def verify_token_any' in REPO
    assert "WHERE token_hash=%s AND status='ACTIVE'" in REPO
    assert 'hashlib.sha256(token.encode()).hexdigest()' in REPO

def test_legacy_auth_falls_back_to_token_identity():
    assert 'return KioskRepository().verify_token_any(token)' in WEB
