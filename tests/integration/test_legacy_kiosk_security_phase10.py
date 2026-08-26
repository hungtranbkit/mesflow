"""Session Lifecycle Fix Plan Phase 10 -- legacy kiosk identity security,
against real PostgreSQL + a real running Flask instance.

Real bug this proves fixed: `_legacy_kiosk_identity()` (web/execution.py)
used to silently flip an admin-DISABLED kiosk back to ACTIVE on its own
next heartbeat, so /kiosk-management's disable action had zero real effect.
"""
from __future__ import annotations

import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def _cleanup_phase10_kiosks(db):
    # Real test-hygiene gap found live (2026-08-26) by the new `mesflow
    # audit-integrity` INACTIVE_KIOSK_WITH_LIVE_STATUS check (Reliability
    # Validation Round 2, Gate 3): this file's DISABLED-kiosk tests
    # deliberately heartbeat a device BEFORE disabling it (to prove the
    # heartbeat afterward is rejected, not that it was never live), which
    # leaves a real kiosk_status row with a fresh last_heartbeat_at behind
    # for an identity that's DISABLED -- exactly the shape the audit is
    # designed to flag, except here it's leftover test fixtures, not a
    # product bug. Every run of this file was quietly polluting whatever
    # database it ran against with 1-2 such rows forever.
    yield
    with db.cursor() as cur:
        cur.execute("DELETE FROM kiosk_status WHERE device_uuid LIKE 'PHASE10-%' OR device_uuid LIKE 'WEB-PHASE10-%'")
        cur.execute("DELETE FROM kiosk_identities WHERE device_uuid LIKE 'PHASE10-%' OR device_uuid LIKE 'WEB-PHASE10-%'")


def _register_and_approve(api, db):
    device_uuid = f'PHASE10-{uuid.uuid4()}'
    reg = requests.post(f'{BASE_URL}/api/kiosk/register', json={'device_uuid': device_uuid, 'device_name': 'Phase10 Test Kiosk'}, timeout=10)
    assert reg.status_code == 201, reg.text
    identity_id = reg.json()['identity']['id']
    with db.cursor() as cur:
        cur.execute("SELECT id FROM stations LIMIT 1")
        station = cur.fetchone()
    station_id = station['id'] if station else None
    if station_id is None:
        with db.cursor() as cur:
            cur.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES(%s,'Phase10 Station','TEST','TEST') RETURNING id", (f'P10-ST-{uuid.uuid4()}',))
            station_id = cur.fetchone()['id']
    approve = api.post(f'{BASE_URL}/api/kiosk-identities/{identity_id}/approve', json={'station_id': station_id}, timeout=10)
    assert approve.status_code == 200, approve.text
    return device_uuid, identity_id


def test_disabled_kiosk_rejects_execution_and_does_not_self_reactivate(api, db):
    device_uuid, identity_id = _register_and_approve(api, db)

    # Sanity: ACTIVE identity's heartbeat works before we disable it.
    ok = requests.post(f'{BASE_URL}/api/station/heartbeat', json={'device_uuid': device_uuid}, timeout=10)
    assert ok.status_code == 200, ok.text

    disable = api.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/status', json={'status': 'DISABLED'}, timeout=10)
    assert disable.status_code == 200, disable.text
    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE id=%s', (identity_id,))
        assert cur.fetchone()['status'] == 'DISABLED'

    # Bind/connect used to bypass _legacy_kiosk_identity entirely and the
    # repository UPSERT changed this row back to ACTIVE.
    for route in ('bind', 'connect'):
        rebound = requests.post(
            f'{BASE_URL}/api/kiosk/{route}', json={'device_uuid': device_uuid}, timeout=10)
        assert rebound.status_code == 403, rebound.text
    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE id=%s', (identity_id,))
        assert cur.fetchone()['status'] == 'DISABLED'

    # The real bug: this used to silently flip status back to ACTIVE.
    rejected = requests.post(f'{BASE_URL}/api/station/heartbeat', json={'device_uuid': device_uuid}, timeout=10)
    assert rejected.status_code == 403, rejected.text

    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE id=%s', (identity_id,))
        # THE assertion this bug used to fail: status must STILL be
        # DISABLED after the rejected request, not silently reactivated.
        assert cur.fetchone()['status'] == 'DISABLED'

    # A second, third attempt -- proves it's not a one-shot fluke.
    for _ in range(2):
        again = requests.post(f'{BASE_URL}/api/station/heartbeat', json={'device_uuid': device_uuid}, timeout=10)
        assert again.status_code == 403
    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE id=%s', (identity_id,))
        assert cur.fetchone()['status'] == 'DISABLED'


