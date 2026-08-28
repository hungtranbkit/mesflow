"""P0 fix (2026-08-28): kiosk_v2 device-identity/token authorization on
POST /api/kiosk/v2/events and GET /api/kiosk/v2/state.

Before this fix, ZERO tests exercised device authorization on these two
routes (confirmed by grep -- the only existing /events coverage,
test_kiosk_v2_shared_terminal.py, drove real business flows with an
UNREGISTERED device_id, since nothing rejected that). This file is the
first coverage proving:
  - an unknown/PENDING/SUSPENDED/DISABLED device cannot reach ANY business
    effect through /events or /state;
  - an ACTIVE device with no token, the wrong token, or another device's
    (real, valid) token is rejected the same way;
  - only ACTIVE + the correct token for THAT device continues to work;
  - revocation (admin flips an already-authenticated device to SUSPENDED/
    DISABLED) takes effect immediately, including against a cached
    idempotent replay of an event_id that succeeded before revocation;
  - none of the rejected paths ever create a kiosk_v2_projection row,
    a kiosk_v2_events row, or a work_sessions row.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

_STATUSES_THAT_MUST_REJECT = ('PENDING', 'SUSPENDED', 'DISABLED')


def _device_id(suffix: str) -> str:
    return f'V2-AUTHZ-{suffix}'


def _register(db, suffix: str, status: str, token: str | None = None):
    # kiosk_identities.token_hash is NOT NULL -- a non-ACTIVE identity still
    # needs *some* placeholder hash even when the test never presents that
    # token (the whole point of the PENDING/SUSPENDED/DISABLED tests is that
    # the request is rejected on status alone, before any hash comparison).
    token_hash = hashlib.sha256((token or f'unused-{suffix}').encode()).hexdigest()
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO kiosk_identities(device_uuid,device_name,status,token_hash,last_seen_at)
               VALUES(%s,'Docker Test Authz Kiosk',%s,%s,CURRENT_TIMESTAMP)""",
            (_device_id(suffix), status, token_hash))


def _cleanup(db, suffix: str):
    device = _device_id(suffix)
    with db.cursor() as cur:
        cur.execute('DELETE FROM kiosk_v2_events WHERE device_id=%s', (device,))
        cur.execute('DELETE FROM kiosk_v2_projection WHERE device_id=%s', (device,))
        cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (device,))


def _events_body(device_id: str, event_type='SCAN', payload=None, event_id=None):
    return {
        'protocol_version': 1,
        'device': {'device_id': device_id, 'hardware_id': device_id},
        'event': {'event_id': event_id or uuid.uuid4().hex, 'type': event_type, 'device_seq': 1},
        'context': {},
        'payload': payload or {'raw': 'WF|EMP|NONEXISTENT'},
    }


def _post_events(device_id, token=None, **kwargs):
    headers = {'X-Kiosk-Token': token} if token else {}
    return requests.post(f'{BASE_URL}/api/kiosk/v2/events', json=_events_body(device_id, **kwargs),
                          headers=headers, timeout=10)


def _get_state(device_id, token=None):
    headers = {'X-Kiosk-Token': token} if token else {}
    return requests.get(f'{BASE_URL}/api/kiosk/v2/state', params={'device_id': device_id},
                         headers=headers, timeout=10)


def _projection_exists(db, suffix: str) -> bool:
    with db.cursor() as cur:
        cur.execute('SELECT 1 FROM kiosk_v2_projection WHERE device_id=%s', (_device_id(suffix),))
        return cur.fetchone() is not None


def _event_row_exists(db, suffix: str) -> bool:
    with db.cursor() as cur:
        cur.execute('SELECT 1 FROM kiosk_v2_events WHERE device_id=%s', (_device_id(suffix),))
        return cur.fetchone() is not None


# --- §8: required security behavior matrix ---------------------------------

def test_unknown_device_rejected_and_creates_nothing(db):
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-unknown'
    try:
        r_events = _post_events(_device_id(suffix), token='irrelevant')
        assert r_events.status_code == 403, r_events.text
        assert r_events.json()['error']['code'] == 'DEVICE_NOT_ALLOWED'

        r_state = _get_state(_device_id(suffix), token='irrelevant')
        assert r_state.status_code == 403, r_state.text

        assert _projection_exists(db, suffix) is False
        assert _event_row_exists(db, suffix) is False
    finally:
        _cleanup(db, suffix)


@pytest.mark.parametrize('status', _STATUSES_THAT_MUST_REJECT)
def test_non_active_status_rejected_regardless_of_token(db, status):
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + f'-{status.lower()}'
    token = f'TOKEN-{suffix}'
    _register(db, suffix, status, token=token)
    try:
        for presented_token in (None, token, 'wrong-token'):
            r = _post_events(_device_id(suffix), token=presented_token)
            assert r.status_code == 403, (status, presented_token, r.text)
            assert r.json()['error']['code'] == 'DEVICE_NOT_ALLOWED'

            r_state = _get_state(_device_id(suffix), token=presented_token)
            assert r_state.status_code == 403, (status, presented_token, r_state.text)

        assert _projection_exists(db, suffix) is False
        assert _event_row_exists(db, suffix) is False
    finally:
        _cleanup(db, suffix)


