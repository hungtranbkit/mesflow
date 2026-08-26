"""Shared multi-employee kiosk fix (2026-08-26) -- regression coverage for
POST /api/kiosk/v2/events end-to-end. Before this fix, a successful OP scan
(session START) left the device's kiosk_v2_projection row parked in
SESSION_ACTIVE for whichever employee started it -- any OTHER employee
scanning their own card on the SAME shared kiosk hit SESSION_EMPLOYEE_MISMATCH
regardless of their own session status, because the kiosk's UI state was
conflated with one employee's server session state. See
app/mesflow/web/kiosk_v2.py's _apply_event() SCAN block for the fix itself.

Real, notable gap this file also closes: before this task, ZERO tests
exercised /api/kiosk/v2/events end-to-end at all (confirmed by grep across
tests/) -- every existing kiosk_v2 test either drove WorkSessionRepository
directly or seeded kiosk_v2_projection rows by hand. This is the first
integration coverage of the actual SCAN/START/FINISH state machine a real
device drives.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _device_id(suffix: str) -> str:
    return f'V2-SHARED-{suffix}'


@pytest.fixture
def three_employee_graph(db):
    """One PO, three operations (so three independent sessions can be open
    at once without tripping each other's dependency-chain checks), three
    employees. Mirrors conftest.seeded_factory's shape, just x3."""
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f')
    ids = {'employees': [], 'operations': []}
    with db.cursor() as cur:
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) "
                   "VALUES(%s,'TEST PRODUCT',100,'IN_PROGRESS') RETURNING id", (f'TEST-PO-SHARED-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Docker Test Part') RETURNING id",
                    (po_id, f'TEST-PART-SHARED-{suffix}'))
        part_id = cur.fetchone()['id']
        cur.execute("INSERT INTO stations(code,name,workshop,production_line) "
                   "VALUES(%s,'Docker Test Station','TEST','TEST') RETURNING id", (f'TEST-ST-SHARED-{suffix}',))
        station_id = cur.fetchone()['id']
        for label in ('A', 'B', 'C'):
            cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) "
                       "VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                        (f'TEST-SHARED-{label}-{suffix}', f'Docker Test Worker {label}',
                         f'WF|EMP|TEST-SHARED-{label}-{suffix}'))
            ids['employees'].append(cur.fetchone()['id'])
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                          VALUES(%s,%s,%s,%s,'IN_PROGRESS',%s) RETURNING id""",
                        (po_id, part_id, f'TEST-OP-SHARED-{label}-{suffix}', f'Docker Test Operation {label}',
                         f'WF|OP|TEST-OP-SHARED-{label}-{suffix}'))
            ids['operations'].append(cur.fetchone()['id'])
    ids['po_id'] = po_id
    ids['part_id'] = part_id
    ids['station_id'] = station_id
    ids['suffix'] = suffix
    yield ids
    with db.cursor() as cur:
        emp_ids = tuple(ids['employees'])
        cur.execute("DELETE FROM kiosk_v2_events WHERE device_id=%s", (_device_id(suffix),))
        cur.execute("DELETE FROM kiosk_v2_projection WHERE device_id=%s", (_device_id(suffix),))
        cur.execute("DELETE FROM work_sessions WHERE employee_id = ANY(%s)", (list(emp_ids),))
        cur.execute("DELETE FROM operations WHERE id = ANY(%s)", (ids['operations'],))
        cur.execute("DELETE FROM parts WHERE id=%s", (part_id,))
        cur.execute("DELETE FROM production_orders WHERE id=%s", (po_id,))
        cur.execute("DELETE FROM stations WHERE id=%s", (station_id,))
        cur.execute("DELETE FROM employees WHERE id = ANY(%s)", (list(emp_ids),))


def _event(device_id: str, event_type: str, payload: dict, expected_state_version: int | None = None) -> dict:
    body = {
        'protocol_version': 1,
        'device': {'device_id': device_id, 'hardware_id': device_id},
        'event': {'event_id': uuid.uuid4().hex, 'type': event_type, 'device_seq': 1},
        'context': {},
        'payload': payload,
    }
    if expected_state_version is not None:
        body['context']['expected_state_version'] = expected_state_version
    return body


def _send(device_id, event_type, payload, expected_state_version=None):
    body = _event(device_id, event_type, payload, expected_state_version)
    r = requests.post(f'{BASE_URL}/api/kiosk/v2/events', json=body, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()


def _scan_emp_qr(g, label):
    idx = {'A': 0, 'B': 1, 'C': 2}[label]
    return f"WF|EMP|TEST-SHARED-{label}-{g['suffix']}"


def _scan_op_qr(g, label):
    idx = {'A': 0, 'B': 1, 'C': 2}[label]
    return f"WF|OP|TEST-OP-SHARED-{label}-{g['suffix']}"


def test_employee_scan_with_no_active_session_goes_to_wait_operation(db, three_employee_graph):
    g = three_employee_graph
    device = _device_id(g['suffix'])
    resp = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'A')})
    assert resp['accepted'] is True
    assert resp['state']['name'] == 'WAIT_OPERATION'
    assert resp['view']['employee_name'] == 'Docker Test Worker A'


def test_full_shared_terminal_multi_user_scenario(db, three_employee_graph):
    """The exact mandatory E2E scenario from the shared-terminal fix task:
    A starts, B starts, C starts, kiosk returns READY (WAIT_EMPLOYEE) after
    each -- no user ever blocks another -- then A and B each return and
    finish independently, while C's session stays untouched throughout."""
    g = three_employee_graph
    device = _device_id(g['suffix'])

    # A scans -> WAIT_OPERATION(A) -> starts OP1 -> kiosk back to READY.
    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'A')})
    assert r['state']['name'] == 'WAIT_OPERATION'
    r = _send(device, 'SCAN', {'raw': _scan_op_qr(g, 'A')})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'WAIT_EMPLOYEE', 'kiosk must return to READY right after a successful START'
    assert r['view'] == {}, 'no leftover employee/operation context after a successful START'

    # B scans immediately -- must NOT inherit A's context, must NOT be
    # blocked by A's still-open session.
    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'B')})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'WAIT_OPERATION'
    assert r['view']['employee_name'] == 'Docker Test Worker B'
    r = _send(device, 'SCAN', {'raw': _scan_op_qr(g, 'B')})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'WAIT_EMPLOYEE'

    # C scans immediately -- same guarantee.
    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'C')})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'WAIT_OPERATION'
    assert r['view']['employee_name'] == 'Docker Test Worker C'
    r = _send(device, 'SCAN', {'raw': _scan_op_qr(g, 'C')})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'WAIT_EMPLOYEE'

    # A's and B's sessions are both genuinely still OPEN server-side right
    # now, simultaneously, while the kiosk itself sits idle -- the whole
    # point of the fix.
    with db.cursor() as cur:
        cur.execute('SELECT employee_id, status FROM work_sessions WHERE employee_id = ANY(%s)',
                   (g['employees'],))
        rows = {row['employee_id']: row['status'] for row in cur.fetchall()}
    assert rows[g['employees'][0]] == 'OPEN'  # A
    assert rows[g['employees'][1]] == 'OPEN'  # B
    assert rows[g['employees'][2]] == 'OPEN'  # C

    # A returns: server finds A's OPEN OP-A session, kiosk shows it fresh
    # (not a hangover -- this row didn't exist on the device between A's
    # START and now, it just went through B and C).
    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'A')})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'SESSION_ACTIVE'
    assert r['view']['employee_name'] == 'Docker Test Worker A'
    assert r['view']['operation_code'] == f"TEST-OP-SHARED-A-{g['suffix']}"
    # B's context must not have leaked into what A now sees.
    assert 'Worker B' not in r['view']['employee_name']

    # A scans again to confirm finish -> QUANTITY_INPUT -> submits -> READY.
    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'A')})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'QUANTITY_INPUT'
    r = _send(device, 'QUANTITY_SUBMITTED', {'quantity_good': 10, 'quantity_defect': 0, 'quantity_rework': 0})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'WAIT_EMPLOYEE'

    with db.cursor() as cur:
        cur.execute('SELECT status, good_qty FROM work_sessions WHERE employee_id=%s', (g['employees'][0],))
        row = cur.fetchone()
    assert row['status'] == 'CLOSED'
    assert row['good_qty'] == 10

    # B returns while C's session is still open and untouched -- server
    # finds B's OPEN OP-B session, not A's (now closed) or C's.
    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'B')})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'SESSION_ACTIVE'
    assert r['view']['operation_code'] == f"TEST-OP-SHARED-B-{g['suffix']}"
    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'B')})
    r = _send(device, 'QUANTITY_SUBMITTED', {'quantity_good': 5, 'quantity_defect': 1, 'quantity_rework': 0})
    assert r['accepted'] is True, r
    assert r['state']['name'] == 'WAIT_EMPLOYEE'

    # C's session was never touched by any of A's or B's traffic on this
    # same shared device.
    with db.cursor() as cur:
        cur.execute('SELECT status FROM work_sessions WHERE employee_id=%s', (g['employees'][2],))
        assert cur.fetchone()['status'] == 'OPEN'


