"""Migration 0055 + ESP heartbeat OTA scope against real PostgreSQL and a
real running MESFlow API (compose.test.yml). Proves:

* 0055 seeded exactly one stable ``mesflow_instance_id`` and added the
  ``kiosk_identities.hardware_profile`` / ``firmware_artifact_id`` columns;
* a real heartbeat persists the device-reported profile/artifact and the
  response carries this instance's id (ota_agent_url only when configured);
* /api/internal/instance and /api/internal/kiosks agree on the instance and
  expose the profile; readiness carries the instance and stays token-scoped.
"""
from __future__ import annotations

import os
import re
import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

INTERNAL = {'X-MESFlow-Internal-Token': os.environ.get('MESFLOW_INTERNAL_API_TOKEN') or 'local-internal-readiness-token'}
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


@pytest.fixture(autouse=True)
def _cleanup(db):
    yield
    with db.cursor() as cur:
        cur.execute("DELETE FROM kiosk_status WHERE device_uuid LIKE 'OTA55-%'")
        cur.execute("DELETE FROM kiosk_identities WHERE device_uuid LIKE 'OTA55-%'")


def _register_and_approve(api, db):
    device = f'OTA55-{uuid.uuid4()}'
    reg = requests.post(f'{BASE_URL}/api/kiosk/register', json={'device_uuid': device, 'device_name': 'OTA55 Kiosk'}, timeout=10)
    assert reg.status_code == 201, reg.text
    identity_id = reg.json()['identity']['id']
    with db.cursor() as cur:
        cur.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES(%s,'OTA55 Station','TEST','TEST') RETURNING id,code",
                    (f'OTA55-ST-{uuid.uuid4().hex[:8]}',))
        station = cur.fetchone()
    approve = api.post(f'{BASE_URL}/api/kiosk-identities/{identity_id}/approve', json={'station_id': station['id']}, timeout=10)
    assert approve.status_code == 200, approve.text
    return device, station['code']


def test_migration_0055_schema_and_single_stable_instance_id(db):
    with db.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        assert cur.fetchone()['version_num'] >= '0055'
        cur.execute("SELECT value FROM system_meta WHERE key='mesflow_instance_id'")
        rows = cur.fetchall()
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_name='kiosk_identities' AND column_name IN ('hardware_profile','firmware_artifact_id')""")
        cols = {r['column_name'] for r in cur.fetchall()}
    assert len(rows) == 1 and UUID_RE.match(rows[0]['value'])
    assert cols == {'hardware_profile', 'firmware_artifact_id'}


def test_heartbeat_persists_profile_and_returns_instance(api, db):
    device, station_code = _register_and_approve(api, db)
    inst = requests.get(f'{BASE_URL}/api/internal/instance', headers=INTERNAL, timeout=10)
    assert inst.status_code == 200, inst.text
    inst = inst.json()
    assert inst['state'] == 'VERIFIED' and UUID_RE.match(inst['instance_id'])
    assert requests.get(f'{BASE_URL}/api/internal/instance', timeout=10).status_code == 401

    hb = requests.post(f'{BASE_URL}/api/station/heartbeat', json={
        'device_uuid': device, 'ui_state': 'READY', 'firmware_version': '5.6.3', 'firmware_build': '20261111.0001',
        'hardware_profile': 'es3c28p-n16r8-m910-gm65uart1', 'firmware_artifact_id': 'a' * 64, 'ota_capable': True,
    }, timeout=10)
    assert hb.status_code == 200, hb.text
    body = hb.json()
    assert body['instance_id'] == inst['instance_id']
    # No compiled/shared default: without MESFLOW_OTA_AGENT_URL nothing is advertised.
    assert body['ota_agent_url'] == (inst.get('ota_agent_url') or '')
    assert 'deploy.mesflow.net' not in body['ota_agent_url']

    with db.cursor() as cur:
        cur.execute("SELECT hardware_profile,firmware_artifact_id,firmware_version FROM kiosk_identities WHERE device_uuid=%s", (device,))
        row = cur.fetchone()
    assert row == {'hardware_profile': 'es3c28p-n16r8-m910-gm65uart1', 'firmware_artifact_id': 'a' * 64, 'firmware_version': '5.6.3'}

    inv = requests.get(f'{BASE_URL}/api/internal/kiosks', headers=INTERNAL, timeout=10).json()
    assert inv['instance_id'] == inst['instance_id']
    item = next(x for x in inv['items'] if x['kiosk_id'] == device)
    assert item['hardware_profile'] == 'es3c28p-n16r8-m910-gm65uart1' and item['station_code'] == station_code

    ready = requests.get(f'{BASE_URL}/api/internal/kiosks/{device}/ota-readiness', headers=INTERNAL, timeout=10).json()
    assert ready['instance_id'] == inst['instance_id'] and ready['instance_state'] == 'VERIFIED'
    # Another device's token (here: none) cannot read this kiosk's readiness.
    assert requests.get(f'{BASE_URL}/api/internal/kiosks/{device}/ota-readiness', timeout=10).status_code == 403


def test_instance_id_is_stable_across_calls(db):
    a = requests.get(f'{BASE_URL}/api/internal/instance', headers=INTERNAL, timeout=10).json()
    b = requests.get(f'{BASE_URL}/api/internal/instance', headers=INTERNAL, timeout=10).json()
    with db.cursor() as cur:
        cur.execute("SELECT value FROM system_meta WHERE key='mesflow_instance_id'")
        stored = cur.fetchone()['value']
    assert a['instance_id'] == b['instance_id'] == stored
