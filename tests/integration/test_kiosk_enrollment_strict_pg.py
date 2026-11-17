"""Hardware kiosk enrollment against the STRICT API (legacy autobind OFF, the
production/staging default) + real PostgreSQL (migration 0056).

Root cause reproduced (2026-11-12, bench ESP 40:D0 on a fresh staging
instance): /api/kiosk/connect answered 403 for an unknown device and wrote
nothing (kiosk_identities count=0), so no admin could ever approve it; the
whole integration suite ran with MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND=1 and
never exercised that branch. These tests run against mesflow-test-api-strict.

Proves: unknown device + its own secret -> PENDING with a 6-char code;
no token before admin approval; approval is per identity, admin-only,
short-lived and single-use; a different secret cannot take over or claim;
firmware without a secret keeps the old 403; the claimed token works.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

STRICT_URL = os.environ.get('MESFLOW_STRICT_BASE_URL', 'http://mesflow-test-api-strict:8080').rstrip('/')
PREFIX = 'ENROLL56-'


@pytest.fixture(autouse=True)
def _cleanup(db):
    yield
    with db.cursor() as cur:
        cur.execute("DELETE FROM kiosk_status WHERE device_uuid LIKE %s", (PREFIX + '%',))
        cur.execute("DELETE FROM kiosk_identities WHERE device_uuid LIKE %s", (PREFIX + '%',))


@pytest.fixture()
def station(db):
    with db.cursor() as cur:
        cur.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES(%s,'Enroll56 Station','TEST','TEST') RETURNING id,code",
                    (f'E56-{uuid.uuid4().hex[:8]}',))
        return cur.fetchone()


def _device():
    return f'{PREFIX}{uuid.uuid4()}', secrets.token_hex(32)


def _connect(device, secret=None, station_code='', **extra):
    body = {'device_uuid': device, 'device_id': 'ESP-TEST', 'station_code': station_code,
            'firmware_version': '5.6.6', 'hardware_profile': 'es3c28p-n16r8-m910-gm65uart1', **extra}
    if secret is not None:
        body['device_secret'] = secret
    return requests.post(f'{STRICT_URL}/api/kiosk/connect', json=body, timeout=10)


def _row(db, device):
    with db.cursor() as cur:
        cur.execute("SELECT * FROM kiosk_identities WHERE device_uuid=%s", (device,))
        return cur.fetchone()


def _approve(api, identity_id, station_id, **extra):
    return api.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/approve-enrollment',
                    json={'station_id': station_id, **extra}, timeout=10)


def test_unknown_device_with_secret_is_recorded_pending_with_code(db, station):
    device, secret = _device()
    r = _connect(device, secret, station_code=station['code'])
    assert r.status_code == 403, r.text
    body = r.json()
    assert body['error'] == 'KIOSK_ENROLLMENT_PENDING' and 'kiosk_token' not in body
    assert body['enrollment_code'] == hashlib.sha256(secret.encode()).hexdigest()[:6].upper()
    row = _row(db, device)
    assert row and row['status'] == 'PENDING' and not row['token_hash']
    assert row['enroll_secret_hash'] == hashlib.sha256(secret.encode()).hexdigest()
    assert row['enroll_station_code'] == station['code'] and row['enroll_approved_until'] is None


def test_old_firmware_without_secret_unchanged_403_and_nothing_written(db):
    device, _ = _device()
    r = _connect(device, None)
    assert r.status_code == 403 and r.json()['error'] == 'FORBIDDEN', r.text
    assert _row(db, device) is None


def test_no_token_before_approval_and_overview_shows_code(db, api, station):
    device, secret = _device()
    first = _connect(device, secret)
    again = _connect(device, secret)
    assert again.status_code == 403 and again.json()['error'] == 'KIOSK_ENROLLMENT_PENDING'
    overview = api.get(f'{BASE_URL}/api/kiosk-management/overview', timeout=10).json()
    card = next(k for k in overview['kiosks'] if k['device_uuid'] == device)
    assert card['status'] == 'PENDING' and card['enrollment_code'] == first.json()['enrollment_code']
    assert 'enroll_secret_hash' not in card and card['enrollment_window_open'] is False


def test_admin_approval_then_device_claims_token_once(db, api, station):
    device, secret = _device()
    _connect(device, secret)
    identity_id = _row(db, device)['id']
    ok = _approve(api, identity_id, station['id'])
    assert ok.status_code == 200, ok.text
    assert 'token' not in ok.json() and 'kiosk_token' not in ok.json()  # never shown to the admin
    claim = _connect(device, secret)
    assert claim.status_code == 200, claim.text
    data = claim.json()
    assert data['enrolled'] is True and data['kiosk_token'] and data['station_code'] == station['code']
    row = _row(db, device)
    assert row['status'] == 'ACTIVE' and row['station_id'] == station['id']
    assert row['token_hash'] == hashlib.sha256(data['kiosk_token'].encode()).hexdigest()
    assert row['enroll_approved_until'] is None  # single use
    hb = requests.post(f'{STRICT_URL}/api/station/heartbeat', json={'device_uuid': device, 'ui_state': 'READY'}, timeout=10)
    assert hb.status_code == 200, hb.text
    tok = requests.post(f'{STRICT_URL}/api/kiosk/heartbeat', json={'device_uuid': device},
                        headers={'X-Kiosk-Token': data['kiosk_token']}, timeout=10)
    assert tok.status_code == 200, tok.text
    # Now ACTIVE: replaying the secret alone cannot mint another token.
    replay = _connect(device, secret)
    assert replay.status_code == 403, replay.text
    assert _row(db, device)['token_hash'] == row['token_hash']


def test_other_secret_cannot_take_over_or_claim(db, api, station):
    device, secret = _device()
    _connect(device, secret)
    stolen = _connect(device, secrets.token_hex(32))
    assert stolen.status_code == 403 and stolen.json()['error'] == 'FORBIDDEN', stolen.text
    assert _row(db, device)['enroll_secret_hash'] == hashlib.sha256(secret.encode()).hexdigest()
    assert _approve(api, _row(db, device)['id'], station['id']).status_code == 200
    assert _connect(device, secrets.token_hex(32)).status_code == 403
    assert _row(db, device)['status'] == 'PENDING'
    assert _connect(device, secret).status_code == 200  # the real device still enrolls


def test_expired_approval_does_not_issue_token(db, api, station):
    device, secret = _device()
    _connect(device, secret)
    identity_id = _row(db, device)['id']
    assert _approve(api, identity_id, station['id'], ttl_minutes=1).status_code == 200
    with db.cursor() as cur:
        cur.execute("UPDATE kiosk_identities SET enroll_approved_until=CURRENT_TIMESTAMP-INTERVAL '1 second' WHERE id=%s", (identity_id,))
    r = _connect(device, secret)
    assert r.status_code == 403 and r.json()['error'] == 'KIOSK_ENROLLMENT_PENDING'
    assert _row(db, device)['status'] == 'PENDING'


def test_approval_is_single_device_and_admin_only(db, api, station):
    a, sa = _device()
    b, sb = _device()
    _connect(a, sa)
    _connect(b, sb)
    anon = requests.post(f'{STRICT_URL}/api/kiosk-management/{_row(db, a)["id"]}/approve-enrollment',
                         json={'station_id': station['id']}, timeout=10)
    assert anon.status_code in (401, 403), anon.text
    assert _approve(api, _row(db, a)['id'], station['id']).status_code == 200
    assert _connect(b, sb).status_code == 403 and _row(db, b)['status'] == 'PENDING'
    assert _connect(a, sa).status_code == 200
    again = _approve(api, _row(db, a)['id'], station['id'])  # ACTIVE now
    assert again.status_code == 409, again.text
    assert _approve(api, _row(db, b)['id'], 999999999).status_code == 404


def test_ttl_is_bounded(db, api, station):
    device, secret = _device()
    _connect(device, secret)
    r = _approve(api, _row(db, device)['id'], station['id'], ttl_minutes=100000)
    assert r.status_code == 200
    with db.cursor() as cur:
        cur.execute("SELECT enroll_approved_until<=CURRENT_TIMESTAMP+INTERVAL '61 minutes' ok FROM kiosk_identities WHERE device_uuid=%s", (device,))
        assert cur.fetchone()['ok'] is True
