"""Regression coverage for MESFlow Production/Operation overview UI fix.

Bug: DashboardRepository.daily_progress()'s day_state CASE mapped
day_defect_qty > 0 directly to a state HAS_DEFECT, rendered by the
frontend as a red "Có lỗi" (error) badge. NG/defect quantity is normal
production data, not an actionable exception, and must never by itself
turn an Operation row red.

Fix: HAS_DEFECT was removed. day_state now describes operational/session
state only (RUNNING/NEEDS_REVIEW/UPDATED/IDLE), where NEEDS_REVIEW is
reserved for a real actionable exception -- an auto-closed session whose
quantity was never confirmed by a human (closed_by_system AND NOT
quantity_confirmed, the same columns/concept the Session Exceptions inbox
already uses for AUTO_CLOSED_UNCONFIRMED) -- reusing that signal rather
than re-deriving a second, duplicate exception rule.

These tests drive the real HTTP API (/api/dashboard/shift, which embeds
daily_progress() output as `items`) against a live Postgres, per the
project's established end-to-end verification pattern.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.postgres
HCM = ZoneInfo('Asia/Ho_Chi_Minh')
SHIFT_DATE = '2026-08-06'


def _shift_id(db, code='DAY'):
    return db.execute("SELECT id FROM work_shifts WHERE code=%s", (code,)).fetchone()['id']


def _insert_session(db, employee_id, operation_id, station_id, suffix, tag, status, start, end=None,
                     good_qty=1, defect_qty=0, closed_by_system=False, quantity_confirmed=True):
    row = db.execute(
        """INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,started_at,ended_at,
               good_qty,defect_qty,closed_by_system,quantity_confirmed,start_request_id,finish_request_id)
           VALUES(%s,%s,%s,'docker-e2e',%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (employee_id, operation_id, station_id, status, start, end, good_qty, defect_qty,
         closed_by_system, quantity_confirmed,
         f'start-{tag}-{suffix}', f'finish-{tag}-{suffix}' if end else None),
    ).fetchone()
    return row['id']


def _op_item(body, operation_id):
    match = [item for item in body['items'] if item['operation_id'] == operation_id]
    assert match, f'operation {operation_id} missing from /api/dashboard/shift items'
    return match[0]


def _fetch(api, shift_id):
    response = api.get(f'http://mesflow-test-api:8080/api/dashboard/shift?shift_date={SHIFT_DATE}&shift_id={shift_id}&limit=2000', timeout=10)
    assert response.status_code == 200, response.text
    return response.json()


def test_ng_quantity_alone_does_not_trigger_needs_review(db, api, seeded_factory):
    # Closed session with NG (defect_qty) > 0, nothing else abnormal:
    # normally closed by the worker, quantity confirmed. This alone must
    # never produce the warning state.
    g = seeded_factory
    day = _shift_id(db)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'ng-only',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 30, tzinfo=HCM),
                     good_qty=33, defect_qty=5, closed_by_system=False, quantity_confirmed=True)
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['day_state'] != 'NEEDS_REVIEW'
    assert item['day_state'] == 'UPDATED'
    # NG quantity itself must still be visible/reported, just not a status.
    assert item['day_defect_qty'] == 5
    assert item['day_good_qty'] == 33


def test_auto_closed_unconfirmed_session_still_produces_needs_review(db, api, seeded_factory):
    # A real actionable exception: the shift auto-close job ended the
    # session and nobody has confirmed the final quantities yet.
    g = seeded_factory
    day = _shift_id(db)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'unconfirmed',
                     'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 30, tzinfo=HCM),
                     good_qty=0, defect_qty=0, closed_by_system=True, quantity_confirmed=False)
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['day_state'] == 'NEEDS_REVIEW'


def test_running_operation_still_shows_running(db, api, seeded_factory):
    g = seeded_factory
    day = _shift_id(db)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'running',
                     'OPEN', datetime(2026, 8, 6, 9, 0, tzinfo=HCM))
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['day_state'] == 'RUNNING'


def test_running_operation_with_ng_on_a_prior_session_still_shows_running(db, api, seeded_factory):
    # NG on an earlier, already-closed-and-confirmed session must not
    # override or hide the fact that the Operation is currently running.
    g = seeded_factory
    day = _shift_id(db)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'ng-earlier',
                     'CLOSED', datetime(2026, 8, 6, 8, 0, tzinfo=HCM), datetime(2026, 8, 6, 8, 30, tzinfo=HCM),
                     good_qty=10, defect_qty=3, closed_by_system=False, quantity_confirmed=True)
    _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'still-running',
                     'OPEN', datetime(2026, 8, 6, 9, 0, tzinfo=HCM))
    item = _op_item(_fetch(api, day), g['operation_id'])
    assert item['day_state'] == 'RUNNING'
    assert item['day_defect_qty'] == 3


def test_needs_review_outranks_running_when_both_present(db, api, seeded_factory):
    # An unconfirmed auto-closed session is a real actionable exception and
    # must surface even if the same Operation also has someone running it
    # right now -- it must not be silently hidden behind RUNNING.
    g = seeded_factory
    day = _shift_id(db)
    second_id = db.execute(
        "INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
        (f'TEST-nr-{g["suffix"]}', 'Docker NeedsReview Worker', f'WF|EMP|TEST-nr-{g["suffix"]}'),
    ).fetchone()['id']
    second_session_id = None
    try:
        _insert_session(db, g['employee_id'], g['operation_id'], g['station_id'], g['suffix'], 'unconfirmed2',
                         'CLOSED', datetime(2026, 8, 6, 9, 0, tzinfo=HCM), datetime(2026, 8, 6, 9, 30, tzinfo=HCM),
                         good_qty=0, defect_qty=0, closed_by_system=True, quantity_confirmed=False)
        second_session_id = _insert_session(db, second_id, g['operation_id'], g['station_id'], g['suffix'], 'running2',
                                             'OPEN', datetime(2026, 8, 6, 10, 0, tzinfo=HCM))
        item = _op_item(_fetch(api, day), g['operation_id'])
        assert item['day_state'] == 'NEEDS_REVIEW'
        assert item['open_session_count'] == 1
    finally:
        if second_session_id is not None:
            db.execute("DELETE FROM work_sessions WHERE id=%s", (second_session_id,))
        db.execute("DELETE FROM employees WHERE id=%s", (second_id,))
