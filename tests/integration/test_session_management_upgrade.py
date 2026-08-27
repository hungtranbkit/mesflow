"""Session Management upgrade (spec sections 2/4/6/7/9/10): quantity
confirmation on auto-close, the AUTO_CLOSED_UNCONFIRMED review-queue entry,
dedicated Operation transfer, and reporting exclusion/restore -- against
real PostgreSQL, same fixtures/conventions as
test_shift_session_lifecycle.py and test_session_exception_workflow.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from mesflow.core.working_calendar import resolve_shift_window_for_datetime
from mesflow.db.repositories.execution import SupervisorRepository, WorkSessionRepository
from mesflow.db.repositories.analytics import ReportRepository
from mesflow.db.repositories.base import ConflictError
from mesflow.db.repositories.production_state import reconcile_operation_and_po

pytestmark = pytest.mark.postgres

HCM = ZoneInfo('Asia/Ho_Chi_Minh')


def _open_session(db, g, started_at: datetime, request_id: str, good=0, defect=0) -> int:
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,good_qty,defect_qty,start_request_id)
               VALUES(%s,%s,%s,'OPEN',%s,%s,%s,%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], started_at, good, defect, request_id),
        )
        return cur.fetchone()['id']


def _closed_session(db, g, started_at: datetime, request_id: str, good=0, defect=0) -> int:
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
               VALUES(%s,%s,%s,'CLOSED',%s,%s,%s,%s,%s,%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], started_at, started_at + timedelta(hours=1),
             good, defect, request_id, request_id + '-fin'),
        )
        return cur.fetchone()['id']


def _row(db, session_id: int):
    with db.cursor() as cur:
        cur.execute('SELECT * FROM work_sessions WHERE id=%s', (session_id,))
        return cur.fetchone()


def _operation_row(db, operation_id: int):
    with db.cursor() as cur:
        cur.execute('SELECT * FROM operations WHERE id=%s', (operation_id,))
        return cur.fetchone()


@pytest.fixture()
def sibling_operation(db, seeded_factory):
    """A second Operation in the SAME Part/PO as seeded_factory's own
    operation -- the common, unrestricted Operation-transfer case."""
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,%s,'Sibling Operation','IN_PROGRESS',%s) RETURNING id""",
            (g['po_id'], g['part_id'], f'TEST-OP-SIB-{g["suffix"]}', f'WF|OP|TEST-OP-SIB-{g["suffix"]}'))
        op_id = cur.fetchone()['id']
    yield op_id
    with db.cursor() as cur:
        # A test may have transferred a session onto this operation (that's
        # the whole point of the fixture) -- clear the FK reference before
        # dropping the row, same cleanup order seeded_factory's own teardown
        # already relies on.
        cur.execute('DELETE FROM operation_adjustments WHERE operation_id=%s', (op_id,))
        cur.execute('DELETE FROM work_sessions WHERE operation_id=%s', (op_id,))
        cur.execute('DELETE FROM operations WHERE id=%s', (op_id,))


@pytest.fixture()
def cross_part_operation(db, seeded_factory):
    """A second Part (and Operation) under the SAME PO -- exercises the
    cross-Part confirmation gate (spec section 6)."""
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Cross Part') RETURNING id",
                    (g['po_id'], f'TEST-PART-X-{g["suffix"]}'))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,%s,'Cross Part Operation','IN_PROGRESS',%s) RETURNING id""",
            (g['po_id'], part_id, f'TEST-OP-XP-{g["suffix"]}', f'WF|OP|TEST-OP-XP-{g["suffix"]}'))
        op_id = cur.fetchone()['id']
    yield op_id
    with db.cursor() as cur:
        cur.execute('DELETE FROM operation_adjustments WHERE operation_id=%s', (op_id,))
        cur.execute('DELETE FROM work_sessions WHERE operation_id=%s', (op_id,))
        cur.execute('DELETE FROM operations WHERE id=%s', (op_id,))
        cur.execute('DELETE FROM parts WHERE id=%s', (part_id,))


@pytest.fixture()
def cross_po_operation(db, seeded_factory):
    """A second Production Order/Part/Operation entirely -- exercises the
    admin-only cross-PO transfer gate (spec section 6)."""
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'X PRODUCT',50,'IN_PROGRESS') RETURNING id",
                    (f'TEST-PO-X-{g["suffix"]}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'X Part') RETURNING id",
                    (po_id, f'TEST-PART-XPO-{g["suffix"]}'))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,%s,'Other PO Operation','IN_PROGRESS',%s) RETURNING id""",
            (po_id, part_id, f'TEST-OP-XPO-{g["suffix"]}', f'WF|OP|TEST-OP-XPO-{g["suffix"]}'))
        op_id = cur.fetchone()['id']
    yield op_id
    with db.cursor() as cur:
        cur.execute('DELETE FROM operation_adjustments WHERE operation_id=%s', (op_id,))
        cur.execute('DELETE FROM work_sessions WHERE operation_id=%s', (op_id,))
        cur.execute('DELETE FROM operations WHERE id=%s', (op_id,))
        cur.execute('DELETE FROM parts WHERE id=%s', (part_id,))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))


