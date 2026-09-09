"""Regressions for the three defects the 2026-09-09 architecture audit found.

Each of these shipped, reached the live TEST host, and was invisible to the
suite that was green at the time — so each gets a test that fails on the old
behaviour rather than a comment promising not to do it again.

  P0-1  the legacy ESP validation endpoint refused every id-based QR payload,
        which made SETUP labels unscannable on older firmware
  P0-2  /api/kiosk-web/* accepted unauthenticated production writes and served
        the whole employee roster (badge QR values included) to the internet
  P1-e  support Operations were counted as production Operations in four
        management rollups, permanently deflating progress
"""
from __future__ import annotations

import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


# ---------------------------------------------------------------- P0-1

def test_legacy_lookup_resolves_an_id_based_qr_payload(api, db, seeded_factory):
    """`/api/lookup` is what the OLDER ESP firmware calls before a scan.

    It matched only `WF|OP|`, and `'WF|OPID|4243'.startswith('WF|OP|')` is
    False — the fifth character is 'I', not '|'. Every SETUP label carries the
    id shape, so setup was unreachable on those devices while working
    everywhere else. That asymmetry is what kept it hidden.
    """
    graph = seeded_factory
    operation_id = graph['operation_id']

    by_id = requests.get(f'{BASE_URL}/api/lookup', params={'qr': f'WF|OPID|{operation_id}'}, timeout=15)
    assert by_id.status_code == 200, by_id.text
    body = by_id.json()
    assert body['type'] == 'operation'
    assert body['operation']['id'] == operation_id

    # The legacy code shape still resolves to the same row — this fix adds a
    # payload, it does not replace one. Labels already printed keep working.
    code = db.execute('SELECT code FROM operations WHERE id=%s', (operation_id,)).fetchone()['code']
    by_code = requests.get(f'{BASE_URL}/api/lookup', params={'qr': f'WF|OP|{code}'}, timeout=15)
    assert by_code.status_code == 200, by_code.text
    assert by_code.json()['operation']['id'] == operation_id


def test_legacy_lookup_resolves_a_setup_label_end_to_end(api, seeded_factory):
    """The real shape of the bug: configure setup, scan its printed label."""
    graph = seeded_factory
    assert api.put(f"{BASE_URL}/api/operations/{graph['operation_id']}/setup",
                   json={'requires_setup': True, 'setup_note': 'Lắp khuôn'}, timeout=15).status_code == 200
    setup = api.get(f"{BASE_URL}/api/operations/{graph['operation_id']}/setup", timeout=15).json()['setup']

    scanned = requests.get(f'{BASE_URL}/api/lookup', params={'qr': setup['qr']}, timeout=15)
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()['operation']['id'] == setup['id']


def test_legacy_lookup_still_rejects_a_payload_it_cannot_resolve(seeded_factory):
    """Widening the accepted shapes must not turn the endpoint into a sink."""
    junk = requests.get(f'{BASE_URL}/api/lookup', params={'qr': 'WF|THING|9'}, timeout=15)
    assert junk.status_code == 400, junk.text


# ---------------------------------------------------------------- P0-2

def _anon():
    """A client with no cookie and no kiosk token — i.e. the open internet."""
    return requests.Session()


def test_kiosk_web_writes_reject_an_unauthenticated_caller(seeded_factory):
    """These three endpoints write the authoritative production record.

    Until this fix they carried no decorator at all: anyone who could reach
    the host could open and close work sessions in a real employee's name, and
    close a session out from under a worker who was mid-task.
    """
    graph = seeded_factory
    anon = _anon()

    scan = anon.post(f'{BASE_URL}/api/kiosk-web/scan',
                     json={'qr': f"WF|EMP|TEST-{graph['suffix']}"}, timeout=15)
    assert scan.status_code in (401, 403), scan.text

    start = anon.post(f'{BASE_URL}/api/kiosk-web/start', json={
        'employee_id': graph['employee_id'], 'operation_id': graph['operation_id'],
        'request_id': f'ANON-{uuid.uuid4()}'}, timeout=15)
    assert start.status_code in (401, 403), start.text

    finish = anon.post(f'{BASE_URL}/api/kiosk-web/finish/1',
                       json={'good_qty': 5, 'request_id': f'ANON-{uuid.uuid4()}'}, timeout=15)
    assert finish.status_code in (401, 403), finish.text

    # Nothing was written by any of the three.
    assert anon.get(f'{BASE_URL}/api/kiosk-web/health', timeout=15).status_code == 200, \
        'the unauthenticated health probe must keep working'