def test_pending_kiosk_rejects_execution_before_approval(db):
    device_uuid = f'PHASE10-PENDING-{uuid.uuid4()}'
    reg = requests.post(f'{BASE_URL}/api/kiosk/register', json={'device_uuid': device_uuid, 'device_name': 'Phase10 Pending Kiosk'}, timeout=10)
    assert reg.status_code == 201, reg.text
    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE device_uuid=%s', (device_uuid,))
        assert cur.fetchone()['status'] == 'PENDING'

    rejected = requests.post(f'{BASE_URL}/api/station/heartbeat', json={'device_uuid': device_uuid}, timeout=10)
    assert rejected.status_code == 403, rejected.text
    rebound = requests.post(f'{BASE_URL}/api/kiosk/bind', json={'device_uuid': device_uuid}, timeout=10)
    assert rebound.status_code == 403, rebound.text
    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE device_uuid=%s', (device_uuid,))
        assert cur.fetchone()['status'] == 'PENDING'


def test_disabled_web_kiosk_heartbeat_does_not_reactivate(db):
    device_uuid = f'WEB-PHASE10-{uuid.uuid4()}'
    created = requests.post(
        f'{BASE_URL}/api/kiosk-web/heartbeat', json={'device_uuid': device_uuid}, timeout=10)
    assert created.status_code == 200, created.text
    with db.cursor() as cur:
        cur.execute("UPDATE kiosk_identities SET status='DISABLED' WHERE device_uuid=%s", (device_uuid,))
    rejected = requests.post(
        f'{BASE_URL}/api/kiosk-web/heartbeat', json={'device_uuid': device_uuid}, timeout=10)
    assert rejected.status_code == 403, rejected.text
    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE device_uuid=%s', (device_uuid,))
        assert cur.fetchone()['status'] == 'DISABLED'


# NOTE: a "default-off rejects unknown devices" behavioral test does NOT
# live here. This shared test server explicitly sets
# MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND=1 (compose.test.yml) because the
# PRE-EXISTING integration suite (test_kiosk_offline_sync.py,
# test_production_state_integrity.py, etc.) exercises the legacy v1 kiosk
# flow against ad-hoc, never-explicitly-registered device_uuids and
# depends on auto-bind working -- same reasoning as MESFLOW_TEST_AUTO_LOGIN=1
# there. The actual "default is OFF" code-level guarantee is proven
# instead by tests/test_kiosk_security_relaxed_contract.py's
# test_legacy_identity_gates_autobind_behind_explicit_config_default_off
# (reads core/config.py's own source for the "0" default), which does not
# need a live server and is unaffected by this environment's opt-in.


def test_autobind_when_explicitly_enabled_still_creates_active_identity(db):
    """The OTHER half of Phase 10 -- when an environment deliberately opts
    in (this test server does, see the module-level NOTE above), a genuinely
    unknown device_uuid must still auto-bind as ACTIVE (unchanged behavior
    from before the fix) -- the fix gates the behavior, it does not remove
    it, per the fix plan's own "không phá ESP cũ âm thầm"."""
    device_uuid = f'PHASE10-AUTOBIND-{uuid.uuid4()}'
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM kiosk_identities WHERE device_uuid=%s', (device_uuid,))
        assert cur.fetchone()['n'] == 0

    ok = requests.post(f'{BASE_URL}/api/station/heartbeat', json={'device_uuid': device_uuid}, timeout=10)
    assert ok.status_code == 200, ok.text

    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE device_uuid=%s', (device_uuid,))
        row = cur.fetchone()
    assert row is not None and row['status'] == 'ACTIVE'


def test_reactivated_kiosk_can_execute_again(api, db):
    """The other half of the fix: an admin RE-enabling a kiosk (deliberate,
    explicit) must still work -- this isn't a one-way lockout."""
    device_uuid, identity_id = _register_and_approve(api, db)
    api.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/status', json={'status': 'DISABLED'}, timeout=10)
    assert requests.post(f'{BASE_URL}/api/station/heartbeat', json={'device_uuid': device_uuid}, timeout=10).status_code == 403

    reactivate = api.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/status', json={'status': 'ACTIVE'}, timeout=10)
    assert reactivate.status_code == 200, reactivate.text
    ok = requests.post(f'{BASE_URL}/api/station/heartbeat', json={'device_uuid': device_uuid}, timeout=10)
    assert ok.status_code == 200, ok.text