# ---- quantity_confirmed (spec section 2/4) ----

def test_auto_close_marks_quantity_unconfirmed(db, seeded_factory):
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'AC-UNCONF-{g["suffix"]}')
    window = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))
    shift_end = window[2]
    result = WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-unconf')
    assert result is not None
    row = _row(db, sid)
    assert row['closed_by_system'] is True
    assert row['quantity_confirmed'] is False


def test_admin_adjust_reconfirms_quantity(db, seeded_factory):
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'AC-ADJ-{g["suffix"]}')
    shift_end = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))[2]
    WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-adj')
    assert _row(db, sid)['quantity_confirmed'] is False
    SupervisorRepository().adjust(sid, {'good_qty': 20, 'defect_qty': 1, 'reason': 'Bổ sung số liệu thực tế'}, user_id=None)
    row = _row(db, sid)
    assert row['quantity_confirmed'] is True
    assert row['good_qty'] == 20 and row['defect_qty'] == 1


def test_edit_session_reconfirms_quantity(db, seeded_factory):
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'AC-EDIT-{g["suffix"]}')
    shift_end = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))[2]
    WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-edit')
    row = _row(db, sid)
    SupervisorRepository().edit_session(sid, {
        'good_qty': 15, 'defect_qty': 0, 'started_at': row['started_at'].isoformat(),
        'ended_at': row['ended_at'].isoformat(), 'reason': 'Nhập số liệu thật',
    }, user_id=None)
    assert _row(db, sid)['quantity_confirmed'] is True


def test_auto_closed_unconfirmed_session_surfaces_in_inbox_then_clears_after_correction(db, seeded_factory):
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'AC-INBOX-{g["suffix"]}')
    shift_end = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))[2]
    WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-inbox')

    inbox = ReportRepository().session_exceptions(employee_id=g['employee_id'], limit=200)
    item = next(row for row in inbox if row['session_id'] == sid and row['exception_code'] == 'AUTO_CLOSED_UNCONFIRMED')
    assert item['classification'] == 'ACTION_REQUIRED'
    assert item['human_decision_required'] is True

    SupervisorRepository().adjust(sid, {'good_qty': 10, 'defect_qty': 0, 'reason': 'Đã kiểm tra và nhập số liệu'}, user_id=None)
    inbox_after = ReportRepository().session_exceptions(employee_id=g['employee_id'], limit=200)
    matching = [row for row in inbox_after if row['session_id'] == sid and row['exception_code'] == 'AUTO_CLOSED_UNCONFIRMED']
    assert not matching, 'must leave the default Inbox once corrected (condition no longer true)'


def test_normal_manual_close_never_enters_the_review_queue(db, seeded_factory):
    """spec section 19: a normal session must never bother the admin."""
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
            VALUES(%s,%s,%s,'CLOSED',%s,%s,5,0,%s,%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], datetime(2026, 8, 10, 8, 0, tzinfo=HCM),
             datetime(2026, 8, 10, 9, 0, tzinfo=HCM), f'NORMAL-START-{g["suffix"]}', f'NORMAL-END-{g["suffix"]}'))
        sid = cur.fetchone()['id']
    inbox = ReportRepository().session_exceptions(employee_id=g['employee_id'], limit=200)
    assert not [row for row in inbox if row['session_id'] == sid]


# ---- Operation transfer (spec section 6) ----

