"""P0 2026-09-12: "Chờ sửa" on Tổng quan must be what the operator declared.

Reported symptom: the operator finished a session declaring 3 NG of which 2
were repairable -- "sản phẩm chờ sửa = 2" in their words -- and the Tổng quan
Operation row showed **1**.

The number on screen was `defect - rework - scrap`, which under the real,
write-side meaning of work_sessions.rework_qty ("Lỗi sửa được", declared
repairable -- see 0051_repair_pending_semantics.py) is the SCRAP remainder:
the exact complement of the answer. Every test here drives the REAL finish
path (WorkSessionRepository.finish, the same call the kiosk makes) rather than
UPDATE-ing operations.* by hand, because the bug lived in the gap between what
that path writes and what the rollups read -- a test that writes the columns
itself cannot see it.

The three screens must also agree, always: Tổng quan PO card, Tổng quan
Operation row, and Hàng chờ sửa are asserted against the same expected number
in every case below.
"""
import pytest

from mesflow.db.repositories.analytics import DashboardRepository
from mesflow.db.repositories.execution import WorkSessionRepository, SupervisorRepository
from mesflow.db.repositories.rework import ReworkQueueRepository


def _finish(graph, *, good, defect, repairable, tag):
    """Declare one session's output exactly as the kiosk finish screen does."""
    repo = WorkSessionRepository()
    started = repo.start({'employee_id': graph['employee_id'], 'operation_id': graph['operation_id'],
                          'station_id': graph['station_id'], 'request_id': f"rp-start-{tag}-{graph['suffix']}"})
    session_id = int(started['session']['id'])
    repo.finish(session_id, {'good_qty': good, 'defect_qty': defect, 'rework_qty': repairable,
                             'request_id': f"rp-finish-{tag}-{graph['suffix']}"})
    return session_id


def _screens(graph):
    """The three places a user can read "Chờ sửa". They must never disagree."""
    dashboard = DashboardRepository()
    po = next(r for r in dashboard.po_progress(500) if int(r['po_id']) == int(graph['po_id']))
    operation = next(r for r in dashboard.operation_overview(5000)
                     if int(r['operation_id']) == int(graph['operation_id']))
    queue = [r for r in ReworkQueueRepository().queue(5000)
             if int(r['source_operation_id']) == int(graph['operation_id'])]
    return po, operation, queue


def _assert_pending(graph, expected, *, scrap=None):
    po, operation, queue = _screens(graph)
    assert operation['repair_pending_quantity'] == expected, 'Tổng quan Operation "Chờ sửa"'
    assert po['repair_pending_quantity'] == expected, 'Tổng quan PO card "CẦN SỬA"'
    assert sum(int(r['pending_qty']) for r in queue) == expected, 'Hàng chờ sửa'
    # A row with nothing left to do must leave the queue entirely, not linger at 0.
    assert all(int(r['pending_qty']) > 0 for r in queue)
    if scrap is not None:
        assert po['scrap_quantity'] == scrap, 'Tổng quan PO card "Phế"'
    return po, operation, queue


def test_declared_two_shows_two(db, seeded_factory):
    """The reported case, exactly: 3 NG of which 2 repairable -> "Chờ sửa 2"."""
    g = seeded_factory
    _finish(g, good=7, defect=3, repairable=2, tag='a')
    # Before 0051 this asserted 1 -- the one piece declared UNrepairable.
    po, operation, _ = _assert_pending(g, 2, scrap=1)
    # ...and the buckets it is derived from are all separately visible, so a
    # future regression cannot hide behind a coincidentally-right total.
    assert (operation['defect_qty'], operation['rework_qty'],
            operation['repaired_qty'], operation['scrap_qty']) == (3, 2, 0, 1)
    assert (po['defect_quantity'], po['repairable_quantity'], po['repaired_quantity']) == (3, 2, 0)


def test_all_defects_repairable_leaves_nothing_in_scrap(db, seeded_factory):
    g = seeded_factory
    _finish(g, good=8, defect=2, repairable=2, tag='b')
    _assert_pending(g, 2, scrap=0)


