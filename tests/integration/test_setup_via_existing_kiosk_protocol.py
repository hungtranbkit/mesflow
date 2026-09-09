"""Setup máy, driven end to end over the kiosk protocol the ESP ALREADY speaks.

This is the file that has to hold, because it encodes the constraint the whole
design was rewritten around: the ESP terminal is fixed hardware with a small
screen and firmware that is expensive to change, so setup may not introduce a
new screen, a new event type, or a new branch in the device's state machine.

What a worker actually does, using nothing the device did not already do:

    SCAN card  ->  SCAN the SETUP label  ->  SCAN card  ->  QUANTITY_SUBMITTED
    (WAIT_OP)      (session starts)          (QUANTITY_INPUT)   (session closes)

Exactly the four steps of an ordinary Operation. The SETUP row is an ordinary
`operations` row with its own label; the backend is the only thing that knows
the session is a setup, and it is the backend that zeroes the quantities and
records that setup happened (WorkSessionRepository._finish_within).

Every request below goes to /api/kiosk/v2/events -- the real firmware endpoint,
byte-identical envelope -- so a pass here means a real device performs this flow
today, unmodified. Nothing in app/mesflow/web/kiosk_v2.py was changed for the
feature; if these tests ever need a change there, the design has broken its own
premise.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

TOKEN_PREFIX = 'TEST-SETUP-KIOSK-'
NOTE = "1. Lắp khuôn số 3\n2. Căn tâm theo dưỡng\n3. Chạy thử 2 sản phẩm"


def _device_id(suffix: str) -> str:
    return f'V2-SETUP-{suffix}'


@pytest.fixture
def setup_graph(db):
    """One PO / Part / production Operation / employee, plus a real ACTIVE
    kiosk identity so /events accepts this device the way it accepts a real
    one (see _authorize_kiosk_v2_device)."""
    suffix = datetime.now(timezone.utc).strftime('%H%M%S%f')
    with db.cursor() as cur:
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) "
                    "VALUES(%s,'TEST PRODUCT',100,'IN_PROGRESS') RETURNING id", (f'PO-SU-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Part setup') RETURNING id",
                    (po_id, f'PT-SU-{suffix}'))
        part_id = cur.fetchone()['id']
        cur.execute("INSERT INTO stations(code,name,workshop,production_line) "
                    "VALUES(%s,'Station setup','TEST','TEST') RETURNING id", (f'ST-SU-{suffix}',))
        station_id = cur.fetchone()['id']
        cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) "
                    "VALUES(%s,'Thợ setup','TEST','Worker',%s) RETURNING id",
                    (f'EMP-SU-{suffix}', f'WF|EMP|EMP-SU-{suffix}'))
        employee_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,%s,'Cắt laser','IN_PROGRESS',%s) RETURNING id""",
                    (po_id, part_id, f'OP01-{suffix}', f'WF|OP|OP01-{suffix}'))
        operation_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,status,token_hash,last_seen_at)
            VALUES(%s,'Kiosk setup test','ACTIVE',%s,CURRENT_TIMESTAMP)""",
                    (_device_id(suffix), hashlib.sha256(f'{TOKEN_PREFIX}{suffix}'.encode()).hexdigest()))
    graph = dict(suffix=suffix, po_id=po_id, part_id=part_id, station_id=station_id,
                 employee_id=employee_id, operation_id=operation_id,
                 employee_qr=f'WF|EMP|EMP-SU-{suffix}', operation_qr=f'WF|OP|OP01-{suffix}')
    yield graph
    with db.cursor() as cur:
        cur.execute('DELETE FROM kiosk_v2_events WHERE device_id=%s', (_device_id(suffix),))
        cur.execute('DELETE FROM kiosk_v2_projection WHERE device_id=%s', (_device_id(suffix),))
        cur.execute('DELETE FROM kiosk_identities WHERE device_uuid=%s', (_device_id(suffix),))
        cur.execute('DELETE FROM work_sessions WHERE employee_id=%s', (employee_id,))
        cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po_id,))
        cur.execute('DELETE FROM parts WHERE id=%s', (part_id,))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))
        cur.execute('DELETE FROM stations WHERE id=%s', (station_id,))
        cur.execute('DELETE FROM employees WHERE id=%s', (employee_id,))


def _send(graph, event_type, payload):
    """One event, in the exact envelope docs/PROTOCOL.md specifies."""
    device = _device_id(graph['suffix'])
    body = {
        'protocol_version': 1,
        'device': {'device_id': device, 'hardware_id': device},
        'event': {'event_id': uuid.uuid4().hex, 'type': event_type, 'device_seq': 1},
        'context': {},
        'payload': payload,
    }
    response = requests.post(f'{BASE_URL}/api/kiosk/v2/events', json=body,
                             headers={'X-Kiosk-Token': f"{TOKEN_PREFIX}{graph['suffix']}"}, timeout=15)
    assert response.status_code == 200, response.text
    return response.json()


def _configure_setup(api, operation_id, minutes=15):
    response = api.put(f'{BASE_URL}/api/operations/{operation_id}/setup',
                       json={'requires_setup': True, 'expected_setup_minutes': minutes,
                             'setup_note': NOTE}, timeout=15)
    assert response.status_code == 200, response.text
    read = api.get(f'{BASE_URL}/api/operations/{operation_id}/setup', timeout=15)
    assert read.status_code == 200, read.text
    state = read.json()
    assert state.get('setup'), state
    return state['setup']


def test_setup_label_is_its_own_scannable_operation(api, setup_graph):
    """The label a worker looks for: Part-qualified text, id-based payload."""
    setup = _configure_setup(api, setup_graph['operation_id'])
    suffix = setup_graph['suffix']
    # Deterministic, derived from the parent -- not a random code to look up.
    assert setup['code'] == f'OP01-{suffix}-SU'
    # Printed text names the Part, because a bare code repeats across Parts.
    assert setup['display_key'] == f'PT-SU-{suffix}-OP01-{suffix}-SU'
    # Payload addresses the immutable row id, which a code can no longer do.
    assert setup['qr'] == f"WF|OPID|{setup['id']}"


def test_production_starts_even_when_the_linked_setup_never_ran(api, setup_graph):
    """Setup is related work, not a gate — proved over the real device protocol.

    The predecessor of this test asserted the opposite: that scanning the
    production label was refused with a 409 naming the SETUP label. That rule
    was removed on 2026-09-09.
    """
    _configure_setup(api, setup_graph['operation_id'])
    assert _send(setup_graph, 'SCAN', {'raw': setup_graph['employee_qr']})['state']['name'] == 'WAIT_OPERATION'

    accepted = _send(setup_graph, 'SCAN', {'raw': setup_graph['operation_qr']})
    assert accepted['accepted'] is True, accepted
    assert accepted['state']['name'] == 'WAIT_EMPLOYEE', accepted


def test_full_setup_then_production_over_the_unmodified_protocol(api, db, setup_graph):
    """The mandatory end-to-end flow, using only SCAN and QUANTITY_SUBMITTED."""
    setup = _configure_setup(api, setup_graph['operation_id'])

    # 1. Card, then the SETUP label -- an ordinary session start.
    _send(setup_graph, 'SCAN', {'raw': setup_graph['employee_qr']})
    started = _send(setup_graph, 'SCAN', {'raw': setup['qr']})
    assert started['accepted'] is True, started
    opened = db.execute("""SELECT id,operation_id,status FROM work_sessions
        WHERE employee_id=%s AND status='OPEN'""", (setup_graph['employee_id'],)).fetchone()
    assert opened['operation_id'] == setup['id']

    # 2. Card again -> the SAME quantity screen every operation finishes on.
    back = _send(setup_graph, 'SCAN', {'raw': setup_graph['employee_qr']})
    assert back['state']['name'] == 'QUANTITY_INPUT'

    # 3. Submit. A setup produces nothing, so 0 is what an operator types.
    done = _send(setup_graph, 'QUANTITY_SUBMITTED',
                 {'quantity_good': 0, 'quantity_defect': 0, 'quantity_rework': 0})
    assert done['accepted'] is True, done
    assert done['state']['name'] == 'WAIT_EMPLOYEE'

    # The setup is recorded as history and left no production data behind.
    main = db.execute("""SELECT setup_completed_at,setup_completed_session_id,done_qty,defect_qty
        FROM operations WHERE id=%s""", (setup_graph['operation_id'],)).fetchone()
    assert main['setup_completed_at'] is not None, 'when setup last ran is worth keeping'
    assert main['setup_completed_session_id'] == opened['id']
    assert (main['done_qty'], main['defect_qty']) == (0, 0)
    assert api.get(f"{BASE_URL}/api/operations/{setup_graph['operation_id']}/setup",
                   timeout=15).json()['state'] == 'DONE'

    # 4. Production starts, exactly as it would have before the setup ran.
    _send(setup_graph, 'SCAN', {'raw': setup_graph['employee_qr']})
    produce = _send(setup_graph, 'SCAN', {'raw': setup_graph['operation_qr']})
    assert produce['accepted'] is True, produce
    assert db.execute("""SELECT operation_id FROM work_sessions
        WHERE employee_id=%s AND status='OPEN'""",
        (setup_graph['employee_id'],)).fetchone()['operation_id'] == setup_graph['operation_id']


def test_a_number_typed_on_the_keypad_never_becomes_production(api, db, setup_graph):
    """The keypad cannot be removed from the device, so it must be harmless.

    An operator who taps a digit out of habit must not invent 7 good pieces on
    an Operation that made none. The backend discards the figure rather than
    rejecting the submit: a rejection on a fixed terminal with one error line
    would just strand them.
    """
    setup = _configure_setup(api, setup_graph['operation_id'])
    _send(setup_graph, 'SCAN', {'raw': setup_graph['employee_qr']})
    _send(setup_graph, 'SCAN', {'raw': setup['qr']})
    _send(setup_graph, 'SCAN', {'raw': setup_graph['employee_qr']})
    accepted = _send(setup_graph, 'QUANTITY_SUBMITTED',
                     {'quantity_good': 7, 'quantity_defect': 3, 'quantity_rework': 1})
    assert accepted['accepted'] is True, accepted

    session = db.execute("""SELECT good_qty,defect_qty,rework_qty,status FROM work_sessions
        WHERE operation_id=%s ORDER BY id DESC LIMIT 1""", (setup['id'],)).fetchone()
    assert (session['good_qty'], session['defect_qty'], session['rework_qty']) == (0, 0, 0)
    assert session['status'] == 'CLOSED'
    setup_row = db.execute('SELECT done_qty,defect_qty FROM operations WHERE id=%s',
                           (setup['id'],)).fetchone()
    assert (setup_row['done_qty'], setup_row['defect_qty']) == (0, 0)
    # ...and the setup is still recorded as having happened.
    assert db.execute('SELECT setup_completed_at FROM operations WHERE id=%s',
                      (setup_graph['operation_id'],)).fetchone()['setup_completed_at'] is not None


def test_a_new_operation_has_no_linked_setup_by_default(api, db, setup_graph):
    """An Operation nobody configured stays a plain production step."""
    state = api.get(f"{BASE_URL}/api/operations/{setup_graph['operation_id']}/setup",
                    timeout=15).json()
    assert state['setup'] is None
    assert state['state'] == 'NONE'
    assert state['has_setup'] is False
    assert db.execute("""SELECT COUNT(*) n FROM operations
        WHERE parent_operation_id=%s AND operation_type='SETUP'""",
        (setup_graph['operation_id'],)).fetchone()['n'] == 0

    _send(setup_graph, 'SCAN', {'raw': setup_graph['employee_qr']})
    assert _send(setup_graph, 'SCAN', {'raw': setup_graph['operation_qr']})['accepted'] is True


def test_setup_label_is_printable_from_the_qr_catalogue(api, setup_graph):
    """A label nobody can print is a label nobody can scan."""
    setup = _configure_setup(api, setup_graph['operation_id'])
    catalogue = api.get(f"{BASE_URL}/api/qr-labels?type=OPERATION&limit=3000"
                        f"&production_order_id={setup_graph['po_id']}", timeout=20)
    assert catalogue.status_code == 200, catalogue.text
    rows = {row['code']: row for row in catalogue.json()['items']}
    assert setup['display_key'] in rows, 'the SETUP label must be printable'
    row = rows[setup['display_key']]
    assert row['qr_payload'] == setup['qr']
    assert row['active'] is True, 'it is startable, so it must not be greyed out'
    assert 'Setup máy' in row['detail']