def test_transfer_operation_same_part_recomputes_progress(db, seeded_factory, sibling_operation):
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
            VALUES(%s,%s,%s,'CLOSED',%s,%s,7,1,%s,%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], datetime(2026, 8, 10, 8, 0, tzinfo=HCM),
             datetime(2026, 8, 10, 9, 0, tzinfo=HCM), f'XFER-START-{g["suffix"]}', f'XFER-END-{g["suffix"]}'))
        sid = cur.fetchone()['id']

    result = SupervisorRepository().transfer_operation(sid, {
        'operation_id': sibling_operation, 'reason': 'Giao nhầm Operation',
    }, user_id=None, actor_role='supervisor')
    assert result['item']['operation_id'] == sibling_operation
    assert _row(db, sid)['operation_id'] == sibling_operation
    assert _row(db, sid)['quantity_confirmed'] is True

    old_op = _operation_row(db, g['operation_id'])
    new_op = _operation_row(db, sibling_operation)
    assert int(old_op['done_qty']) == 0 and int(old_op['defect_qty']) == 0, 'source Operation must no longer count this session'
    assert int(new_op['done_qty']) == 7 and int(new_op['defect_qty']) == 1, 'target Operation must now count it'


def test_transfer_operation_requires_a_reason(db, seeded_factory, sibling_operation):
    g = seeded_factory
    sid = _open_session(db, g, datetime(2026, 8, 10, 8, 0, tzinfo=HCM), f'XFER-NOREASON-{g["suffix"]}')
    with pytest.raises(ValueError):
        SupervisorRepository().transfer_operation(sid, {'operation_id': sibling_operation}, user_id=None, actor_role='supervisor')


def test_transfer_operation_cross_part_blocked_then_allowed_with_confirmation(db, seeded_factory, cross_part_operation):
    g = seeded_factory
    sid = _open_session(db, g, datetime(2026, 8, 10, 8, 0, tzinfo=HCM), f'XFER-XPART-{g["suffix"]}')
    with pytest.raises(ConflictError, match='Part khác'):
        SupervisorRepository().transfer_operation(sid, {
            'operation_id': cross_part_operation, 'reason': 'Thử chuyển khác Part',
        }, user_id=None, actor_role='supervisor')
    # Explicit confirmation unblocks it -- never silent.
    result = SupervisorRepository().transfer_operation(sid, {
        'operation_id': cross_part_operation, 'reason': 'Thử chuyển khác Part', 'confirm_cross_part': True,
    }, user_id=None, actor_role='supervisor')
    assert result['item']['operation_id'] == cross_part_operation


def test_transfer_operation_cross_po_blocked_for_non_admin_allowed_for_admin(db, seeded_factory, cross_po_operation):
    g = seeded_factory
    # CLOSED, not OPEN -- uq_open_session_per_employee allows only one OPEN
    # session per employee at a time, and this test needs two independent
    # sessions to exercise both the blocked and the allowed path.
    sid_a = _closed_session(db, g, datetime(2026, 8, 10, 8, 0, tzinfo=HCM), f'XFER-XPO-A-{g["suffix"]}')
    with pytest.raises(ConflictError, match='PO khác'):
        SupervisorRepository().transfer_operation(sid_a, {
            'operation_id': cross_po_operation, 'reason': 'Thử chuyển khác PO', 'confirm_cross_part': True,
        }, user_id=None, actor_role='supervisor')
    sid_b = _closed_session(db, g, datetime(2026, 8, 10, 8, 0, tzinfo=HCM), f'XFER-XPO-B-{g["suffix"]}')
    result = SupervisorRepository().transfer_operation(sid_b, {
        'operation_id': cross_po_operation, 'reason': 'Thử chuyển khác PO admin', 'confirm_cross_part': True,
    }, user_id=None, actor_role='admin')
    assert result['item']['operation_id'] == cross_po_operation


def test_transfer_operation_rejects_cancelled_target(db, seeded_factory, sibling_operation):
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute("UPDATE operations SET status='CANCELLED' WHERE id=%s", (sibling_operation,))
    sid = _open_session(db, g, datetime(2026, 8, 10, 8, 0, tzinfo=HCM), f'XFER-CANCELLED-{g["suffix"]}')
    with pytest.raises(ConflictError, match='CANCELLED'):
        SupervisorRepository().transfer_operation(sid, {
            'operation_id': sibling_operation, 'reason': 'Thử chuyển vào Operation đã hủy',
        }, user_id=None, actor_role='supervisor')