def test_pending_zero_when_nothing_declared_repairable(db, seeded_factory):
    """Declaring 5 NG, none of them repairable, must queue NOTHING.

    Before 0051 this put all 5 into the repair queue and reported "Phế 0" --
    the same inversion seen from the other side.
    """
    g = seeded_factory
    _finish(g, good=5, defect=5, repairable=0, tag='c')
    _assert_pending(g, 0, scrap=5)


def test_pending_zero_when_no_defects_at_all(db, seeded_factory):
    g = seeded_factory
    _finish(g, good=10, defect=0, repairable=0, tag='d')
    _assert_pending(g, 0, scrap=0)


def test_multiple_sessions_sum_quantities_not_rows(db, seeded_factory):
    """Three sessions declaring 2+1+3 repairable must total 6, not 3 rows."""
    g = seeded_factory
    _finish(g, good=8, defect=2, repairable=2, tag='e1')
    _finish(g, good=9, defect=1, repairable=1, tag='e2')
    _finish(g, good=6, defect=4, repairable=3, tag='e3')
    _, _, queue = _assert_pending(g, 6, scrap=1)
    assert len(queue) == 3, 'three source sessions, but the total is a SUM of qty'


def test_partial_repair_decrements_pending(db, seeded_factory):
    """pending 2, repair 1 -> 1 left; the repaired piece becomes GOOD output."""
    g = seeded_factory
    session_id = _finish(g, good=8, defect=2, repairable=2, tag='f')
    _assert_pending(g, 2)

    ReworkQueueRepository().resolve(session_id, {
        'repaired_qty': 1, 'scrapped_qty': 0, 'employee_id': g['employee_id'],
        'request_id': f"rp-resolve-{g['suffix']}"})

    po, operation, _ = _assert_pending(g, 1, scrap=0)
    assert operation['repaired_qty'] == 1
    assert po['repaired_quantity'] == 1
    assert operation['done_qty'] == 9, 'the repaired piece is credited as good output'
    # The declaration itself is a historical fact and must not be rewritten by
    # a repair -- 0044 incremented it here, which is how a resolved item could
    # re-enter the queue.
    assert operation['rework_qty'] == 2


def test_partial_scrap_decrements_pending_and_books_scrap(db, seeded_factory):
    g = seeded_factory
    session_id = _finish(g, good=8, defect=2, repairable=2, tag='g')
    ReworkQueueRepository().resolve(session_id, {
        'repaired_qty': 0, 'scrapped_qty': 1, 'employee_id': g['employee_id'],
        'request_id': f"rp-scrap-{g['suffix']}"})
    po, operation, _ = _assert_pending(g, 1, scrap=1)
    assert operation['done_qty'] == 8, 'a scrapped piece is not good output'
    assert po['repaired_quantity'] == 0


def test_repair_and_scrap_together_empty_the_bucket(db, seeded_factory):
    g = seeded_factory
    session_id = _finish(g, good=5, defect=5, repairable=4, tag='h')
    ReworkQueueRepository().resolve(session_id, {
        'repaired_qty': 3, 'scrapped_qty': 1, 'employee_id': g['employee_id'],
        'request_id': f"rp-both-{g['suffix']}"})
    # 1 unrepairable at declaration + 1 written off at the bench = Phế 2.
    po, operation, queue = _assert_pending(g, 0, scrap=2)
    assert queue == [], 'a fully resolved session leaves the queue'
    assert (operation['done_qty'], operation['repaired_qty']) == (8, 3)


def test_resolving_more_than_pending_is_refused(db, seeded_factory):
    from mesflow.db.repositories.base import ConflictError
    g = seeded_factory
    session_id = _finish(g, good=8, defect=2, repairable=2, tag='i')
    with pytest.raises(ConflictError):
        ReworkQueueRepository().resolve(session_id, {
            'repaired_qty': 3, 'scrapped_qty': 0, 'employee_id': g['employee_id'],
            'request_id': f"rp-over-{g['suffix']}"})
    _assert_pending(g, 2)


