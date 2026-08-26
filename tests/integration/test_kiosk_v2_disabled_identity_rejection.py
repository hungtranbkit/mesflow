"""ESP kiosk physical field test (2026-08-26), §11 "401/403 test" -- real,
confirmed P1 security bug found live flashing a real ESP32-S3 test board:
POST /api/kiosk/v2/bootstrap and /api/kiosk/v2/heartbeat both wrapped
mesflow.web.execution._legacy_kiosk_identity() in a bare
`except Exception: ...` that silently swallowed the PermissionDeniedError
it correctly raises for a DISABLED/SUSPENDED/PENDING kiosk identity (or an
unregistered one when MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND is off) --
bootstrap() then reported device_status="ACTIVE" regardless (the ternary's
`not identity` branch), and heartbeat() still returned accepted=True.
Verified live: setting a real kiosk_identities row to SUSPENDED had ZERO
effect on either endpoint's response before this fix -- an admin disabling
a compromised/decommissioned kiosk via /kiosk-management did nothing to
stop it using the kiosk_v2 protocol.

Fixed by catching PermissionDeniedError specifically and returning a real
403 (matching every other caller of this identity resolver), while still
tolerating genuinely-unexpected exceptions the same permissive way as
before (this identity check must not turn an unrelated bug into a
device-bricking failure).

A second regression was caught in the SAME live test round: the fix's
first version routed through api_error_response()/jsonify(), which
escapes non-ASCII to \\uXXXX by default -- the Vietnamese rejection
message arrived on the real device as literal "u0111ang u1edf
tru1ea1ng..." instead of "đang ở trạng...", the exact class of bug this
file's own _json_response() helper exists to prevent (see its docstring)
-- this path just wasn't routed through it yet. Both tests below assert
on the real Vietnamese text, not just the status code, so a regression
back to escaped output fails loudly.
"""
from __future__ import annotations

import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _register_device(db, device_uuid: str, status: str) -> None:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO kiosk_identities(device_uuid, device_name, status) VALUES (%s, %s, %s)",
            (device_uuid, f'field-test-{device_uuid}', status))


@pytest.mark.parametrize('status', ['SUSPENDED', 'DISABLED', 'PENDING'])
def test_bootstrap_rejects_non_active_identity_with_real_403(db, status):
    device = f'V2-DISABLED-{uuid.uuid4().hex[:10]}'
    _register_device(db, device, status)
    try:
        r = requests.post(f'{BASE_URL}/api/kiosk/v2/bootstrap',
                           json={'device_id': device, 'hardware_id': device}, timeout=10)
        assert r.status_code == 403, \
            f'a {status} kiosk identity must be rejected with 403, not silently treated as ACTIVE: {r.text}'
        body = r.json()
        assert body['ok'] is False
        assert body['error'] == 'FORBIDDEN'
        # Real UTF-8, never a \uXXXX escape -- the firmware's hand-rolled
        # JSON parser (json_extract.cpp) cannot decode escape sequences.
        assert status in body['message']
        assert 'đang ở trạng thái' in body['message'], \
            f'message must be real UTF-8 Vietnamese, not \\uXXXX-escaped: {body["message"]!r}'
        assert '\\u' not in r.text, f'response body must never contain a raw \\u escape: {r.text!r}'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (device,))


def test_bootstrap_still_accepts_active_identity(db):
    device = f'V2-ACTIVE-{uuid.uuid4().hex[:10]}'
    _register_device(db, device, 'ACTIVE')
    try:
        r = requests.post(f'{BASE_URL}/api/kiosk/v2/bootstrap',
                           json={'device_id': device, 'hardware_id': device}, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body['accepted'] is True
        assert body['device_status'] == 'ACTIVE'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (device,))


def test_heartbeat_rejects_suspended_identity_with_real_403(db):
    device = f'V2-HB-DISABLED-{uuid.uuid4().hex[:10]}'
    _register_device(db, device, 'SUSPENDED')
    try:
        r = requests.post(f'{BASE_URL}/api/kiosk/v2/heartbeat',
                           json={'device_id': device, 'ui_state': 'READY'}, timeout=10)
        assert r.status_code == 403, \
            f'heartbeat from a SUSPENDED kiosk must be rejected, not accepted=True: {r.text}'
        body = r.json()
        assert body['accepted'] is not True if 'accepted' in body else True
        assert body['error'] == 'FORBIDDEN'
        assert 'đang ở trạng thái' in body['message']
        with db.cursor() as cur:
            cur.execute('SELECT last_heartbeat_at FROM kiosk_status WHERE device_uuid=%s', (device,))
            row = cur.fetchone()
        assert row is None, 'a rejected heartbeat must never write kiosk_status (would show as falsely ONLINE)'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_status WHERE device_uuid=%s', (device,))
            cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (device,))
