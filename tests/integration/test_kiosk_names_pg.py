"""Canonical kiosk names: real API auth and PostgreSQL identity invariants."""
from __future__ import annotations

import json
import os
import secrets
import uuid

import pytest
import requests
from werkzeug.security import generate_password_hash

from conftest import BASE_URL

pytestmark = pytest.mark.postgres
STRICT_URL = os.environ.get('MESFLOW_STRICT_BASE_URL', 'http://mesflow-test-api-strict:8080').rstrip('/')


@pytest.fixture()
def station(db):
    with db.cursor() as cur:
        cur.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES(%s,'Kiosk names','TEST','TEST') RETURNING id,code",
                    (f'KN-{uuid.uuid4().hex[:10]}',))
        row = cur.fetchone()
    yield row
    with db.cursor() as cur:
        cur.execute('DELETE FROM stations WHERE id=%s', (row['id'],))


@pytest.fixture()
def devices(db):
    identities = []

    def make(prefix=''):
        device = prefix + str(uuid.uuid4())
        identities.append(device)
        return device

    yield make
    with db.cursor() as cur:
        cur.execute("DELETE FROM audit_logs WHERE entity_type='kiosk_identity' AND entity_id IN (SELECT id::text FROM kiosk_identities WHERE device_uuid=ANY(%s))", (identities,))
        cur.execute('DELETE FROM kiosk_status WHERE device_uuid=ANY(%s)', (identities,))
        cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=ANY(%s)', (identities,))


def _row(db, device):
    with db.cursor() as cur:
        cur.execute('SELECT * FROM kiosk_identities WHERE device_uuid=%s', (device,))
        return cur.fetchone()


def _register(device, name='ESP default'):
    response = requests.post(f'{STRICT_URL}/api/kiosk/register', json={'device_uuid': device, 'device_name': name}, timeout=10)
    assert response.status_code == 201, response.text
    return response.json()['identity']


def _rename(api, identity_id, name):
    return api.patch(f'{BASE_URL}/api/kiosk-management/{identity_id}/name', json={'device_name': name}, timeout=10)


@pytest.fixture()
def active(db, api, station, devices):
    device = devices()
    identity = _register(device)
    response = api.post(f'{BASE_URL}/api/kiosk-identities/{identity["id"]}/approve', json={'station_id': station['id']}, timeout=10)
    assert response.status_code == 200, response.text
    return device, identity['id'], response.json()['token']


def test_rename_changes_only_name_and_is_idempotent(db, api, active):
    device, identity_id, token = active
    before = _row(db, device)
    response = _rename(api, identity_id, '  Máy 1  ')
    assert response.status_code == 200, response.text
    assert response.json() == {'ok': True, 'changed': True, 'item': {'id': identity_id, 'device_uuid': device, 'device_name': 'Máy 1'}}
    after = _row(db, device)
    assert after['device_name'] == 'Máy 1'
    assert {k: v for k, v in before.items() if k not in ('device_name', 'updated_at')} == {k: v for k, v in after.items() if k not in ('device_name', 'updated_at')}
    again = _rename(api, identity_id, 'Máy 1')
    assert again.status_code == 200 and again.json()['changed'] is False
    assert _row(db, device) == after
    with db.cursor() as cur:
        cur.execute("SELECT details_json FROM audit_logs WHERE action='KIOSK_RENAME' AND entity_type='kiosk_identity' AND entity_id=%s", (str(identity_id),))
        audit = cur.fetchall()
    assert len(audit) == 1
    details = json.loads(audit[0]['details_json']) if isinstance(audit[0]['details_json'], str) else audit[0]['details_json']
    assert details['previous_name'] == 'ESP default'
    assert details['device_name'] == 'Máy 1'
    heartbeat = requests.post(f'{STRICT_URL}/api/kiosk/heartbeat', json={'device_uuid': device}, headers={'X-Kiosk-Token': token}, timeout=10)
    assert heartbeat.status_code == 200 and heartbeat.json()['device_name'] == 'Máy 1'


@pytest.mark.parametrize('body', [None, [], {}, {'device_name': ''}, {'device_name': '   '}, {'device_name': 12}, {'device_name': 'a' * 64}, {'device_name': 'ế' * 22}, {'device_name': 'Máy\n1'}, {'device_name': 'Máy\x7f1'}, {'device_name': 'Máy 1', 'station_id': 1}, {'device_name': 'Máy 1', 'status': 'ACTIVE'}])
def test_invalid_name_or_extra_fields_do_not_touch_identity(db, api, devices, body):
    device = devices()
    identity = _register(device)
    before = _row(db, device)
    response = api.patch(f'{BASE_URL}/api/kiosk-management/{identity["id"]}/name', json=body, timeout=10)
    assert response.status_code == 400, response.text
    assert _row(db, device) == before