def test_employee_roster_is_not_public(seeded_factory):
    """`demo-data` returned every employee's badge QR value — a credential.

    A badge QR is what identifies a worker at a terminal, so publishing the
    list is equivalent to publishing everyone's key.
    """
    anon = _anon()
    roster = anon.get(f'{BASE_URL}/api/kiosk-web/demo-data', timeout=15)
    assert roster.status_code in (401, 403), roster.text[:300]
    assert 'WF|EMP|' not in roster.text, 'a badge QR value leaked in the rejection body'


def test_kiosk_web_writes_accept_a_valid_device_token(db, seeded_factory):
    """A shop-floor terminal has nobody signed in, so it authenticates as a
    device: the same approved-kiosk token hardware kiosks already use."""
    graph = seeded_factory
    suffix = graph['suffix']
    device = f'WEB-TEST-{suffix}'
    token = f'kiosk-token-{uuid.uuid4().hex}'
    import hashlib
    with db.cursor() as cur:
        cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,status,token_hash,last_seen_at)
            VALUES(%s,'Web kiosk test','ACTIVE',%s,CURRENT_TIMESTAMP)""",
            (device, hashlib.sha256(token.encode()).hexdigest()))
    try:
        client = requests.Session()
        client.headers['X-Kiosk-Token'] = token
        scan = client.post(f'{BASE_URL}/api/kiosk-web/scan',
                           json={'qr': f'WF|EMP|TEST-{suffix}'}, timeout=15)
        assert scan.status_code == 200, scan.text
        assert scan.json()['employee']['id'] == graph['employee_id']

        started = client.post(f'{BASE_URL}/api/kiosk-web/start', json={
            'employee_id': graph['employee_id'], 'operation_id': graph['operation_id'],
            'station_id': graph['station_id'], 'device_uuid': device,
            'request_id': f'TOKEN-{uuid.uuid4()}'}, timeout=15)
        assert started.status_code == 201, started.text

        # ...and a revoked device loses access immediately, without a redeploy.
        with db.cursor() as cur:
            cur.execute("UPDATE kiosk_identities SET status='DISABLED' WHERE device_uuid=%s", (device,))
        revoked = client.post(f'{BASE_URL}/api/kiosk-web/scan',
                              json={'qr': f'WF|EMP|TEST-{suffix}'}, timeout=15)
        assert revoked.status_code in (401, 403), revoked.text
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (device,))


def test_a_signed_in_operator_needs_no_device_token(api, seeded_factory):
    """The browser kiosk must still work for an admin who is simply logged in."""
    graph = seeded_factory
    scan = api.post(f'{BASE_URL}/api/kiosk-web/scan',
                    json={'qr': f"WF|EMP|TEST-{graph['suffix']}"}, timeout=15)
    assert scan.status_code == 200, scan.text


# ---------------------------------------------------------------- P1-e

def _setup_row_for(api, operation_id):
    assert api.put(f'{BASE_URL}/api/operations/{operation_id}/setup',
                   json={'requires_setup': True, 'setup_note': 'x'}, timeout=15).status_code == 200
    return api.get(f'{BASE_URL}/api/operations/{operation_id}/setup', timeout=15).json()['setup']


def test_support_operations_do_not_dilute_management_rollups(api, db, seeded_factory):
    """A support Operation must not appear as an unfinished production step.

    It has no target and can never reach COMPLETED — a SETUP session closes at
    good_qty=0 by construction — so every rollup that counts it acquires a
    denominator that never fills. The PO-health board turns a finished PO into
    a permanent CRITICAL "Quá hạn"; the dispatch board reports the PO's whole
    quantity as WIP waiting at the setup bench.
    """
    graph = seeded_factory
    po_id = graph['po_id']

    before = api.get(f'{BASE_URL}/api/dashboard/control-tower', timeout=25)
    assert before.status_code == 200, before.text
    row_before = next((x for x in before.json()['po_health'] if x['id'] == po_id), None)
    assert row_before is not None, 'the seeded PO must appear on the control tower'
    count_before = row_before['operation_count']

    setup = _setup_row_for(api, graph['operation_id'])

    after = api.get(f'{BASE_URL}/api/dashboard/control-tower', timeout=25).json()
    row_after = next(x for x in after['po_health'] if x['id'] == po_id)
    assert row_after['operation_count'] == count_before, \
        'creating a SETUP row must not change the production Operation count'

    # The dispatch board must not offer a support Operation as work to schedule.
    control = api.get(f'{BASE_URL}/api/production-control?limit=2000', timeout=25)
    assert control.status_code == 200, control.text
    listed = [x for x in control.json()['operations'] if x['operation_id'] == setup['id']]
    assert not listed, 'a SETUP row reached the dispatch board with a priority score and phantom WIP'

    # ...nor rank in the Operation KPI table with a completion it cannot reach.
    kpi = api.get(f'{BASE_URL}/api/kpi/operations?limit=1000', timeout=25)
    if kpi.status_code == 200:
        payload = kpi.json()
        rows = payload.get('items') or payload.get('operations') or []
        assert not [x for x in rows if x.get('id') == setup['id']], \
            'a SETUP row appeared in the Operation KPI ranking at 0% forever'


def test_setup_time_still_counts_as_work_after_the_rollup_fix(api, db, seeded_factory):
    """The filters must exclude support work from PRODUCTION totals only.

    Excluding it from the employee day view instead would make a worker's
    setup hours vanish from their timesheet — the opposite failure.
    """
    graph = seeded_factory
    setup = _setup_row_for(api, graph['operation_id'])
    started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'SU-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'operation_id': setup['id'], 'station_id': graph['station_id']}, timeout=15)
    assert started.status_code == 201, started.text
    session_id = started.json()['session']['id']
    assert api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'SU-{uuid.uuid4()}', 'good_qty': 0, 'defect_qty': 0,
        'rework_qty': 0}, timeout=15).status_code == 200

    today = db.execute("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::date d").fetchone()['d']
    day = api.get(f'{BASE_URL}/api/dashboard/day?date={today}&limit=1000', timeout=25).json()
    assert [x for x in day['sessions'] if x['operation_id'] == setup['id']], \
        'setup time disappeared from the employee day view'
    assert not [x for x in day['items'] if x['operation_id'] == setup['id']], \
        'setup appeared in production progress'


def test_an_admin_can_issue_a_kiosk_token_and_that_token_works(api, db, seeded_factory):
    """The enrollment path, end to end.

    `POST /api/kiosk-identities/<id>/approve` already existed but nothing in
    the app called it, so the credential the gate above requires could not be
    minted through the product at all — a lock with no key. Kiosk Management
    now issues it. This test walks the whole path an admin actually takes:
    a terminal announces itself, the admin issues a token, the terminal writes
    with it, and issuing again cuts the old one off.
    """
    graph = seeded_factory
    device = f"WEB-ENROLL-{graph['suffix']}"

    # 1. The terminal announces itself the way the browser kiosk does.
    announced = requests.post(f'{BASE_URL}/api/kiosk-web/heartbeat',
                              json={'device_uuid': device, 'device_name': 'Web kiosk enroll test'}, timeout=15)
    assert announced.status_code == 200, announced.text
    identity = db.execute('SELECT id,status,token_hash FROM kiosk_identities WHERE device_uuid=%s',
                          (device,)).fetchone()
    assert identity is not None, 'the terminal must appear in Kiosk Management'
    # Stored as '' rather than NULL, which is just as safe: the lookup compares
    # it to a sha256 hex digest, and no digest is ever empty.
    assert not identity['token_hash'], \
        'announcing itself must NOT hand a device a credential -- an admin issues it'

    try:
        # ...and until then it cannot write, even though its row says ACTIVE.
        unenrolled = requests.post(f'{BASE_URL}/api/kiosk-web/scan',
                                   json={'qr': f"WF|EMP|TEST-{graph['suffix']}"}, timeout=15)
        assert unenrolled.status_code in (401, 403), unenrolled.text

        # 2. The admin issues a token against a real station.
        issued = api.post(f"{BASE_URL}/api/kiosk-identities/{identity['id']}/approve",
                          json={'station_id': graph['station_id']}, timeout=15)
        assert issued.status_code == 200, issued.text
        token = issued.json()['token']
        assert token, 'approve must return the plaintext token exactly once'

        # 3. The terminal can now write.
        client = requests.Session()
        client.headers['X-Kiosk-Token'] = token
        scan = client.post(f'{BASE_URL}/api/kiosk-web/scan',
                           json={'qr': f"WF|EMP|TEST-{graph['suffix']}"}, timeout=15)
        assert scan.status_code == 200, scan.text

        # 4. Re-issuing replaces the credential — the dialog warns about this,
        #    so the behaviour had better match the warning.
        reissued = api.post(f"{BASE_URL}/api/kiosk-identities/{identity['id']}/approve",
                            json={'station_id': graph['station_id']}, timeout=15)
        assert reissued.status_code == 200, reissued.text
        assert reissued.json()['token'] != token
        stale = client.post(f'{BASE_URL}/api/kiosk-web/scan',
                            json={'qr': f"WF|EMP|TEST-{graph['suffix']}"}, timeout=15)
        assert stale.status_code in (401, 403), 'the previous token must stop working'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_status WHERE device_uuid=%s', (device,))
            cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (device,))
