"""Session Lifecycle Fix Plan Phase 7 -- offline session timestamp
integrity. A kiosk_client_events row with time_quality=='synced' carries a
real device clock reading; work_sessions.started_at/ended_at must reflect
that reading (started_at_trusted/ended_at_trusted=TRUE) instead of blindly
using server CURRENT_TIMESTAMP -- but only when the value is plausible
(time_policy.trusted_event_time's skew bounds); 'estimated'/'unknown'
quality, or an implausible synced value, must fall back to server time
exactly as before this phase (started_at_trusted/ended_at_trusted=FALSE)."""
import uuid
from datetime import datetime, timedelta, timezone

from conftest import BASE_URL


def _event(kiosk, sequence, kind, local_session, worker_qr, operation_qr, event_time, quality, **qty):
    event_id = f'{kiosk}-{sequence:06d}'
    return {
        'schema_version': 1,
        'client_event_id': event_id,
        'local_sequence': sequence,
        'local_session_id': local_session,
        'session_trace_id': local_session,
        'event_type': kind,
        'worker_qr': worker_qr,
        'operation_qr': operation_qr,
        'good_qty': qty.get('good', 0),
        'defect_qty': qty.get('defect', 0),
        'repairable_qty': qty.get('rework', 0),
        'scrap_qty': qty.get('defect', 0) - qty.get('rework', 0),
        'time_quality': quality,
        'event_time': event_time.isoformat() if event_time else None,
        'boot_id': 'TEST-BOOT-P7',
        'device_uptime_ms': sequence * 100,
        'offline_snapshot_revision': 'TEST-REVISION',
        'offline': True,
    }


def _post(api, kiosk, station, events):
    return api.post(f'{BASE_URL}/api/kiosk/offline-sync', json={
        'device_id': kiosk, 'station_code': station, 'events': events,
    }, timeout=30)


def test_synced_plausible_timestamp_is_trusted_onto_the_session(api, db, seeded_factory):
    g = seeded_factory
    kiosk = f'P7-KIOSK-{uuid.uuid4().hex[:10]}'
    worker = f'WF|EMP|TEST-{g["suffix"]}'
    operation = f'WF|OP|TEST-OP-{g["suffix"]}'
    station = db.execute('SELECT code FROM stations WHERE id=%s', (g['station_id'],)).fetchone()['code']

    real_start = datetime.now(timezone.utc) - timedelta(hours=3)
    real_finish = datetime.now(timezone.utc) - timedelta(hours=1)
    events = [
        _event(kiosk, 1, 'START', 'S1', worker, operation, real_start, 'synced'),
        _event(kiosk, 2, 'FINISH', 'S1', worker, operation, real_finish, 'synced', good=5),
    ]
    r = _post(api, kiosk, station, events)
    assert r.status_code == 200, r.text
    results = r.json()['results']
    assert all(x['status'] == 'accepted' for x in results), results
    session_id = results[0]['server_session_id']

    row = db.execute(
        'SELECT started_at,ended_at,started_at_trusted,ended_at_trusted FROM work_sessions WHERE id=%s', (session_id,)
    ).fetchone()
    assert row['started_at_trusted'] is True
    assert row['ended_at_trusted'] is True
    assert abs((row['started_at'] - real_start).total_seconds()) < 2
    assert abs((row['ended_at'] - real_finish).total_seconds()) < 2


def test_unknown_quality_falls_back_to_server_time(api, db, seeded_factory):
    g = seeded_factory
    kiosk = f'P7-KIOSK-{uuid.uuid4().hex[:10]}'
    worker = f'WF|EMP|TEST-{g["suffix"]}'
    operation = f'WF|OP|TEST-OP-{g["suffix"]}'
    station = db.execute('SELECT code FROM stations WHERE id=%s', (g['station_id'],)).fetchone()['code']

    stale_claim = datetime.now(timezone.utc) - timedelta(hours=3)
    before = datetime.now(timezone.utc)
    events = [_event(kiosk, 1, 'START', 'S1', worker, operation, stale_claim, 'unknown')]
    r = _post(api, kiosk, station, events)
    assert r.status_code == 200, r.text
    session_id = r.json()['results'][0]['server_session_id']

    row = db.execute('SELECT started_at,started_at_trusted FROM work_sessions WHERE id=%s', (session_id,)).fetchone()
    assert row['started_at_trusted'] is False
    # started_at reflects the SERVER's own receipt time, not the untrusted claim.
    assert row['started_at'] >= before - timedelta(seconds=2)


def test_synced_but_implausibly_far_future_is_not_trusted(api, db, seeded_factory):
    g = seeded_factory
    kiosk = f'P7-KIOSK-{uuid.uuid4().hex[:10]}'
    worker = f'WF|EMP|TEST-{g["suffix"]}'
    operation = f'WF|OP|TEST-OP-{g["suffix"]}'
    station = db.execute('SELECT code FROM stations WHERE id=%s', (g['station_id'],)).fetchone()['code']

    bogus_future = datetime.now(timezone.utc) + timedelta(days=400)  # clearly a broken/unset RTC
    events = [_event(kiosk, 1, 'START', 'S1', worker, operation, bogus_future, 'synced')]
    r = _post(api, kiosk, station, events)
    assert r.status_code == 200, r.text
    session_id = r.json()['results'][0]['server_session_id']

    row = db.execute('SELECT started_at,started_at_trusted FROM work_sessions WHERE id=%s', (session_id,)).fetchone()
    assert row['started_at_trusted'] is False
    assert row['started_at'] < bogus_future - timedelta(days=1)
