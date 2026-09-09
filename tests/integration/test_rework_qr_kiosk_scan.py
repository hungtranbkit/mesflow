"""What the SỬA HÀNG operation's QR does, end to end.

The workbench is created as a real operation with a real code and QR
(`WF|OP|REWORK-<po_id>-<part_code>`), so before 2026-09-09 it behaved like any
other scannable step: the QR print screen offered it as an active label, and
scanning it at a kiosk opened an ordinary session (HTTP 201). That loop never
closed -- a session there credits nothing back to the source operation and
moves nothing in the queue, because the queue is keyed by SOURCE SESSION and a
scan of "SỬA HÀNG for this Part" says nothing about whose defects are being
repaired. Worse, once daily_sessions started listing rework sessions as
working time (4832a96), a quantity typed into such a session would have leaked
into the dashboard's "Sản lượng đạt".

So the workbench is now non-scannable and is not offered for printing; repairs
are recorded on the Hàng chờ sửa screen, which knows the source session. These
tests pin all of that down.
"""
import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _start(api, employee_id, operation_id, station_id):
    return api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'QR-START-{uuid.uuid4()}', 'employee_id': employee_id,
        'operation_id': operation_id, 'station_id': station_id, 'device_uuid': 'TEST-QR-KIOSK',
    }, timeout=10)


def _finish(api, session_id, good, defect=0, rework=0):
    return api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'QR-FINISH-{uuid.uuid4()}', 'good_qty': good,
        'defect_qty': defect, 'rework_qty': rework,
    }, timeout=10)


def _seed_pending(api, db, graph, good=92, defect=8, repaired=1):
    started = _start(api, graph['employee_id'], graph['operation_id'], graph['station_id'])
    assert started.status_code == 201, started.text
    session_id = started.json()['session']['id']
    assert _finish(api, session_id, good, defect).status_code == 200
    resolved = api.post(f'{BASE_URL}/api/rework/queue/{session_id}/resolve', json={
        'request_id': f'QR-RESOLVE-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'repaired_qty': repaired,
    }, timeout=15)
    assert resolved.status_code == 200, resolved.text
    rework_op = db.execute("""SELECT id,code,qr,name,status FROM operations
        WHERE production_order_id=%s AND is_rework_op""", (graph['po_id'],)).fetchone()
    assert rework_op is not None
    return session_id, rework_op


def test_rework_operation_gets_a_real_scannable_qr_per_po_and_part(api, db, seeded_factory):
    graph = seeded_factory
    _session_id, rework_op = _seed_pending(api, db, graph)

    part_code = db.execute('SELECT code FROM parts WHERE id=%s', (graph['part_id'],)).fetchone()['code']
    assert rework_op['name'] == 'SỬA HÀNG'
    assert rework_op['code'] == f"REWORK-{graph['po_id']}-{part_code}"
    assert rework_op['qr'] == f"WF|OP|{rework_op['code']}"

    # One workbench per (PO, Part), created lazily -- a second resolve reuses it.
    assert db.execute('SELECT COUNT(*) n FROM operations WHERE production_order_id=%s AND is_rework_op',
                      (graph['po_id'],)).fetchone()['n'] == 1

    # ...and it stays visible in the UNFILTERED catalogue (active_only=0), so a
    # label printed before the workbench was made non-scannable can still be
    # looked up -- flagged inactive, see the next test.
    labels = api.get(f'{BASE_URL}/api/qr-labels?type=OPERATION&active_only=0&limit=2000', timeout=15)
    assert labels.status_code == 200, labels.text
    listed = [x for x in labels.json()['items'] if x['code'] == rework_op['code']]
    assert listed, 'the SỬA HÀNG QR must be findable in the QR catalogue'
    assert listed[0]['qr_payload'] == rework_op['qr']
    assert listed[0]['active'] is False, 'listed for audit, but never as a scannable label'


def test_scanning_the_workbench_qr_at_a_kiosk_is_refused(api, db, seeded_factory):
    """Starting a bare session on the workbench cannot do repair accounting.

    The queue is keyed by SOURCE SESSION -- resolve() has to know whose defects
    are being repaired in order to credit the original operation and decrement
    that session's pending. A kiosk scan of "SỬA HÀNG" for a Part carries no
    such reference, so a session started this way could only ever record time
    against a workbench that has no target: the queue would not move, the
    source operation would get no credit, and (since daily_sessions now lists
    rework sessions as working time) any quantity typed in would leak into the
    dashboard's "Sản lượng đạt" without ever being real production.

    Refused with a message that points at the screen that CAN do it.
    """
    graph = seeded_factory
    source_session_id, rework_op = _seed_pending(api, db, graph)

    before = db.execute('SELECT done_qty,rework_qty FROM operations WHERE id=%s',
                        (graph['operation_id'],)).fetchone()
    queued_before = db.execute("""SELECT defect_qty-rework_qty-scrap_qty pending
        FROM work_sessions WHERE id=%s""", (source_session_id,)).fetchone()['pending']

    response = _start(api, graph['employee_id'], rework_op['id'], graph['station_id'])
    assert response.status_code == 409, f'expected refusal, got {response.status_code}: {response.text}'
    # Compare the decoded message: the JSON body escapes non-ASCII.
    assert 'Hàng chờ sửa' in response.json()['message']

    # Nothing moved: no session, no credit, queue untouched.
    assert db.execute('SELECT COUNT(*) n FROM work_sessions WHERE operation_id=%s AND status=%s',
                      (rework_op['id'], 'OPEN')).fetchone()['n'] == 0
    after = db.execute('SELECT done_qty,rework_qty FROM operations WHERE id=%s',
                       (graph['operation_id'],)).fetchone()
    assert (after['done_qty'], after['rework_qty']) == (before['done_qty'], before['rework_qty'])
    assert db.execute("""SELECT defect_qty-rework_qty-scrap_qty pending FROM work_sessions WHERE id=%s""",
                      (source_session_id,)).fetchone()['pending'] == queued_before


def test_workbench_qr_is_not_advertised_as_scannable(api, db, seeded_factory):
    """It must not be printed as a shop-floor label it cannot honour.

    active_only=1 is what the QR print screen uses by default, and its whole
    point (see qr_labels()) is "only list what the kiosk will actually accept".
    """
    graph = seeded_factory
    _session_id, rework_op = _seed_pending(api, db, graph)
    labels = api.get(f'{BASE_URL}/api/qr-labels?type=OPERATION&active_only=1&limit=2000', timeout=15)
    assert labels.status_code == 200, labels.text
    listed = [x for x in labels.json()['items'] if x['code'] == rework_op['code']]
    assert not listed, 'the workbench cannot be started from a kiosk, so it must not be offered for printing'
