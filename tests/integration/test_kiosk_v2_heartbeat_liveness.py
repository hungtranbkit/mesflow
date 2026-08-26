"""Real bug found live (2026-08-26): POST /api/kiosk/v2/heartbeat accepted
every heartbeat (200, accepted:true) but never wrote to kiosk_status, so
system_health_service.KioskProvider (and the Trạm kiosk / kiosk-management
dashboard) could never show a genuinely healthy, actively-heartbeating v2
kiosk as ONLINE -- it always read a NULL/stale last_heartbeat_at. Reported
symptom: "ESP đang online, mà sao trên trạm kiosk trên mesflow vẫn báo
offline" (ESP is online, but the kiosk station on MESFlow still reports
offline). Root cause and fix live in app/mesflow/web/kiosk_v2.py::heartbeat().
"""
from __future__ import annotations

import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def test_v2_heartbeat_actually_updates_kiosk_status_liveness(db):
    device = f'V2-HB-{uuid.uuid4().hex[:10]}'
    bind = requests.post(f'{BASE_URL}/api/kiosk/bind', json={'device_uuid': device}, timeout=10)
    assert bind.status_code == 200, bind.text

    with db.cursor() as cur:
        cur.execute('SELECT last_heartbeat_at FROM kiosk_status WHERE device_uuid=%s', (device,))
        before = cur.fetchone()
    # Before the fix, a v2 kiosk that was only ever bound (never sent a v1
    # /station/heartbeat or /kiosk/heartbeat) has NO kiosk_status row at all.
    assert before is None

    r = requests.post(f'{BASE_URL}/api/kiosk/v2/heartbeat', json={
        'device_id': device, 'ui_state': 'READY', 'wifi_rssi': -55, 'uptime_seconds': 120,
        'firmware_version': '0.10.2',
    }, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()['accepted'] is True

    with db.cursor() as cur:
        cur.execute('SELECT last_heartbeat_at,ui_state,wifi_rssi FROM kiosk_status WHERE device_uuid=%s', (device,))
        after = cur.fetchone()
    assert after is not None, 'v2 heartbeat must create/update a kiosk_status row -- this is exactly what the dashboard reads for ONLINE/OFFLINE'
    assert after['last_heartbeat_at'] is not None
    assert after['ui_state'] == 'READY'
    assert after['wifi_rssi'] == -55
    with db.cursor() as cur:
        cur.execute('SELECT firmware_version FROM kiosk_identities WHERE device_uuid=%s', (device,))
        assert cur.fetchone()['firmware_version'] == '0.10.2'

    # And the actual health computation the dashboard uses now sees it as ONLINE.
    s = requests.Session()
    s.post(f'{BASE_URL}/api/auth/login', json={'username': 'admin', 'password': 'Admin@123456'}, timeout=10)
    health = s.get(f'{BASE_URL}/api/system-health', timeout=10).json()
    kiosk_component = next(c for c in health['components'] if c['component'] == 'KIOSK_FLEET')
    item = next(x for x in kiosk_component['details']['items'] if x['device_uuid'] == device)
    assert item['normalized_status'] == 'ONLINE'


def test_v2_heartbeat_still_rejects_disabled_kiosk(db):
    device = f'V2-HB-DISABLED-{uuid.uuid4().hex[:10]}'
    bind = requests.post(f'{BASE_URL}/api/kiosk/bind', json={'device_uuid': device}, timeout=10)
    identity_id = None
    with db.cursor() as cur:
        cur.execute('SELECT id FROM kiosk_identities WHERE device_uuid=%s', (device,))
        identity_id = cur.fetchone()['id']
        cur.execute("UPDATE kiosk_identities SET status='DISABLED' WHERE id=%s", (identity_id,))

    r = requests.post(f'{BASE_URL}/api/kiosk/v2/heartbeat', json={'device_id': device}, timeout=10)
    # The endpoint always returns accepted:true (fire-and-forget protocol,
    # unchanged by this fix) -- but it must NOT have written a live
    # heartbeat for a DISABLED identity.
    assert r.status_code == 200
    with db.cursor() as cur:
        cur.execute('SELECT 1 FROM kiosk_status WHERE device_uuid=%s', (device,))
        assert cur.fetchone() is None