def test_utf8_limit_and_missing_identity(api, devices):
    identity = _register(devices())
    valid = 'ế' * 21  # 63 encoded bytes, rather than 63 Unicode characters.
    response = _rename(api, identity['id'], valid)
    assert response.status_code == 200 and response.json()['item']['device_name'] == valid
    response = _rename(api, 2147483647, 'Máy không tồn tại')
    assert response.status_code == 404, response.text


@pytest.mark.parametrize(('role', 'expected'), [('manager', 200), ('viewer', 403), (None, 401)])
def test_rename_role_boundary(db, devices, role, expected):
    device = devices()
    identity = _register(device)
    client = requests.Session()
    user_id = None
    try:
        if role:
            username = f'kn-{role}-{uuid.uuid4().hex[:8]}'
            with db.cursor() as cur:
                cur.execute('INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,%s,%s,%s,TRUE,FALSE) RETURNING id',
                            (username, 'Kiosk name test', generate_password_hash('Test@123456'), role))
                user_id = cur.fetchone()['id']
            login = client.post(f'{STRICT_URL}/api/auth/login', json={'username': username, 'password': 'Test@123456'}, timeout=10)
            assert login.status_code == 200, login.text
        response = client.patch(f'{STRICT_URL}/api/kiosk-management/{identity["id"]}/name', json={'device_name': 'Máy quản lý'}, timeout=10)
        assert response.status_code == expected, response.text
        assert _row(db, device)['device_name'] == ('Máy quản lý' if expected == 200 else 'ESP default')
    finally:
        client.close()
        if user_id:
            with db.cursor() as cur:
                cur.execute('DELETE FROM users WHERE id=%s', (user_id,))


def test_stale_device_names_cannot_revert_admin_alias(db, api, active, station):
    device, identity_id, token = active
    assert _rename(api, identity_id, 'Máy 2').status_code == 200
    _register(device, 'Old firmware default')
    assert _row(db, device)['device_name'] == 'Máy 2'
    for path in ('/api/kiosk/heartbeat', '/api/station/heartbeat'):
        heartbeat = requests.post(f'{STRICT_URL}{path}', json={'device_uuid': device, 'device_name': 'Old firmware default', 'ui_state': 'READY'}, headers={'X-Kiosk-Token': token}, timeout=10)
        assert heartbeat.status_code == 200, heartbeat.text
        assert heartbeat.json()['device_name'] == 'Máy 2'
    bind = requests.post(f'{STRICT_URL}/api/kiosk/connect', json={'device_uuid': device, 'device_name': 'Old firmware default', 'station_code': station['code']}, headers={'X-Kiosk-Token': token}, timeout=10)
    assert bind.status_code == 200 and bind.json()['device_name'] == 'Máy 2', bind.text
    assert _row(db, device)['device_name'] == 'Máy 2'


def test_pending_alias_survives_contact_approval_and_claim(db, api, station, devices):
    device, secret = devices(), secrets.token_hex(32)
    body = {'device_uuid': device, 'device_secret': secret, 'device_name': 'Factory default'}
    first = requests.post(f'{STRICT_URL}/api/kiosk/connect', json=body, timeout=10)
    assert first.status_code == 403 and first.json()['error'] == 'KIOSK_ENROLLMENT_PENDING', first.text
    identity_id = _row(db, device)['id']
    assert _rename(api, identity_id, 'Máy 3').status_code == 200
    assert _row(db, device)['status'] == 'PENDING'
    assert requests.post(f'{STRICT_URL}/api/kiosk/connect', json=body, timeout=10).status_code == 403
    approval = api.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/approve-enrollment', json={'station_id': station['id']}, timeout=10)
    assert approval.status_code == 200, approval.text
    claim = requests.post(f'{STRICT_URL}/api/kiosk/connect', json=body, timeout=10)
    assert claim.status_code == 200 and claim.json()['device_name'] == 'Máy 3', claim.text
    assert _row(db, device)['device_name'] == 'Máy 3'


def test_web_demo_heartbeat_preserves_name(db, api, devices):
    device = devices('WEB-')
    body = {'device_uuid': device, 'device_name': 'Web Kiosk Demo'}
    first = requests.post(f'{STRICT_URL}/api/kiosk-web/heartbeat', json=body, timeout=10)
    assert first.status_code == 200, first.text
    assert _rename(api, _row(db, device)['id'], 'Trình duyệt xưởng').status_code == 200
    again = requests.post(f'{STRICT_URL}/api/kiosk-web/heartbeat', json=body, timeout=10)
    assert again.status_code == 200, again.text
    assert _row(db, device)['device_name'] == 'Trình duyệt xưởng'
