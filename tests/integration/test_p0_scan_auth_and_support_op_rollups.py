"""Regressions for the three defects the 2026-09-09 architecture audit found.

Each of these shipped, reached the live TEST host, and was invisible to the
suite that was green at the time — so each gets a test that fails on the old
behaviour rather than a comment promising not to do it again.

  P0-1  the legacy ESP validation endpoint refused every id-based QR payload,
        which made SETUP labels unscannable on older firmware
  P0-2  /api/kiosk-web/* accepted unauthenticated production writes and served
        the whole employee roster (badge QR values included) to the internet.
        SUPERSEDED IN PART, 2026-09-12: the business owner confirmed the Kiosk
        web surface is a PUBLIC operational surface -- a workshop machine opens
        /kiosk with no web account at all -- so scan/start/finish are anonymous
        again, deliberately and with tests that say so. The roster half of the
        fix stands: demo-data is still signed-in only.
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


def test_kiosk_web_writes_accept_an_anonymous_workshop_browser(seeded_factory):
    """The Kiosk web surface is PUBLIC (business owner decision, 2026-09-12).

    A machine on the shop floor opens /kiosk directly: no web account, no
    login page, no session cookie -- ever. It must be able to run the whole
    scan -> start -> finish loop anonymously, because the person doing the
    work is identified by the badge they scan, not by a browser login.

    This supersedes the 2026-09-09 P0-2 decision that put
    production_client_required() on these three routes. That decorator
    assumed every shop-floor terminal could carry a device token; in
    practice it locked the real workshop machines out of the kiosk. The
    roster endpoint below stays closed -- that part of P0-2 still stands.
    """
    graph = seeded_factory
    anon = _anon()

    scan = anon.post(f'{BASE_URL}/api/kiosk-web/scan',
                     json={'qr': f"WF|EMP|TEST-{graph['suffix']}"}, timeout=15)
    assert scan.status_code == 200, scan.text
    assert scan.json()['employee']['id'] == graph['employee_id']

    started = anon.post(f'{BASE_URL}/api/kiosk-web/start', json={
        'employee_id': graph['employee_id'], 'operation_id': graph['operation_id'],
        'station_id': graph['station_id'], 'device_uuid': f"ANON-{graph['suffix']}",
        'request_id': f'ANON-START-{uuid.uuid4()}'}, timeout=15)
    assert started.status_code == 201, started.text
    session_id = started.json()['session']['id']

    finished = anon.post(f'{BASE_URL}/api/kiosk-web/finish/{session_id}',
                         json={'good_qty': 5, 'defect_qty': 0,
                               'request_id': f'ANON-FINISH-{uuid.uuid4()}'}, timeout=15)
    assert finished.status_code == 200, finished.text

    assert anon.get(f'{BASE_URL}/api/kiosk-web/health', timeout=15).status_code == 200


def test_anonymous_kiosk_start_is_still_idempotent(seeded_factory):
    """Opening the surface must not cost the duplicate-submit protection.

    request_id idempotency lives in the repository, not in the auth layer, so
    a retry from an anonymous kiosk (flaky shop-floor Wi-Fi, operator double-
    tap) still returns the same session instead of opening a second one.
    """
    graph = seeded_factory
    anon = _anon()
    request_id = f'ANON-IDEM-{uuid.uuid4()}'
    body = {'employee_id': graph['employee_id'], 'operation_id': graph['operation_id'],
            'station_id': graph['station_id'], 'device_uuid': f"ANON-{graph['suffix']}",
            'request_id': request_id}

    first = anon.post(f'{BASE_URL}/api/kiosk-web/start', json=body, timeout=15)
    assert first.status_code == 201, first.text
    replay = anon.post(f'{BASE_URL}/api/kiosk-web/start', json=body, timeout=15)
    assert replay.status_code == 201, replay.text
    assert replay.json()['session']['id'] == first.json()['session']['id']


def test_opening_the_kiosk_did_not_open_the_admin_apis(seeded_factory):
    """The public boundary is the kiosk surface and nothing else.

    Same anonymous client that just ran a production session above must still
    be refused by every management API -- this is the regression that would
    turn a scoped kiosk fix into a full auth bypass.
    """
    anon = _anon()
    for path in ('/api/employees',
                 '/api/production-orders',
                 '/api/session-management/sessions',
                 '/api/session-exceptions',
                 '/api/templates',
                 '/api/kiosks',
                 '/api/users',
                 '/api/system/action-logs',
                 '/api/kiosk-board',
                 '/api/kiosk-board/activity',
                 '/api/kiosk-board/po-options'):
        response = anon.get(f'{BASE_URL}{path}', timeout=15)
        assert response.status_code in (401, 403), f'{path} is reachable anonymously: {response.text[:200]}'


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
        # ...and it can already work, because the kiosk surface is public
        # (2026-09-12). Enrollment is about binding a terminal to a station
        # and being able to CUT IT OFF later, not about unlocking the kiosk.
        unenrolled = requests.post(f'{BASE_URL}/api/kiosk-web/scan',
                                   json={'qr': f"WF|EMP|TEST-{graph['suffix']}"}, timeout=15)
        assert unenrolled.status_code == 200, unenrolled.text

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
        # The revoked token is refused rather than silently downgraded to the
        # anonymous public path -- otherwise revocation would be a no-op and
        # an admin would have no way to cut a specific terminal off at all.
        assert client.headers['X-Kiosk-Token'] == token
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_status WHERE device_uuid=%s', (device,))
            cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (device,))