# ---- Exclude / restore from reporting (spec section 7) ----

def test_exclude_session_removes_it_from_operation_progress_and_restore_brings_it_back(db, seeded_factory):
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
            VALUES(%s,%s,%s,'CLOSED',%s,%s,9,2,%s,%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], datetime(2026, 8, 10, 8, 0, tzinfo=HCM),
             datetime(2026, 8, 10, 9, 0, tzinfo=HCM), f'EXCL-START-{g["suffix"]}', f'EXCL-END-{g["suffix"]}'))
        sid = cur.fetchone()['id']
        # A raw INSERT (bypassing finish()/adjust(), which always reconcile
        # as part of the same transaction) doesn't update operations.done_qty
        # by itself -- reconcile once here to establish the real baseline
        # exclude_session() is expected to change.
        reconcile_operation_and_po(cur, g['operation_id'])
    before = _operation_row(db, g['operation_id'])
    assert int(before['done_qty']) == 9 and int(before['defect_qty']) == 2

    SupervisorRepository().exclude_session(sid, {'reason': 'Dữ liệu test'}, user_id=None, actor_username='tester')
    row = _row(db, sid)
    assert row['excluded_from_reports'] is True and row['exclusion_reason'] == 'Dữ liệu test'
    assert row['status'] == 'CLOSED', 'exclude must never touch OPEN/CLOSED lifecycle status'
    after_exclude = _operation_row(db, g['operation_id'])
    assert int(after_exclude['done_qty']) == 0 and int(after_exclude['defect_qty']) == 0

    SupervisorRepository().restore_session(sid, {'reason': 'Loại nhầm, đây là Session thật'}, user_id=None, actor_username='tester')
    row_restored = _row(db, sid)
    assert row_restored['excluded_from_reports'] is False
    after_restore = _operation_row(db, g['operation_id'])
    assert int(after_restore['done_qty']) == 9 and int(after_restore['defect_qty']) == 2


def test_exclude_requires_a_reason_and_is_not_double_appliable(db, seeded_factory):
    g = seeded_factory
    sid = _open_session(db, g, datetime(2026, 8, 10, 8, 0, tzinfo=HCM), f'EXCL-NOREASON-{g["suffix"]}')
    with pytest.raises(ValueError):
        SupervisorRepository().exclude_session(sid, {}, user_id=None, actor_username='tester')
    SupervisorRepository().exclude_session(sid, {'reason': 'Duplicate'}, user_id=None, actor_username='tester')
    with pytest.raises(ConflictError):
        SupervisorRepository().exclude_session(sid, {'reason': 'Duplicate'}, user_id=None, actor_username='tester')


def test_restore_requires_current_session_to_be_excluded(db, seeded_factory):
    g = seeded_factory
    sid = _open_session(db, g, datetime(2026, 8, 10, 8, 0, tzinfo=HCM), f'RESTORE-NOTEXCL-{g["suffix"]}')
    with pytest.raises(ConflictError):
        SupervisorRepository().restore_session(sid, {'reason': 'không cần'}, user_id=None, actor_username='tester')


def test_excluded_session_never_appears_in_the_review_inbox(db, seeded_factory):
    """spec section 7 UI badge + section 19: an excluded session is a
    finished decision, not new manager work waiting in the Inbox."""
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'EXCL-INBOX-{g["suffix"]}')
    shift_end = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))[2]
    WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-excl-inbox')
    assert [row for row in ReportRepository().session_exceptions(employee_id=g['employee_id'], limit=200)
            if row['session_id'] == sid], 'sanity: must be in the inbox before exclude'
    SupervisorRepository().exclude_session(sid, {'reason': 'Dữ liệu test'}, user_id=None, actor_username='tester')
    inbox_after = ReportRepository().session_exceptions(employee_id=g['employee_id'], limit=200)
    assert not [row for row in inbox_after if row['session_id'] == sid]
    all_rows = ReportRepository().session_exceptions(employee_id=g['employee_id'], limit=200, session_id=sid)
    assert any(row['classification'] == 'EXCLUDED' for row in all_rows)
