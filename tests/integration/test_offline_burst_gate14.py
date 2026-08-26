"""Reliability Validation Round 2, Gate 14 -- offline reconnect burst.

Simulates 30 kiosks reconnecting simultaneously, each submitting a queued
batch of offline events (START then FINISH, plus each event resubmitted
3x -- exactly what a kiosk retrying an unacknowledged upload after a
flaky reconnect looks like) over the real
/api/kiosk/offline-sync HTTP endpoint, using the deterministic 1-kiosk-1-
worker mapping FIX 2's load generator established (no employee/operation
sharing between kiosks -- only the parent PO is shared, matching FIX 2's
now-documented, expected contention characteristic).

Verifies: no 500 collapse, no duplicate business effect from the repeated
uploads (offline_sync's own idempotency, not just kiosk_client_events'
UNIQUE constraint), no connection exhaustion, and a clean audit_integrity()
afterward.
"""
from __future__ import annotations

import concurrent.futures
import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

N_KIOSKS = 30


def _event(kiosk, sequence, kind, local_session, worker_qr, operation_qr, **qty):
    return {
        'schema_version': 1,
        'client_event_id': f'{kiosk}-{sequence:06d}',
        'local_sequence': sequence,
        'local_session_id': local_session,
        'session_trace_id': local_session,
        'event_type': kind,
        'worker_qr': worker_qr,
        'operation_qr': operation_qr,
        'good_qty': qty.get('good', 0),
        'defect_qty': qty.get('defect', 0),
        'repairable_qty': qty.get('rework', 0),
        'scrap_qty': max(qty.get('defect', 0) - qty.get('rework', 0), 0),
        'time_quality': 'unknown',
        'boot_id': f'{kiosk}-BOOT',
        'device_uptime_ms': sequence * 100,
        'offline_snapshot_revision': 'GATE14-REVISION',
        'offline': True,
    }


