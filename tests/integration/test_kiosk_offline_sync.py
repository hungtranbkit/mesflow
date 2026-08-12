import concurrent.futures
import uuid

from conftest import BASE_URL


def _event(kiosk, sequence, kind, local_session, worker_qr, operation_qr, **qty):
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
        'time_quality': 'unknown',
        'boot_id': 'TEST-BOOT',
        'device_uptime_ms': sequence * 100,
        'offline_snapshot_revision': 'TEST-REVISION',
        'offline': True,
    }


def _post(api, kiosk, station, events):
    return api.post(f'{BASE_URL}/api/kiosk/offline-sync', json={
        'device_id': kiosk, 'station_code': station, 'events': events,
    }, timeout=30)


def test_offline_sync_accepted_duplicate_payload_conflict(api, db, seeded_factory):
    g = seeded_factory
    kiosk = f'CODEX-KIOSK-{uuid.uuid4().hex[:10]}'
    worker = f'WF|EMP|TEST-{g["suffix"]}'
    operation = f'WF|OP|TEST-OP-{g["suffix"]}'
    start = _event(kiosk, 1, 'START', 'LOCAL-1', worker, operation)
    finish = _event(kiosk, 2, 'FINISH', 'LOCAL-1', worker, operation, good=22, defect=3, rework=1)

    first = _post(api, kiosk, f'TEST-ST-{g["suffix"]}', [start, finish])
    assert first.status_code == 200, first.text
    assert [x['status'] for x in first.json()['results']] == ['accepted', 'accepted']
    replay = _post(api, kiosk, f'TEST-ST-{g["suffix"]}', [start, finish])
    assert [x['status'] for x in replay.json()['results']] == ['duplicate', 'duplicate']

    changed = dict(finish, good_qty=999)
    conflict = _post(api, kiosk, f'TEST-ST-{g["suffix"]}', [changed]).json()['results'][0]
    assert conflict['status'] == 'rejected'
    assert conflict['reason_code'] == 'IDEMPOTENCY_PAYLOAD_CONFLICT'
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) count,MAX(good_qty) good,MAX(defect_qty) defect,MAX(rework_qty) rework FROM work_sessions WHERE employee_id=%s', (g['employee_id'],))
        row = cur.fetchone()
    assert row == {'count': 1, 'good': 22, 'defect': 3, 'rework': 1}


def test_concurrent_duplicate_creates_one_session(api, db, seeded_factory):
    g = seeded_factory
    kiosk = f'CODEX-KIOSK-{uuid.uuid4().hex[:10]}'
    event = _event(kiosk, 1, 'START', 'CONCURRENT-1', f'WF|EMP|TEST-{g["suffix"]}', f'WF|OP|TEST-OP-{g["suffix"]}')
    station = f'TEST-ST-{g["suffix"]}'

    def send(_):
        # requests.Session is not guaranteed thread-safe; use requests directly.
        import requests
        return requests.post(f'{BASE_URL}/api/kiosk/offline-sync', json={
            'device_id': kiosk, 'station_code': station, 'events': [event],
        }, timeout=30).json()['results'][0]['status']

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(send, range(10)))
    assert statuses.count('accepted') >= 1
    assert set(statuses) <= {'accepted', 'duplicate'}
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) count FROM work_sessions WHERE employee_id=%s', (g['employee_id'],))
        assert cur.fetchone()['count'] == 1


def test_one_hundred_ordered_events_survive_batching(api, db, seeded_factory):
    g = seeded_factory
    kiosk = f'CODEX-KIOSK-{uuid.uuid4().hex[:10]}'
    worker = f'WF|EMP|TEST-{g["suffix"]}'
    operation = f'WF|OP|TEST-OP-{g["suffix"]}'
    station = f'TEST-ST-{g["suffix"]}'
    events = []
    for index in range(50):
        seq = index * 2 + 1
        local = f'LOCAL-{index:03d}'
        events.append(_event(kiosk, seq, 'START', local, worker, operation))
        events.append(_event(kiosk, seq + 1, 'FINISH', local, worker, operation, good=1))
    results = []
    for offset in range(0, 100, 20):
        response = _post(api, kiosk, station, events[offset:offset + 20])
        assert response.status_code == 200, response.text
        results.extend(response.json()['results'])
    assert len(results) == 100
    assert all(x['status'] == 'accepted' for x in results)
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) count,COALESCE(SUM(good_qty),0) good FROM work_sessions WHERE employee_id=%s', (g['employee_id'],))
        assert cur.fetchone() == {'count': 50, 'good': 50}
        cur.execute('SELECT array_agg(local_sequence ORDER BY id) seq FROM kiosk_client_events WHERE kiosk_id=%s', (kiosk,))
        assert cur.fetchone()['seq'] == list(range(1, 101))


def test_business_reject_is_audited_and_does_not_block_later_event(api, db, seeded_factory):
    g = seeded_factory
    kiosk = f'CODEX-KIOSK-{uuid.uuid4().hex[:10]}'
    operation = f'WF|OP|TEST-OP-{g["suffix"]}'
    bad = _event(kiosk, 1, 'START', 'BAD-1', 'WF|EMP|DOES-NOT-EXIST', operation)
    good = _event(kiosk, 2, 'START', 'GOOD-2', f'WF|EMP|TEST-{g["suffix"]}', operation)
    response = _post(api, kiosk, f'TEST-ST-{g["suffix"]}', [bad, good])
    assert response.status_code == 200, response.text
    assert [x['status'] for x in response.json()['results']] == ['rejected', 'accepted']
    with db.cursor() as cur:
        cur.execute('SELECT status,reason_code FROM kiosk_client_events WHERE client_event_id=%s', (bad['client_event_id'],))
        assert cur.fetchone() == {'status': 'rejected', 'reason_code': 'BUSINESS_REJECT'}


def test_snapshot_and_three_kiosks_have_isolated_sequences(api, db, seeded_factory):
    g = seeded_factory
    station = f'TEST-ST-{g["suffix"]}'
    worker = f'WF|EMP|TEST-{g["suffix"]}'
    operation = f'WF|OP|TEST-OP-{g["suffix"]}'
    kiosks = [f'CODEX-KIOSK-0{i}-{uuid.uuid4().hex[:6]}' for i in range(1, 4)]
    for kiosk in kiosks:
        snapshot = api.get(f'{BASE_URL}/api/kiosk/offline-snapshot', headers={'X-Device-ID': kiosk}, timeout=30)
        assert snapshot.status_code == 200, snapshot.text
        body = snapshot.json()
        assert body['schema_version'] == 1 and body['revision']
        assert any(x['qr'] == worker for x in body['employees'])
        start = _event(kiosk, 1, 'START', f'{kiosk}-LOCAL', worker, operation)
        finish = _event(kiosk, 2, 'FINISH', f'{kiosk}-LOCAL', worker, operation, good=1)
        result = _post(api, kiosk, station, [start, finish]).json()['results']
        assert [x['status'] for x in result] == ['accepted', 'accepted']
    with db.cursor() as cur:
        cur.execute('SELECT kiosk_id,array_agg(local_sequence ORDER BY local_sequence) seq FROM kiosk_client_events WHERE kiosk_id=ANY(%s) GROUP BY kiosk_id', (kiosks,))
        rows = cur.fetchall()
    assert {row['kiosk_id']: row['seq'] for row in rows} == {kiosk: [1, 2] for kiosk in kiosks}
