"""Source contract for admin-approved hardware enrollment (0056), no DB."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = (ROOT / 'app/mesflow/web/execution.py').read_text(encoding='utf-8')
REPO = (ROOT / 'app/mesflow/db/repositories/execution.py').read_text(encoding='utf-8')
MIG = (ROOT / 'app/migrations/versions/0056_kiosk_enrollment_approval.py').read_text(encoding='utf-8')


def _block(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def test_migration_chain_and_columns():
    assert 'down_revision = "0055_mesflow_instance_identity"' in MIG
    for col in ('enroll_secret_hash', 'enroll_station_id', 'enroll_approved_until', 'enroll_approved_by'):
        assert col in MIG


def test_approve_route_is_admin_only_instance_verified_and_never_returns_token():
    b = _block(WEB, "@bp.post('/kiosk-management/<int:identity_id>/approve-enrollment')", "@bp.get('/kiosk-management/generation')")
    assert "@roles_required('admin','manager')" in b
    assert "inst.get('state')!='VERIFIED'" in b
    assert 'KIOSK_ENROLLMENT_APPROVE' in b
    assert 'kiosk_token' not in b and 'token=' not in b


def test_connect_enrollment_only_for_secret_and_pending_or_strict_unknown():
    b = _block(WEB, "def legacy_kiosk_bind():", "@bp.post('/station/heartbeat')")
    assert "status_now=='PENDING' or (not existing and not settings.allow_legacy_kiosk_autobind)" in b
    assert 'allow_legacy_unauthenticated_rebind' in b  # ACTIVE rebind rule untouched


def test_repository_single_use_bounded_and_no_overwrite():
    contact = _block(REPO, 'def enrollment_contact', 'def approve_enrollment')
    assert 'compare_digest(stored,secret_hash)' in contact
    assert 'enroll_approved_until=NULL,enroll_station_id=NULL' in contact  # single use
    assert 'ENROLL_PENDING_CAP' in contact
    approve = _block(REPO, 'def approve_enrollment', 'def bind_legacy')
    assert 'max(1,min(60,' in approve and "!='PENDING'" in approve
    assert 'token' not in approve.replace('token is never shown', '')