def test_idempotent_finish_replay_does_not_double_count(db, seeded_factory):
    """A kiosk retry (same request_id) must not add a second 2 to the queue."""
    g = seeded_factory
    repo = WorkSessionRepository()
    started = repo.start({'employee_id': g['employee_id'], 'operation_id': g['operation_id'],
                          'station_id': g['station_id'], 'request_id': f"rp-idem-start-{g['suffix']}"})
    session_id = int(started['session']['id'])
    payload = {'good_qty': 8, 'defect_qty': 2, 'rework_qty': 2,
               'request_id': f"rp-idem-finish-{g['suffix']}"}
    repo.finish(session_id, dict(payload))
    _assert_pending(g, 2)
    repo.finish(session_id, dict(payload))
    _assert_pending(g, 2)


def test_idempotent_resolve_replay_does_not_double_credit(db, seeded_factory):
    g = seeded_factory
    session_id = _finish(g, good=6, defect=4, repairable=4, tag='k')
    payload = {'repaired_qty': 2, 'scrapped_qty': 0, 'employee_id': g['employee_id'],
               'request_id': f"rp-idem-resolve-{g['suffix']}"}
    ReworkQueueRepository().resolve(session_id, dict(payload))
    _assert_pending(g, 2)
    replay = ReworkQueueRepository().resolve(session_id, dict(payload))
    assert replay['idempotent_replay'] is True
    po, operation, _ = _assert_pending(g, 2)
    assert (operation['repaired_qty'], operation['done_qty']) == (2, 8)


def test_repeated_reads_are_stable(db, seeded_factory):
    """Reloading Tổng quan must not drift the number (no accumulating rollup)."""
    g = seeded_factory
    _finish(g, good=7, defect=3, repairable=2, tag='l')
    for _ in range(3):
        _assert_pending(g, 2, scrap=1)


def test_excluded_session_leaves_the_pending_bucket(db, seeded_factory):
    """excluded_from_reports=TRUE means "not real work" -- including its repairs."""
    g = seeded_factory
    session_id = _finish(g, good=7, defect=3, repairable=2, tag='m')
    _assert_pending(g, 2)
    with db.cursor() as cur:
        cur.execute('UPDATE work_sessions SET excluded_from_reports=TRUE WHERE id=%s', (session_id,))
    from mesflow.db.connection import transaction
    from mesflow.db.repositories.production_state import reconcile_operation_and_po
    with transaction() as conn:
        with conn.cursor() as cur:
            reconcile_operation_and_po(cur, int(g['operation_id']))
    _assert_pending(g, 0, scrap=0)


def test_cannot_edit_declaration_below_what_was_already_resolved(db, seeded_factory):
    """Guarded with a sentence, not a raw IntegrityError from 0051's CHECK.

    Owned by execution._guard_rework_ledger, which reads rework_ledger (the
    immutable record) rather than the session row, so pre-existing drift cannot
    talk its way past it. It is a Conflict, not a bad request: the numbers the
    supervisor typed are well-formed, they just contradict work already booked.
    """
    from mesflow.db.repositories.base import ConflictError
    g = seeded_factory
    session_id = _finish(g, good=6, defect=4, repairable=4, tag='n')
    ReworkQueueRepository().resolve(session_id, {
        'repaired_qty': 3, 'scrapped_qty': 0, 'employee_id': g['employee_id'],
        'request_id': f"rp-guard-{g['suffix']}"})
    with pytest.raises(ConflictError, match='Hàng chờ sửa'):
        SupervisorRepository().adjust(session_id, {
            'good_qty': 6, 'defect_qty': 4, 'rework_qty': 1,
            'reason': 'hạ khai báo sửa được xuống dưới số đã xử lý'}, None)
    _assert_pending(g, 1)
    # ...and the legitimate correction is still allowed: 3 repaired means the
    # declaration may come down to 3, just not below it.
    SupervisorRepository().adjust(session_id, {
        'good_qty': 6, 'defect_qty': 4, 'rework_qty': 3,
        'reason': 'đếm lại: chỉ 3 cái sửa được'}, None)
    _assert_pending(g, 0, scrap=1)
