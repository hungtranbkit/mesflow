"""Stable hardware display numbers, exercised through real PostgreSQL and APIs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import secrets
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import requests
from sqlalchemy import create_engine, text

from conftest import BASE_URL

pytestmark = pytest.mark.postgres
STRICT_URL = os.environ.get('MESFLOW_STRICT_BASE_URL', 'http://mesflow-test-api-strict:8080').rstrip('/')
SEQUENCE = 'kiosk_display_number_seq'


@pytest.fixture()
def number_devices(db):
    devices = []

    def make(prefix=''):
        value = prefix + str(uuid.uuid4())
        devices.append(value)
        return value

    yield make
    with db.cursor() as cur:
        cur.execute("DELETE FROM audit_logs WHERE entity_type='kiosk_identity' AND entity_id IN (SELECT id::text FROM kiosk_identities WHERE device_uuid=ANY(%s))", (devices,))
        cur.execute('DELETE FROM kiosk_status WHERE device_uuid=ANY(%s)', (devices,))
        cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=ANY(%s)', (devices,))


@pytest.fixture()
def number_station(db):
    with db.cursor() as cur:
        cur.execute("INSERT INTO stations(code,name) VALUES(%s,'Display number test') RETURNING id,code", ('DN-' + uuid.uuid4().hex[:10],))
        station = cur.fetchone()
    yield station
    with db.cursor() as cur:
        cur.execute('DELETE FROM stations WHERE id=%s', (station['id'],))


def _row(db, device):
    with db.cursor() as cur:
        cur.execute('SELECT * FROM kiosk_identities WHERE device_uuid=%s', (device,))
        return cur.fetchone()


def _sequence(db):
    with db.cursor() as cur:
        cur.execute(f'SELECT last_value,is_called FROM {SEQUENCE}')
        return dict(cur.fetchone())


def _register(device, **extra):
    response = requests.post(f'{STRICT_URL}/api/kiosk/register', json={'device_uuid': device, 'device_name': 'Number test', **extra}, timeout=10)
    assert response.status_code == 201, response.text
    return response.json()['identity']


def _approve(api, identity_id, station_id):
    response = api.post(f'{BASE_URL}/api/kiosk-identities/{identity_id}/approve', json={'station_id': station_id}, timeout=10)
    assert response.status_code == 200, response.text
    return response.json()


def test_unapproved_registration_has_nullable_number(db, number_devices):
    identity = _register(number_devices(), display_number=123)
    assert 'display_number' in identity
    assert identity['display_number'] is None
    before = _sequence(db)
    for _ in range(3):
        assert _register(identity['device_uuid'], display_number=456)['display_number'] is None
    assert _sequence(db) == before


def test_approval_and_repeat_contacts_keep_number_and_credentials(db, api, number_devices, number_station):
    device = number_devices()
    identity = _register(device)
    result = _approve(api, identity['id'], number_station['id'])
    number, token = result['identity']['display_number'], result['token']
    assert type(number) is int and 1 <= number <= 2147483647
    before = _row(db, device)
    allocated = _sequence(db)
    for _ in range(3):
        assert _register(device, display_number=number + 1000)['display_number'] == number
        for path in ('/api/kiosk/heartbeat', '/api/station/heartbeat'):
            response = requests.post(f'{STRICT_URL}{path}', headers={'X-Kiosk-Token': token}, json={'device_uuid': device, 'display_number': number + 1000}, timeout=10)
            assert response.status_code == 200, response.text
            assert response.json()['display_number'] == number
    after = _row(db, device)
    for key in ('id', 'device_uuid', 'device_name', 'station_id', 'status', 'token_hash', 'display_number'):
        assert after[key] == before[key]
    assert _sequence(db) == allocated
    response = api.get(f'{BASE_URL}/api/kiosk-management/overview', timeout=10)
    assert response.status_code == 200
    assert next(x for x in response.json()['kiosks'] if x['device_uuid'] == device)['display_number'] == number


def test_authenticated_rebind_preserves_number(db, api, number_devices, number_station):
    device = number_devices('LEGACY-')
    identity = _register(device)
    result = _approve(api, identity['id'], number_station['id'])
    number = result['identity']['display_number']
    allocated = _sequence(db)
    response = requests.post(f'{STRICT_URL}/api/kiosk/connect', headers={'X-Kiosk-Token': result['token']}, json={'device_uuid': device, 'station_code': number_station['code'], 'display_number': 999999}, timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()['display_number'] == number
    assert _sequence(db) == allocated


def test_enrollment_code_is_separate_and_only_approval_allocates(db, api, number_devices, number_station):
    device, secret = number_devices(), secrets.token_hex(32)
    body = {'device_uuid': device, 'device_secret': secret, 'device_name': 'Pending number', 'display_number': 5000}
    before = _sequence(db)
    for _ in range(3):
        response = requests.post(f'{STRICT_URL}/api/kiosk/connect', json=body, timeout=10)
        assert response.status_code == 403, response.text
        pending = response.json()
        assert pending['error'] == 'KIOSK_ENROLLMENT_PENDING'
        assert len(pending['enrollment_code']) == 6
        assert pending['display_number'] is None
    assert _sequence(db) == before
    identity_id = _row(db, device)['id']
    approval = api.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/approve-enrollment', json={'station_id': number_station['id']}, timeout=10)
    assert approval.status_code == 200, approval.text
    number = approval.json()['display_number']
    assert type(number) is int and number > 0
    assert approval.json()['enrollment_code'] == pending['enrollment_code']
    allocated = _sequence(db)
    again = api.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/approve-enrollment', json={'station_id': number_station['id']}, timeout=10)
    assert again.status_code == 200 and again.json()['display_number'] == number
    claim = requests.post(f'{STRICT_URL}/api/kiosk/connect', json=body, timeout=10)
    assert claim.status_code == 200 and claim.json()['display_number'] == number, claim.text
    assert _sequence(db) == allocated


@pytest.mark.parametrize('prefix', ['WEB-', 'web-'])
def test_web_identities_never_consume_numbers(db, api, number_devices, number_station, prefix):
    device = number_devices(prefix)
    before = _sequence(db)
    for _ in range(3):
        response = requests.post(f'{STRICT_URL}/api/kiosk-web/heartbeat', json={'device_uuid': device, 'display_number': 7}, timeout=10)
        assert response.status_code == 200, response.text
    identity = _row(db, device)
    assert identity['display_number'] is None
    approved = _approve(api, identity['id'], number_station['id'])
    assert approved['identity']['display_number'] is None
    assert _sequence(db) == before


def test_unauthorized_requests_cannot_allocate_or_overwrite(db, number_devices, number_station):
    device = number_devices()
    identity = _register(device)
    before = _sequence(db)
    response = requests.post(f'{STRICT_URL}/api/kiosk-identities/{identity["id"]}/approve', json={'station_id': number_station['id'], 'display_number': 99}, timeout=10)
    assert response.status_code == 401, response.text
    for path in ('/api/kiosk/heartbeat', '/api/station/heartbeat'):
        response = requests.post(f'{STRICT_URL}{path}', json={'device_uuid': device, 'display_number': 99}, headers={'X-Kiosk-Token': 'invalid-token'}, timeout=10)
        assert response.status_code in (400, 401, 403), response.text
    assert _row(db, device)['display_number'] is None
    assert _sequence(db) == before


def test_rename_disable_reenable_keep_identity_number(db, api, number_devices, number_station):
    device = number_devices()
    identity = _register(device)
    _approve(api, identity['id'], number_station['id'])
    before = _row(db, device)
    allocated = _sequence(db)
    rename = api.patch(f'{BASE_URL}/api/kiosk-management/{identity["id"]}/name', json={'device_name': 'Máy đổi tên'}, timeout=10)
    assert rename.status_code == 200
    rejected = api.patch(f'{BASE_URL}/api/kiosk-management/{identity["id"]}/name', json={'device_name': 'Không ghi', 'display_number': 456}, timeout=10)
    assert rejected.status_code == 400
    for state in ('DISABLED', 'ACTIVE'):
        response = api.post(f'{BASE_URL}/api/kiosk-management/{identity["id"]}/status', json={'status': state}, timeout=10)
        assert response.status_code == 200, response.text
        assert response.json()['item']['display_number'] == before['display_number']
    after = _row(db, device)
    for key in ('id', 'device_uuid', 'station_id', 'token_hash', 'display_number'):
        assert after[key] == before[key]
    assert _sequence(db) == allocated


@pytest.mark.parametrize('path', ['/api/kiosk/heartbeat', '/api/station/heartbeat'])
def test_first_authenticated_heartbeat_returns_newly_allocated_number(db, api, number_devices, number_station, path):
    device = number_devices()
    identity = _register(device)
    approved = _approve(api, identity['id'], number_station['id'])
    # Models an ACTIVE identity inserted by the old app during staged rollout.
    with db.cursor() as cur:
        cur.execute('UPDATE kiosk_identities SET display_number=NULL WHERE id=%s', (identity['id'],))
    response = requests.post(f'{STRICT_URL}{path}', headers={'X-Kiosk-Token': approved['token']}, json={'device_uuid': device}, timeout=10)
    assert response.status_code == 200, response.text
    assert type(response.json()['display_number']) is int
    assert response.json()['display_number'] == _row(db, device)['display_number']


def test_concurrent_activation_allocates_once_per_identity(db, api, number_devices):
    identity = _register(number_devices())
    before = _sequence(db)
    cookies = api.cookies.get_dict()

    def activate(identity_id):
        response = requests.post(f'{BASE_URL}/api/kiosk-management/{identity_id}/status', cookies=cookies, json={'status': 'ACTIVE'}, timeout=15)
        assert response.status_code == 200, response.text
        return response.json()['item']['display_number']

    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = list(pool.map(activate, [identity['id']] * 8))
    assert len(set(numbers)) == 1 and type(numbers[0]) is int
    expected = before['last_value'] + 1 if before['is_called'] else before['last_value']
    assert numbers[0] == expected
    assert _sequence(db) == {'last_value': expected, 'is_called': True}
    identities = [_register(number_devices()) for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        more = list(pool.map(activate, [x['id'] for x in identities]))
    assert len(set(more)) == 6
    assert sorted(more) == list(range(expected + 1, expected + 7))


def test_deleted_identity_number_is_not_reused(db, api, number_devices, number_station):
    device = number_devices()
    identity = _register(device)
    first = _approve(api, identity['id'], number_station['id'])['identity']['display_number']
    with db.cursor() as cur:
        cur.execute("DELETE FROM audit_logs WHERE entity_type='kiosk_identity' AND entity_id=%s", (str(identity['id']),))
        cur.execute('DELETE FROM kiosk_identities WHERE id=%s', (identity['id'],))
    replacement = _register(number_devices())
    second = _approve(api, replacement['id'], number_station['id'])['identity']['display_number']
    assert second > first


@pytest.mark.parametrize('with_inventory', [False, True])
def test_migration_backfills_preserves_data_and_has_bounded_unique_sequence(with_inventory):
    migration = Path(__file__).resolve().parents[2] / 'app/migrations/versions/0057_kiosk_display_number.py'
    assert migration.is_file(), 'display-number migration must exist'
    spec = importlib.util.spec_from_file_location('display_number_migration', migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(os.environ['DATABASE_URL'].replace('postgresql://', 'postgresql+psycopg://', 1))
    schema = 'number_test_' + uuid.uuid4().hex
    try:
        with engine.connect() as conn, conn.begin():
            conn.exec_driver_sql(f'CREATE SCHEMA {schema}')
            conn.exec_driver_sql(f'SET LOCAL search_path TO {schema}')
            conn.exec_driver_sql("CREATE TABLE kiosk_identities(id bigint PRIMARY KEY,device_uuid text UNIQUE NOT NULL,device_name text NOT NULL,status text NOT NULL,token_hash text NOT NULL,station_id bigint,created_at timestamptz NOT NULL)")
            if with_inventory:
                conn.exec_driver_sql("""INSERT INTO kiosk_identities VALUES
                    (30,'legacy-third','Earlier alphabet','PENDING','hash-third',NULL,'2026-01-02'),
                    (10,'legacy-second','Zulu','DISABLED','hash-second',12,'2026-01-02'),
                    (20,'legacy-first','First','ACTIVE','hash-first',11,'2026-01-01'),
                    (5,'WEB-browser','Browser','ACTIVE','hash-web',NULL,'2025-01-01'),
                    (6,'web-lower','Browser lower','ACTIVE','hash-web-lower',NULL,'2025-01-01')""")
            before = [dict(x) for x in conn.execute(text('SELECT * FROM kiosk_identities ORDER BY id')).mappings()]
            module.op = Operations(MigrationContext.configure(conn))
            module.upgrade()
            after = [dict(x) for x in conn.execute(text('SELECT * FROM kiosk_identities ORDER BY id')).mappings()]
            assert [{k: v for k, v in row.items() if k != 'display_number'} for row in after] == before
            if with_inventory:
                assert {x['id']: x['display_number'] for x in after} == {5: None, 6: None, 10: 2, 20: 1, 30: 3}
            default = conn.execute(text("SELECT column_default FROM information_schema.columns WHERE table_schema=:schema AND table_name='kiosk_identities' AND column_name='display_number'"), {'schema': schema}).scalar_one()
            assert default is None
            sequence = conn.execute(text("SELECT seqtypid::regtype::text AS type,seqmin,seqmax,seqcycle FROM pg_sequence WHERE seqrelid='kiosk_display_number_seq'::regclass")).mappings().one()
            assert dict(sequence) == {'type': 'integer', 'seqmin': 1, 'seqmax': 2147483647, 'seqcycle': False}
            assert conn.execute(text("SELECT nextval('kiosk_display_number_seq')")).scalar_one() == (4 if with_inventory else 1)
            for invalid in (0, -1):
                with pytest.raises(Exception) as exc, conn.begin_nested():
                    conn.exec_driver_sql("INSERT INTO kiosk_identities VALUES(99,'invalid','Invalid','ACTIVE','hash',NULL,now(),%s)", (invalid,))
                assert getattr(exc.value.orig, 'sqlstate', None) == '23514'
            if with_inventory:
                with pytest.raises(Exception) as exc, conn.begin_nested():
                    conn.exec_driver_sql('UPDATE kiosk_identities SET display_number=1 WHERE id=10')
                assert getattr(exc.value.orig, 'sqlstate', None) == '23505'
            conn.exec_driver_sql("INSERT INTO kiosk_identities VALUES(98,'maximum','Max','ACTIVE','hash',NULL,now(),2147483647)")
            with pytest.raises(Exception) as exc, conn.begin_nested():
                conn.exec_driver_sql("INSERT INTO kiosk_identities VALUES(97,'too-large','Large','ACTIVE','hash',NULL,now(),2147483648)")
            assert getattr(exc.value.orig, 'sqlstate', None) == '22003'
            conn.exec_driver_sql("DELETE FROM kiosk_identities WHERE id=98")
            module.downgrade()
            assert [dict(x) for x in conn.execute(text('SELECT * FROM kiosk_identities ORDER BY id')).mappings()] == before
            conn.exec_driver_sql('DROP TABLE kiosk_identities')
            conn.exec_driver_sql(f'DROP SCHEMA {schema}')
    finally:
        engine.dispose()
