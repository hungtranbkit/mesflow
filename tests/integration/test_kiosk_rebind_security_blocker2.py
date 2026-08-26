"""Codex audit Blocker 2 -- an already-ACTIVE legacy kiosk identity must
not be rebindable/rotatable using nothing but its own public device_uuid.
/api/kiosk/bind|connect now requires the identity's CURRENT token (proven
by X-Kiosk-Token / body `kiosk_token`) before bind_legacy() is allowed to
issue a new one, unless MESFLOW_ALLOW_LEGACY_UNAUTHENTICATED_REBIND is
explicitly enabled (not the case for this test server -- see
test_kiosk_security_relaxed_contract.py for the default-OFF code guarantee,
and test_legacy_kiosk_security_phase10.py for DISABLED/PENDING coverage).
"""
from __future__ import annotations

import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _bind_new_device(device_uuid: str) -> str:
    """First-contact bind on an unknown device (this test server has
    MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND=1) -- returns the real, valid
    kiosk_token bind_legacy() issued for it."""
    r = requests.post(f'{BASE_URL}/api/kiosk/bind', json={'device_uuid': device_uuid}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()['kiosk_token']


def test_active_with_correct_token_is_allowed_and_rotates(db):
    device = f'REBIND-OK-{uuid.uuid4()}'
    token = _bind_new_device(device)

    r = requests.post(f'{BASE_URL}/api/kiosk/bind', json={'device_uuid': device},
                       headers={'X-Kiosk-Token': token}, timeout=10)
    assert r.status_code == 200, r.text
    new_token = r.json()['kiosk_token']
    assert new_token and new_token != token  # bind_legacy() always rotates once authenticated

    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE device_uuid=%s', (device,))
        assert cur.fetchone()['status'] == 'ACTIVE'


def test_active_with_no_token_is_denied(db):
    device = f'REBIND-NOTOKEN-{uuid.uuid4()}'
    token = _bind_new_device(device)

    r = requests.post(f'{BASE_URL}/api/kiosk/bind', json={'device_uuid': device}, timeout=10)
    assert r.status_code == 403, r.text

    # The original token must still work -- the failed attempt did not
    # silently rotate/clear it.
    still_ok = requests.post(f'{BASE_URL}/api/kiosk/heartbeat', json={'device_uuid': device},
                              headers={'X-Kiosk-Token': token}, timeout=10)
    assert still_ok.status_code == 200, still_ok.text


def test_active_with_wrong_token_is_denied(db):
    device = f'REBIND-WRONGTOKEN-{uuid.uuid4()}'
    _bind_new_device(device)

    r = requests.post(f'{BASE_URL}/api/kiosk/bind', json={'device_uuid': device},
                       headers={'X-Kiosk-Token': 'totally-not-the-real-token'}, timeout=10)
    assert r.status_code == 403, r.text


def test_spoofed_device_uuid_without_its_token_is_denied(db):
    """An attacker who only knows/guesses a REAL device_uuid belonging to
    someone else's kiosk (device_uuid is sent in the clear on every request,
    not a secret) must not be able to hijack it -- this is the actual
    vulnerability Codex found."""
    victim_device = f'REBIND-VICTIM-{uuid.uuid4()}'
    victim_token = _bind_new_device(victim_device)

    attacker = requests.post(f'{BASE_URL}/api/kiosk/bind', json={'device_uuid': victim_device}, timeout=10)
    assert attacker.status_code == 403, attacker.text

    # Victim's original token is untouched and still authenticates.
    still_ok = requests.post(f'{BASE_URL}/api/kiosk/heartbeat', json={'device_uuid': victim_device},
                              headers={'X-Kiosk-Token': victim_token}, timeout=10)
    assert still_ok.status_code == 200, still_ok.text


def test_unknown_device_binds_when_autobind_on(db):
    """This test server explicitly opts into MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND=1
    (compose.test.yml) -- a genuinely never-seen device must still bind
    (unrelated to the token-rebind gate, which only applies to EXISTING
    ACTIVE identities)."""
    device = f'REBIND-NEW-{uuid.uuid4()}'
    r = requests.post(f'{BASE_URL}/api/kiosk/connect', json={'device_uuid': device}, timeout=10)
    assert r.status_code == 200, r.text
    with db.cursor() as cur:
        cur.execute('SELECT status FROM kiosk_identities WHERE device_uuid=%s', (device,))
        assert cur.fetchone()['status'] == 'ACTIVE'


# NOTE: "unknown device with autobind OFF is denied" and "compatibility
# mode ON allows unauthenticated rebind" are NOT live-server tests here --
# this shared test server bakes MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND=1 in at
# container start (same reasoning documented in
# test_legacy_kiosk_security_phase10.py), so neither OFF state is reachable
# through this fixture. Both are proven at the code level instead:
# - autobind OFF -> 403: test_kiosk_security_relaxed_contract.py::
#   test_legacy_identity_gates_autobind_behind_explicit_config_default_off
# - unauthenticated rebind OFF by default, and the ON branch existing and
#   logging a warning: test_kiosk_security_relaxed_contract.py::
#   test_active_kiosk_rebind_requires_current_token_by_default