def test_active_device_no_token_rejected_401(db):
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-notoken'
    token = f'TOKEN-{suffix}'
    _register(db, suffix, 'ACTIVE', token=token)
    try:
        r = _post_events(_device_id(suffix), token=None)
        assert r.status_code == 401, r.text
        assert r.json()['error']['code'] == 'AUTH_REQUIRED'

        r_state = _get_state(_device_id(suffix), token=None)
        assert r_state.status_code == 401, r_state.text

        assert _projection_exists(db, suffix) is False
    finally:
        _cleanup(db, suffix)


def test_active_device_wrong_token_rejected_403(db):
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-wrongtoken'
    token = f'TOKEN-{suffix}'
    _register(db, suffix, 'ACTIVE', token=token)
    try:
        r = _post_events(_device_id(suffix), token='completely-wrong-token')
        assert r.status_code == 403, r.text
        assert r.json()['error']['code'] == 'DEVICE_NOT_ALLOWED'

        r_state = _get_state(_device_id(suffix), token='completely-wrong-token')
        assert r_state.status_code == 403, r_state.text

        assert _projection_exists(db, suffix) is False
    finally:
        _cleanup(db, suffix)


def test_active_device_another_devices_real_token_rejected_403(db):
    """A real, valid, ACTIVE token -- just not for the device_id being
    claimed. Confirms verify_token-style binding (device_uuid+token
    together), not just "is this token valid for anyone"."""
    suffix_a = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-tokA'
    suffix_b = suffix_a + '-b'
    token_a = f'TOKEN-{suffix_a}'
    token_b = f'TOKEN-{suffix_b}'
    _register(db, suffix_a, 'ACTIVE', token=token_a)
    _register(db, suffix_b, 'ACTIVE', token=token_b)
    try:
        # Device A claimed, but presenting B's real, valid, ACTIVE token.
        r = _post_events(_device_id(suffix_a), token=token_b)
        assert r.status_code == 403, r.text
        assert r.json()['error']['code'] == 'DEVICE_NOT_ALLOWED'
        assert _projection_exists(db, suffix_a) is False

        # Sanity: B's own token against B's own claimed id still works.
        r_b = _post_events(_device_id(suffix_b), token=token_b)
        assert r_b.status_code == 200, r_b.text
        assert r_b.json()['accepted'] is False  # business-level: bad QR payload, not an auth rejection
        assert 'error' in r_b.json() and r_b.json()['error']['code'] != 'DEVICE_NOT_ALLOWED'
    finally:
        _cleanup(db, suffix_a)
        _cleanup(db, suffix_b)


def test_active_device_correct_token_protocol_continues_normally(db):
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-correct'
    token = f'TOKEN-{suffix}'
    _register(db, suffix, 'ACTIVE', token=token)
    try:
        r = _post_events(_device_id(suffix), token=token)
        assert r.status_code == 200, r.text
        body = r.json()
        # Authorized through to real business logic -- STATE_INVALID_
        # TRANSITION / EMPLOYEE_NOT_FOUND, not an auth rejection.
        assert body['accepted'] is False
        assert body['error']['code'] != 'DEVICE_NOT_ALLOWED'
        assert body['error']['code'] != 'AUTH_REQUIRED'

        r_state = _get_state(_device_id(suffix), token=token)
        assert r_state.status_code == 200, r_state.text
        assert _projection_exists(db, suffix) is True  # only NOW, post-auth
    finally:
        _cleanup(db, suffix)


# --- §9: business mutation protection ---------------------------------------

