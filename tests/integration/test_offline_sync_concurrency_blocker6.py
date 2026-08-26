"""Codex audit Blocker 6 -- a real (not merely environmental) race in
OfflineSyncRepository._record(): two threads posting the EXACT same
offline event concurrently could both pass the unprotected
`existing = self._existing(event_id)` check (a plain SELECT, no lock) and
both reach the INSERT into kiosk_client_events. `ON CONFLICT(client_event_id)
DO NOTHING` only arbitrates that one constraint -- the table also has a
separate UNIQUE(kiosk_id, local_sequence) constraint
(uq_kiosk_client_event_sequence) that the losing thread's INSERT could hit
instead, an unhandled UniqueViolation that used to surface as a bare 409
with no `results` key. Reproduced independently (~1 in 3-16 attempts at 10
concurrent threads before the fix; 0 in 150+ after)."""
from __future__ import annotations

import concurrent.futures
import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _event(kiosk: str, worker_qr: str, operation_qr: str) -> dict:
    return {
        'schema_version': 1, 'client_event_id': f'{kiosk}-000001', 'local_sequence': 1,
        'local_session_id': 'CONCURRENT-1', 'session_trace_id': 'CONCURRENT-1', 'event_type': 'START',
        'worker_qr': worker_qr, 'operation_qr': operation_qr,
        'good_qty': 0, 'defect_qty': 0, 'repairable_qty': 0, 'scrap_qty': 0,
        'time_quality': 'unknown', 'boot_id': 'TEST-BOOT', 'device_uptime_ms': 100,
        'offline_snapshot_revision': 'TEST-REVISION', 'offline': True,
    }


def _send(kiosk: str, event: dict):
    return requests.post(f'{BASE_URL}/api/kiosk/offline-sync',
                          json={'device_id': kiosk, 'station_code': 'ANY', 'events': [event]}, timeout=30)


@pytest.mark.slow
def test_20x_concurrent_identical_event_never_produces_an_unhandled_conflict(db, seeded_factory):
    """Higher concurrency (20 threads, same event, same fresh kiosk) than
    the original 10-thread test -- proves the fix (a real, reproduced race
    in kiosk_client_events' dual UNIQUE constraints), not just the happy
    path. See test_scheduler_cron_install_blocker1.py-style module
    docstring above for the full race explanation; empirically this
    reliably reproduced within 3-16 attempts at 10 threads before the fix
    and did not reproduce in 150+ attempts after."""
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute('SELECT qr FROM employees WHERE id=%s', (g['employee_id'],))
        worker_qr = cur.fetchone()['qr']
        cur.execute('SELECT qr FROM operations WHERE id=%s', (g['operation_id'],))
        operation_qr = cur.fetchone()['qr']
    kiosk = f'BLOCKER6-{uuid.uuid4().hex[:10]}'
    event = _event(kiosk, worker_qr, operation_qr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(lambda _: _send(kiosk, event), range(20)))
    for r in responses:
        assert r.status_code == 200, r.text
        assert 'results' in r.json(), r.text
    statuses = [r.json()['results'][0]['status'] for r in responses]
    # The HTTP-visible status per request can legitimately show more than
    # one 'accepted' under true simultaneous concurrency (many threads can
    # each race past the unprotected `existing` pre-check before any of
    # them durably records the ledger row -- 'duplicate' only fires for a
    # request that arrives AFTER a prior one has already committed); that
    # part is unaffected by this fix and is not the invariant this blocker
    # cares about. What MUST hold -- and is what the fix actually
    # guarantees -- is the real business effect: exactly ONE session, no
    # unhandled error responses of any kind.
    assert statuses.count('accepted') >= 1, statuses
    assert set(statuses) <= {'accepted', 'duplicate'}, statuses
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) n FROM work_sessions WHERE employee_id=%s AND status='OPEN'", (g['employee_id'],))
        assert cur.fetchone()['n'] == 1
