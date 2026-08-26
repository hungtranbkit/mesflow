"""Session Lifecycle Fix Plan Phase 2/3/5/12 -- shift auto-close lifecycle,
stale-session recovery, and race safety, against real PostgreSQL.

Uses the ACTUAL seeded work_shifts config (DAY 08:00-17:00, NIGHT
18:00-00:00, Asia/Ho_Chi_Minh, both cross_midnight=FALSE -- confirmed via
`SELECT * FROM work_shifts`), not the compiled-in DEFAULT_SHIFTS fallback,
so these tests fail loudly if a real deployment's shift config ever
diverges from what this suite assumes.
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from mesflow.core.working_calendar import resolve_shift_window_for_datetime
from mesflow.db.repositories.execution import WorkSessionRepository
from mesflow.db.repositories.exceptions import ExceptionRepository
from mesflow.services.exception_service import ExceptionDetectionService
from mesflow.services.shift_session_service import ShiftSessionReconciliationService

pytestmark = pytest.mark.postgres

HCM = ZoneInfo('Asia/Ho_Chi_Minh')


def _open_session(db, g, started_at: datetime, request_id: str) -> int:
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,start_request_id)
               VALUES(%s,%s,%s,'OPEN',%s,%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], started_at, request_id),
        )
        return cur.fetchone()['id']


def _row(db, session_id: int):
    with db.cursor() as cur:
        cur.execute('SELECT * FROM work_sessions WHERE id=%s', (session_id,))
        return cur.fetchone()


def test_day_shift_auto_close_at_exact_boundary(db, seeded_factory):
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)  # DAY: 08:00-17:00
    sid = _open_session(db, g, started_at, f'DAY-AC-{g["suffix"]}')
    window = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))
    assert window is not None and window[0]['code'] == 'DAY'
    shift_end = window[2]
    assert shift_end.astimezone(HCM).time().isoformat(timespec='minutes') == '17:00'

    result = WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-day')
    assert result is not None and result['ok'] is True
    row = _row(db, sid)
    assert row['status'] == 'CLOSED'
    assert row['ended_at'] == shift_end
    assert row['close_reason'] == 'AUTO_SHIFT_END'
    assert row['closed_by_system'] is True
    assert row['good_qty'] == 0 and row['defect_qty'] == 0 and row['rework_qty'] == 0


def test_night_shift_auto_close_at_exact_boundary(db, seeded_factory):
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 23, 30, tzinfo=HCM)  # NIGHT: 18:00-00:00
    sid = _open_session(db, g, started_at, f'NIGHT-AC-{g["suffix"]}')
    window = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))
    assert window is not None and window[0]['code'] == 'NIGHT'
    shift_end = window[2]
    assert shift_end.astimezone(HCM) == datetime(2026, 8, 11, 0, 0, tzinfo=HCM)

    result = WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-night')
    assert result is not None
    row = _row(db, sid)
    assert row['status'] == 'CLOSED' and row['close_reason'] == 'AUTO_SHIFT_END'


def test_restart_recovery_closes_at_real_historical_boundary_not_now(db, seeded_factory):
    """Phase 3's own worked example: session started during a shift, server
    down through the boundary and long after -- when the reconciliation
    scan finally runs, ended_at must be the REAL shift end, never "now"."""
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)  # DAY, ends 17:00 same day
    sid = _open_session(db, g, started_at, f'RESTART-{g["suffix"]}')
    simulated_now = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)  # ~2 days "later"

    results = ShiftSessionReconciliationService().reconcile(now=simulated_now, dry_run=False, correlation_id='test-restart')
    matching = [r for r in results if r['session_id'] == sid]
    assert len(matching) == 1 and matching[0]['action'] == 'CLOSED'

    row = _row(db, sid)
    assert row['status'] == 'CLOSED'
    assert row['ended_at'] == datetime(2026, 8, 10, 17, 0, tzinfo=HCM).astimezone(timezone.utc)
    assert row['ended_at'] < simulated_now - timedelta(hours=1)  # sanity: genuinely NOT "now"


def test_multi_day_stale_session_closes_at_first_valid_boundary_after_start(db, seeded_factory):
    """A session left open across MULTIPLE days must close at the first
    shift boundary after its own start, not some later one -- the scan
    resolves the shift for started_at itself, never "today"."""
    g = seeded_factory
    started_at = datetime(2026, 8, 8, 9, 0, tzinfo=HCM)  # DAY 2026-08-08, ends 17:00 same day
    sid = _open_session(db, g, started_at, f'MULTIDAY-{g["suffix"]}')
    simulated_now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)  # 2 days later

    results = ShiftSessionReconciliationService().reconcile(now=simulated_now, dry_run=False, correlation_id='test-multiday')
    matching = [r for r in results if r['session_id'] == sid]
    assert len(matching) == 1 and matching[0]['action'] == 'CLOSED'
    row = _row(db, sid)
    assert row['ended_at'].astimezone(HCM).date() == date(2026, 8, 8)
    assert row['ended_at'].astimezone(HCM).time().isoformat(timespec='minutes') == '17:00'


def test_employee_can_start_new_session_next_day_after_reconciliation(db, api, seeded_factory):
    """A stale session must not permanently block the SAME employee from
    starting a new one, once reconciliation has run -- the
    uq_open_session_per_employee constraint means this would otherwise
    wedge the employee out until a human manually intervened."""
    from datetime import date as _date
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'NEXTDAY-{g["suffix"]}')
    ShiftSessionReconciliationService().reconcile(
        now=datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc), dry_run=False, correlation_id='test-nextday')
    assert _row(db, sid)['status'] == 'CLOSED'

    out = WorkSessionRepository().start({
        'request_id': f'NEXTDAY-START-{g["suffix"]}',
        'employee_id': g['employee_id'], 'operation_id': g['operation_id'],
        'station_id': g['station_id'], 'device_uuid': 'test-runner',
    })
    assert out['ok'] is True
    assert out['session']['status'] == 'OPEN'


def test_operation_not_force_completed_by_auto_close_with_insufficient_quantity(db, seeded_factory):
    """Auto-close must never fabricate quantity -- an operation whose
    planned_quantity far exceeds what was ever recorded must NOT flip to
    COMPLETED just because its only session got auto-closed."""
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'OPSTATE-{g["suffix"]}')
    window = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))
    WorkSessionRepository().auto_close_for_shift_end(sid, window[2], correlation_id='test-opstate')
    with db.cursor() as cur:
        cur.execute('SELECT status,done_qty FROM operations WHERE id=%s', (g['operation_id'],))
        op = cur.fetchone()
    assert op['done_qty'] == 0
    assert op['status'] != 'COMPLETED'


def test_concurrent_auto_close_exactly_one_effect_no_duplicate_quantity(db, seeded_factory):
    """Two 'reconciliation runs' racing on the SAME session (Phase 3's own
    requirement) must produce exactly one close and zero duplicate
    quantity_movements rows -- the advisory xact lock in
    auto_close_for_shift_end() serializes this."""
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'RACE-{g["suffix"]}')
    window = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))
    shift_end = window[2]

    results = []
    errors = []

    def close_it():
        try:
            results.append(WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-race'))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=close_it) for _ in range(5)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=30)

    assert not errors, f'unexpected errors: {errors}'
    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1, f'expected exactly one real close, got {len(non_none)} of {len(results)}'
    row = _row(db, sid)
    assert row['status'] == 'CLOSED'
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM quantity_movements WHERE session_id=%s', (sid,))
        # good/defect/rework are all 0->0 (no change) -- record_quantities()
        # skips zero-delta movements entirely, so this must be 0, not just
        # "not duplicated".
        assert cur.fetchone()['n'] == 0


def test_session_past_shift_end_exception_detected_and_auto_resolved_after_close(db, seeded_factory):
    """Phase 5: SESSION_PAST_SHIFT_END must appear well before the 12h
    LONG_OPEN_SESSION threshold, and must auto-resolve (no human opening
    the Exception Center) once the session is actually closed -- reusing
    ExceptionRepository's existing condition_active/AUTO_IGNORED machinery,
    same as LONG_OPEN_SESSION already does.

    started_at is "2 days ago at 10:00 Asia/Ho_Chi_Minh" (real wall-clock-
    relative, not a frozen fixture date, so the test is robust regardless
    of when the suite actually runs) -- deliberately inside the DAY shift's
    08:00-17:00 window rather than an arbitrary hour offset, since the
    CURRENT shift config has a genuine 00:00-08:00 NO_ACTIVE_SHIFT gap
    (found while writing this very test: an earlier "now - 25h" version
    could land there and correctly get skipped by design, an unrelated
    false failure -- see resolve_shift_window_for_datetime()'s own
    NO_ACTIVE_SHIFT contract). 2 days back safely clears both the grace
    window and the 12h LONG_OPEN_SESSION threshold at any real "now".
    """
    g = seeded_factory
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).astimezone(HCM).date()
    started_at = datetime(two_days_ago.year, two_days_ago.month, two_days_ago.day, 10, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'PASTSHIFT-{g["suffix"]}')

    conditions = ExceptionRepository().detected_conditions()
    matching = [c for c in conditions if c['session_id'] == sid and c['exception_type'] == 'SESSION_PAST_SHIFT_END']
    assert len(matching) == 1, f'expected SESSION_PAST_SHIFT_END for session {sid}, got types: {[c["exception_type"] for c in conditions if c["session_id"] == sid]}'

    created = ExceptionDetectionService().reconcile('test-past-shift-end')
    exception_id = next(c['id'] for c in created if c['session_id'] == sid and c['exception_type'] == 'SESSION_PAST_SHIFT_END')
    with db.cursor() as cur:
        cur.execute("SELECT status FROM exception_records WHERE id=%s", (exception_id,))
        assert cur.fetchone()['status'] == 'OPEN'

    window = resolve_shift_window_for_datetime(started_at)
    assert window is not None
    WorkSessionRepository().auto_close_for_shift_end(sid, window[2], correlation_id='test-past-shift-end-close')

    ExceptionDetectionService().reconcile('test-past-shift-end-resolve')
    with db.cursor() as cur:
        cur.execute("SELECT status,auto_ignore_reason FROM exception_records WHERE id=%s", (exception_id,))
        row = cur.fetchone()
    assert row['status'] == 'AUTO_IGNORED'
    assert row['auto_ignore_reason'] == 'SESSION_ALREADY_CLOSED'


def test_manual_finish_vs_auto_close_race_exactly_one_effect(db, seeded_factory):
    """A real operator finishing the session at the same moment the
    reconciliation scan tries to auto-close it -- exactly one of the two
    must win (whichever gets the row lock first), the other must be a
    clean no-op (auto_close returns None / finish() sees a non-OPEN
    session), never a double-close or a corrupted row."""
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'MANUALRACE-{g["suffix"]}')
    window = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))
    shift_end = window[2]

    outcomes = {}

    def do_auto_close():
        try:
            outcomes['auto'] = WorkSessionRepository().auto_close_for_shift_end(sid, shift_end, correlation_id='test-mrace-auto')
        except Exception as exc:  # noqa: BLE001
            outcomes['auto_error'] = exc

    def do_manual_finish():
        try:
            outcomes['manual'] = WorkSessionRepository().finish(sid, {
                'request_id': f'MANUALRACE-FINISH-{g["suffix"]}', 'good_qty': 7, 'defect_qty': 0, 'rework_qty': 0,
            })
        except Exception as exc:  # noqa: BLE001
            outcomes['manual_error'] = exc

    t1 = threading.Thread(target=do_auto_close)
    t2 = threading.Thread(target=do_manual_finish)
    t1.start(); t2.start()
    t1.join(timeout=30); t2.join(timeout=30)

    row = _row(db, sid)
    assert row['status'] == 'CLOSED'
    # Exactly one real effect: either the manual finish's good_qty=7 stuck
    # (auto-close saw it already non-OPEN and no-op'd), or the auto-close
    # won first and the manual finish's own ConflictError('session already
    # closed') is the recorded outcome -- either is a correct, safe
    # resolution; what must NEVER happen is BOTH claiming success with
    # conflicting facts, or a corrupted intermediate state.
    if row['close_reason'] == 'AUTO_SHIFT_END':
        assert row['good_qty'] == 0
        assert 'manual_error' in outcomes
    else:
        assert row['good_qty'] == 7
        assert outcomes.get('auto') is None
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) n FROM work_sessions WHERE id=%s AND status=\'CLOSED\'', (sid,))
        assert cur.fetchone()['n'] == 1