def test_unauthorized_caller_cannot_start_finish_or_submit_quantity(db, seeded_factory):
    """Directly proves the P0: an unauthenticated/unauthorized caller who
    knows a real employee's/operation's QR cannot drive a real START,
    FINISH, or GOOD/NG/REWORK quantity submission through kiosk v2."""
    g = seeded_factory
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-mutation'
    device = _device_id(suffix)
    with db.cursor() as cur:
        cur.execute('SELECT qr FROM employees WHERE id=%s', (g['employee_id'],))
        employee_qr = cur.fetchone()['qr']
        cur.execute('SELECT qr FROM operations WHERE id=%s', (g['operation_id'],))
        operation_qr = cur.fetchone()['qr']
        cur.execute('SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s', (g['employee_id'],))
        sessions_before = cur.fetchone()['n']
        cur.execute('SELECT done_qty,defect_qty FROM operations WHERE id=%s', (g['operation_id'],))
        op_before = dict(cur.fetchone())

    try:
        # No registration at all for `device` -- exactly the P0 scenario:
        # an arbitrary caller who merely knows real QR content.
        r1 = _post_events(device, token=None, payload={'raw': employee_qr})
        assert r1.status_code in (401, 403), r1.text
        r2 = _post_events(device, token='guessed-token', payload={'raw': operation_qr})
        assert r2.status_code in (401, 403), r2.text
        r3 = _post_events(device, token='guessed-token', event_type='QUANTITY_SUBMITTED',
                           payload={'quantity_good': 10, 'quantity_defect': 0, 'quantity_rework': 0})
        assert r3.status_code in (401, 403), r3.text

        with db.cursor() as cur:
            cur.execute('SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s', (g['employee_id'],))
            assert cur.fetchone()['n'] == sessions_before, 'a work_sessions row was created by an unauthorized caller'
            cur.execute('SELECT done_qty,defect_qty FROM operations WHERE id=%s', (g['operation_id'],))
            assert dict(cur.fetchone()) == op_before, 'operation progress changed from an unauthorized caller'
            cur.execute('SELECT 1 FROM kiosk_v2_events WHERE device_id=%s', (device,))
            assert cur.fetchone() is None, 'kiosk_v2_events must stay empty for a rejected device'
    finally:
        _cleanup(db, suffix)


# --- §10/§11: revocation + idempotency-after-revocation ---------------------

def test_revoked_device_rejected_immediately_and_replay_does_not_return_cached_success(db, api):
    """1. register ACTIVE, 2/3. authenticate + succeed once, 4. admin
    revokes via the REAL /kiosk-management/<id>/status API, 5. same
    device/token retries -- including replaying the EXACT event_id that
    succeeded before revocation. Neither call may return a business
    effect or the old cached accepted=true."""
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-revoke'
    token = f'TOKEN-{suffix}'
    device = _device_id(suffix)
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO kiosk_identities(device_uuid,device_name,status,token_hash,last_seen_at)
               VALUES(%s,'Docker Test Revoke Kiosk','ACTIVE',%s,CURRENT_TIMESTAMP) RETURNING id""",
            (device, hashlib.sha256(token.encode()).hexdigest()))
        identity_id = cur.fetchone()['id']

    try:
        event_id = uuid.uuid4().hex
        first = _post_events(device, token=token, event_id=event_id, payload={'raw': 'WF|EMP|NONEXISTENT'})
        assert first.status_code == 200, first.text
        assert first.json()['accepted'] is False  # business rejection (bad QR), but AUTHORIZED -- proves the setup is valid
        assert first.json()['error']['code'] == 'EMPLOYEE_NOT_FOUND'

        revoke = api.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/status',
                           json={'status': 'DISABLED'}, timeout=10)
        assert revoke.status_code == 200, revoke.text

        # §11: replaying the SAME event_id that succeeded (was cached in
        # kiosk_v2_events) before revocation must NOT return that cached
        # response -- authorization must be re-checked and must now fail.
        replay = _post_events(device, token=token, event_id=event_id, payload={'raw': 'WF|EMP|NONEXISTENT'})
        assert replay.status_code == 403, replay.text
        assert replay.json()['error']['code'] == 'DEVICE_NOT_ALLOWED'

        # A brand-new event_id from the same now-revoked device/token also fails.
        fresh = _post_events(device, token=token, payload={'raw': 'WF|EMP|NONEXISTENT'})
        assert fresh.status_code == 403, fresh.text

        state = _get_state(device, token=token)
        assert state.status_code == 403, state.text
    finally:
        _cleanup(db, suffix)


# --- §12: projection creation rule -------------------------------------------

def test_rejected_state_request_never_creates_projection_row(db):
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-noproj'
    try:
        r = _get_state(_device_id(suffix), token=None)
        assert r.status_code in (401, 403), r.text
        assert _projection_exists(db, suffix) is False
    finally:
        _cleanup(db, suffix)


# --- §14: heartbeat unaffected by this change (already fixed 2026-08-26,
# regression-guarded here so a future change can't quietly re-break it) -----

def test_heartbeat_still_rejects_disabled_device_and_does_not_write_status(db):
    from mesflow.domain.errors import PermissionDeniedError  # noqa: F401 -- documents the exact exception this route already handles
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f') + '-hb'
    device = _device_id(suffix)
    _register(db, suffix, 'DISABLED')
    try:
        r = requests.post(f'{BASE_URL}/api/kiosk/v2/heartbeat', json={'device_id': device}, timeout=10)
        assert r.status_code == 403, r.text
        with db.cursor() as cur:
            cur.execute('SELECT 1 FROM kiosk_status WHERE device_uuid=%s', (device,))
            assert cur.fetchone() is None, 'a DISABLED device must never get a kiosk_status row written'
    finally:
        _cleanup(db, suffix)