def _make_graph(db, n, suffix):
    with db.cursor() as cur:
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES (%s,'Gate14',1000,'IN_PROGRESS') RETURNING id", (f'G14-PO-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES (%s,%s,'Gate14 Part') RETURNING id", (po_id, f'G14-PART-{suffix}'))
        part_id = cur.fetchone()['id']
        kiosks = []
        for i in range(n):
            cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES (%s,%s,'TEST','Worker',%s) RETURNING id",
                        (f'G14-EMP-{suffix}-{i}', f'Gate14 Worker {i}', f'WF|EMP|G14-{suffix}-{i}'))
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                VALUES (%s,%s,%s,'Gate14 Operation','IN_PROGRESS',%s) RETURNING id""",
                (po_id, part_id, f'G14-OP-{suffix}-{i}', f'WF|OP|G14-{suffix}-{i}'))
            station_code = f'G14-ST-{suffix}-{i}'
            cur.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES (%s,%s,'TEST','TEST') RETURNING id", (station_code, f'Gate14 Station {i}'))
            device_uuid = f'G14-KIOSK-{suffix}-{i}'
            cur.execute("INSERT INTO kiosk_identities(device_uuid,status) VALUES (%s,'ACTIVE')", (device_uuid,))
            kiosks.append({'device_uuid': device_uuid, 'station_code': station_code, 'worker_qr': f'WF|EMP|G14-{suffix}-{i}', 'operation_qr': f'WF|OP|G14-{suffix}-{i}'})
    return {'po_id': po_id, 'part_id': part_id, 'kiosks': kiosks}


def _drop_graph(db, g, suffix):
    with db.cursor() as cur:
        cur.execute("DELETE FROM kiosk_client_events WHERE kiosk_id LIKE %s", (f'G14-KIOSK-{suffix}-%',))
        cur.execute("DELETE FROM production_trace_events WHERE operation_id IN (SELECT id FROM operations WHERE code LIKE %s)", (f'G14-OP-{suffix}-%',))
        cur.execute("DELETE FROM quantity_movements WHERE operation_id IN (SELECT id FROM operations WHERE code LIKE %s)", (f'G14-OP-{suffix}-%',))
        cur.execute("DELETE FROM kiosk_idempotency WHERE request_id LIKE %s", (f'%{suffix}%',))
        cur.execute("DELETE FROM work_sessions WHERE employee_id IN (SELECT id FROM employees WHERE employee_no LIKE %s)", (f'G14-EMP-{suffix}-%',))
        cur.execute("DELETE FROM kiosk_identities WHERE device_uuid LIKE %s", (f'G14-KIOSK-{suffix}-%',))
        cur.execute("DELETE FROM stations WHERE code LIKE %s", (f'G14-ST-{suffix}-%',))
        cur.execute("DELETE FROM operations WHERE code LIKE %s", (f'G14-OP-{suffix}-%',))
        cur.execute("DELETE FROM parts WHERE id=%s", (g['part_id'],))
        cur.execute("DELETE FROM production_orders WHERE id=%s", (g['po_id'],))
        cur.execute("DELETE FROM employees WHERE employee_no LIKE %s", (f'G14-EMP-{suffix}-%',))


@pytest.mark.timeout(180)
def test_offline_reconnect_burst_no_collapse_no_duplicates(db):
    suffix = uuid.uuid4().hex[:10]
    g = _make_graph(db, N_KIOSKS, suffix)
    try:
        def burst_one(kiosk):
            local_session = f'{kiosk["device_uuid"]}-SESSION'
            events = [
                _event(kiosk['device_uuid'], 1, 'START', local_session, kiosk['worker_qr'], kiosk['operation_qr']),
                _event(kiosk['device_uuid'], 2, 'FINISH', local_session, kiosk['worker_qr'], kiosk['operation_qr'], good=4, defect=1, rework=0),
            ]
            # Each kiosk resubmits its whole queued batch 3x -- exactly
            # what a real device retrying after a flaky reconnect does
            # (fire-and-forget with at-least-once delivery).
            responses = []
            for _ in range(3):
                r = requests.post(f'{BASE_URL}/api/kiosk/offline-sync', json={
                    'device_id': kiosk['device_uuid'], 'station_code': kiosk['station_code'], 'events': events,
                }, timeout=30)
                responses.append(r)
            return kiosk['device_uuid'], responses

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=N_KIOSKS) as pool:
            futures = [pool.submit(burst_one, k) for k in g['kiosks']]
            for f in concurrent.futures.as_completed(futures):
                device_uuid, responses = f.result()
                results[device_uuid] = responses

        # No 500 collapse: every request (30 kiosks x 3 resubmits = 90
        # HTTP calls, each carrying 2 events) must get a real HTTP
        # response, and none of them a 5xx.
        assert len(results) == N_KIOSKS
        for device_uuid, responses in results.items():
            for r in responses:
                assert r.status_code < 500, f'{device_uuid}: {r.status_code} {r.text[:300]}'
                if r.status_code == 200:
                    for item in r.json().get('results', []):
                        assert item.get('status') in ('accepted', 'duplicate'), f'{device_uuid}: unexpected event outcome {item}'

        # No duplicate business effect: exactly ONE closed session per
        # kiosk's employee, with the correct final quantities, despite each
        # kiosk having uploaded its 2-event batch 3 times over.
        with db.cursor() as cur:
            cur.execute("""SELECT ws.id,ws.status,ws.good_qty,ws.defect_qty,ws.rework_qty
                FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id
                WHERE e.employee_no LIKE %s""", (f'G14-EMP-{suffix}-%',))
            rows = cur.fetchall()
        assert len(rows) == N_KIOSKS, f'expected exactly {N_KIOSKS} sessions (one per kiosk), found {len(rows)}'
        for row in rows:
            assert row['status'] == 'CLOSED'
            assert row['good_qty'] == 4 and row['defect_qty'] == 1 and row['rework_qty'] == 0

        # Offline event ledger itself: 30 kiosks x 2 distinct client_event_ids
        # each -- the resubmits must have deduplicated, not multiplied rows.
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM kiosk_client_events WHERE kiosk_id LIKE %s", (f'G14-KIOSK-{suffix}-%',))
            assert cur.fetchone()['n'] == N_KIOSKS * 2

        from mesflow.services.integrity_audit_service import audit_integrity
        integrity = audit_integrity()
        employee_ids = {r['id'] for r in db.execute(
            "SELECT id FROM employees WHERE employee_no LIKE %s", (f'G14-EMP-{suffix}-%',)
        ).fetchall()}
        for category, items in integrity.items():
            offending = [x for x in items if str(x.get('device_uuid', '')).startswith(f'G14-KIOSK-{suffix}')
                         or x.get('employee_id') in employee_ids]
            assert not offending, f'{category}: {offending}'
    finally:
        _drop_graph(db, g, suffix)