def test_employee_b_scan_does_not_get_blocked_by_employee_a_open_session(db, three_employee_graph):
    """The exact old bug, isolated: A starts a session and the kiosk is
    immediately handed to B -- B must resolve their OWN state, never
    SESSION_EMPLOYEE_MISMATCH, and never see any of A's data."""
    g = three_employee_graph
    device = _device_id(g['suffix'])

    _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'A')})
    r = _send(device, 'SCAN', {'raw': _scan_op_qr(g, 'A')})
    assert r['state']['name'] == 'WAIT_EMPLOYEE'

    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'B')})
    assert r['accepted'] is True
    assert r.get('error') is None
    assert r['state']['name'] == 'WAIT_OPERATION'
    assert r['view']['employee_name'] == 'Docker Test Worker B'
    assert 'Worker A' not in r['view'].get('employee_name', '')


def test_response_never_contains_previous_users_temporary_state(db, three_employee_graph):
    """A's WAIT_OPERATION selection (employee scanned, no operation yet) is
    abandoned when B scans instead -- B's response must be a clean slate,
    not a mix of A's and B's data."""
    g = three_employee_graph
    device = _device_id(g['suffix'])

    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'A')})
    assert r['state']['name'] == 'WAIT_OPERATION'

    r = _send(device, 'SCAN', {'raw': _scan_emp_qr(g, 'B')})
    assert r['accepted'] is True
    assert r['view']['employee_name'] == 'Docker Test Worker B'
    assert r['view'].get('operation_code', '') == ''
    assert r['state']['name'] == 'WAIT_OPERATION'
