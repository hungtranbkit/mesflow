"""Stale-session recovery.

WorkSessionRepository.auto_close_for_shift_end() (execution.py) closes ONE
session correctly and atomically. This module is the SCAN that finds which
OPEN sessions are past their shift's end boundary and drives that call for
each -- it does NOT depend on being invoked at the exact moment a shift
ends (Phase 3's own requirement: "Auto-close không được chỉ hoạt động nếu
process đang sống đúng khoảnh khắc shift_end"). A session left OPEN through
a multi-day server outage is found and closed at its REAL historical
shift-end boundary the next time this runs, not at "whenever the process
happened to come back up".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta
from typing import Any

from mesflow.core.config import settings
from mesflow.core.time_policy import business_date, business_datetime_utc, utc_now
from mesflow.core.working_calendar import get_work_shifts, resolve_shift_window_for_datetime
from mesflow.db.connection import fetch_all
from mesflow.db.repositories.execution import WorkSessionRepository


@dataclass(frozen=True)
class StaleSessionCandidate:
    session_id: int
    employee_id: int
    operation_id: int
    started_at: Any
    shift_code: str
    shift_end_at: Any
    minutes_past_end: float
    # 'SHIFT'   -- ranh giới là shift_end thật của ca session thuộc về
    # 'DAY_END' -- session bắt đầu trong khe NO_ACTIVE_SHIFT, không có ca
    #              nào để bám; ranh giới là 24:00 của ngày làm việc đó.
    boundary_kind: str = 'SHIFT'


class ShiftSessionReconciliationService:
    def __init__(self, repository: WorkSessionRepository | None = None):
        self.repository = repository or WorkSessionRepository()

    def find_candidates(self, now=None, grace_minutes: int | None = None) -> list[StaleSessionCandidate]:
        """Read-only: every OPEN session whose OWN resolved shift (the one
        active at its started_at, not "today's" shift) has already ended,
        past the grace window. Never mutates anything -- this is also what
        `mesflow audit-sessions`/the reconcile dry-run path reuses so the
        same detection logic backs both "tell me" and "do it".

        A session whose started_at falls in a NO_ACTIVE_SHIFT gap (Phase
        2/8: resolve_shift_window_for_datetime returns None) is skipped
        here -- there is no shift boundary to auto-close it against. It
        remains visible via the existing LONG_OPEN_SESSION exception
        (12h+) as a genuine anomaly instead.
        """
        now = now or utc_now()
        grace = timedelta(minutes=grace_minutes if grace_minutes is not None else settings.shift_auto_close_grace_minutes)
        rows = fetch_all("""SELECT id,employee_id,operation_id,started_at FROM work_sessions
            WHERE status='OPEN' ORDER BY started_at""")
        shifts = get_work_shifts()  # fetched ONCE -- see resolve_shift_window_for_datetime()'s own docstring (N+1-connections bug found live)
        candidates = []
        for row in rows:
            window = resolve_shift_window_for_datetime(row['started_at'], shifts)
            if window is None:
                # Khe NO_ACTIVE_SHIFT. Trước đây `continue` ở đây, tức
                # session loại này KHÔNG BAO GIỜ được đóng. Ranh giới xác
                # định được duy nhất còn lại là hết ngày làm việc mà nó bắt
                # đầu -- luôn > started_at, nên auto_close_for_shift_end()
                # không bao giờ bị từ chối vì ranh giới nằm trước giờ bắt đầu.
                if not settings.session_day_end_fallback_enabled:
                    continue
                end = self._day_end_boundary(row['started_at'])
                shift_code, boundary_kind = 'NO_ACTIVE_SHIFT', 'DAY_END'
            else:
                shift, _start, end = window
                shift_code, boundary_kind = shift['code'], 'SHIFT'
            if now < end + grace:
                continue
            candidates.append(StaleSessionCandidate(
                session_id=row['id'], employee_id=row['employee_id'], operation_id=row['operation_id'],
                started_at=row['started_at'], shift_code=shift_code, shift_end_at=end,
                minutes_past_end=(now - end).total_seconds() / 60,
                boundary_kind=boundary_kind,
            ))
        return candidates

    @staticmethod
    def _day_end_boundary(started_at):
        """24:00 của ngày làm việc (giờ địa phương) mà `started_at` rơi vào,
        trả về UTC. Deterministic: cùng một session luôn cho cùng một ranh
        giới, bất kể job chạy lúc nào -- điều kiện để cả vòng reconcile là
        idempotent (chạy lại không đổi ended_at)."""
        day = business_date(started_at, timezone_name=settings.timezone_name)
        return business_datetime_utc(day + timedelta(days=1), time.min, settings.timezone_name)

    def reconcile(self, now=None, dry_run: bool | None = None, correlation_id: str = '') -> list[dict[str, Any]]:
        """Drives auto_close_for_shift_end() for every candidate. dry_run
        defaults from settings (Phase 15 rollout switches) when not passed
        explicitly -- an explicit True/False (e.g. from `--dry-run` on the
        CLI, or `audit-sessions`) always wins over the environment default.

        Each candidate is handled independently: one session's failure
        (e.g. a genuine data conflict auto_close_for_shift_end() refuses)
        is recorded as 'FAILED' in that item's own result and does NOT
        abort the rest of the batch -- a batch job must make maximum
        forward progress, not let one bad row silently block every other
        legitimately-stale session behind it.
        """
        now = now or utc_now()
        if dry_run is None:
            dry_run = (not settings.shift_auto_close_enabled) or settings.shift_auto_close_dry_run
        results = []
        for candidate in self.find_candidates(now):
            item = {
                'session_id': candidate.session_id, 'employee_id': candidate.employee_id,
                'operation_id': candidate.operation_id, 'shift_code': candidate.shift_code,
                'started_at': candidate.started_at, 'shift_end_at': candidate.shift_end_at,
                'minutes_past_end': round(candidate.minutes_past_end, 1),
                'boundary_kind': candidate.boundary_kind,
            }
            if dry_run:
                results.append({**item, 'action': 'WOULD_CLOSE'})
                continue
            try:
                outcome = self.repository.auto_close_for_shift_end(
                    candidate.session_id, candidate.shift_end_at, correlation_id=correlation_id,
                    close_reason=('AUTO_DAY_END' if candidate.boundary_kind == 'DAY_END' else 'AUTO_SHIFT_END'))
                results.append({**item, 'action': 'CLOSED' if outcome else 'SKIPPED_ALREADY_CLOSED'})
            except Exception as exc:  # noqa: BLE001 -- one bad row must not abort the batch, see docstring
                results.append({**item, 'action': 'FAILED', 'error': f'{type(exc).__name__}: {exc}'})
        return results
