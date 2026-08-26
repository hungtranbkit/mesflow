"""Read-only production data audit.

Backs `mesflow audit-sessions` (cli.py). Never mutates anything -- every
query here is a plain SELECT. Meant to be run before/after a rollout
(inspect stale-record counts before flipping
MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=1) and periodically in production to spot
data-integrity drift early.
"""
from __future__ import annotations

from typing import Any

from mesflow.core.working_calendar import get_work_shifts, resolve_shift_window_for_datetime
from mesflow.db.connection import fetch_all


def _open_sessions() -> list[dict[str, Any]]:
    return fetch_all("""SELECT ws.id,ws.employee_id,e.employee_no,e.name employee_name,ws.operation_id,
        o.code operation_code,ws.started_at,
        EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - ws.started_at))/3600.0 open_hours
        FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id JOIN operations o ON o.id=ws.operation_id
        WHERE ws.status='OPEN' ORDER BY ws.started_at""")


def audit() -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        'OPEN': [], 'PAST_SHIFT_END': [], 'OPEN_OVER_12H': [], 'CROSS_DAY': [],
        'EMPLOYEE_OVERLAP': [], 'IMPOSSIBLE_DURATION': [], 'OFFLINE_TIME_MISMATCH': [],
        'ORPHAN_EMPLOYEE': [], 'ORPHAN_OPERATION': [], 'DUPLICATE_CLOSE_EVENT': [],
        'DUPLICATE_AUTO_CLOSE_EVENT': [],
    }

    import datetime as dt
    from mesflow.core.config import settings
    from mesflow.core.time_policy import site_zone
    now = dt.datetime.now(dt.timezone.utc)
    zone = site_zone(settings.timezone_name)

    open_rows = _open_sessions()
    shifts = get_work_shifts()  # fetched once -- see resolve_shift_window_for_datetime()'s own N+1 warning
    for row in open_rows:
        item = {k: v for k, v in row.items() if k != 'open_hours'}
        item['open_hours'] = round(float(row['open_hours']), 1)
        result['OPEN'].append(item)
        if row['open_hours'] >= 12:
            result['OPEN_OVER_12H'].append(item)
        # CROSS_DAY: still open, and its calendar date (site timezone)
        # differs from today's -- started on a previous day and never
        # closed, regardless of hour count.
        if row['started_at'].astimezone(zone).date() != now.astimezone(zone).date():
            result['CROSS_DAY'].append(item)
        window = resolve_shift_window_for_datetime(row['started_at'], shifts)
        if window is not None:
            _shift, _start, end = window
            if now >= end:
                result['PAST_SHIFT_END'].append({**item, 'shift_code': _shift['code'], 'shift_end_at': end.isoformat()})

    result['EMPLOYEE_OVERLAP'] = fetch_all("""
        SELECT a.id session_id_a, b.id session_id_b, a.employee_id, e.employee_no, e.name employee_name,
               a.started_at started_at_a, a.ended_at ended_at_a, b.started_at started_at_b, b.ended_at ended_at_b
        FROM work_sessions a JOIN work_sessions b ON b.employee_id=a.employee_id AND b.id>a.id
          JOIN employees e ON e.id=a.employee_id
        WHERE tstzrange(a.started_at,COALESCE(a.ended_at,'infinity'::timestamptz),'[)')
          && tstzrange(b.started_at,COALESCE(b.ended_at,'infinity'::timestamptz),'[)')
        ORDER BY a.employee_id,a.started_at""")

    result['IMPOSSIBLE_DURATION'] = fetch_all("""
        SELECT id,employee_id,operation_id,started_at,ended_at,status
        FROM work_sessions WHERE ended_at IS NOT NULL AND ended_at<started_at
        ORDER BY started_at""")

    # OFFLINE_TIME_MISMATCH: a kiosk_client_events row whose trusted device
    # event_time diverges materially (>15 min) from server_recorded_at
    # (processed_at) -- flags a device clock that's drifted far enough to
    # be worth a human's attention, independent of whether that divergence
    # was ever actually TRUSTED into a work_sessions timestamp (Phase 7).
    result['OFFLINE_TIME_MISMATCH'] = fetch_all("""
        SELECT client_event_id,kiosk_id,event_type,time_quality,event_time,processed_at,
               EXTRACT(EPOCH FROM (processed_at - event_time))/60.0 drift_minutes
        FROM kiosk_client_events
        WHERE time_quality='synced' AND event_time IS NOT NULL
          AND ABS(EXTRACT(EPOCH FROM (processed_at - event_time))) > 900
        ORDER BY processed_at DESC LIMIT 500""")

    # ORPHAN_EMPLOYEE / ORPHAN_OPERATION: work_sessions.employee_id/
    # operation_id both carry FK RESTRICT constraints, so under normal
    # operation these must always be empty -- kept as a cheap, explicit
    # LEFT JOIN...IS NULL safety net anyway, the standard way
    # to catch a referential-integrity break that bypassed the FK (a raw
    # psql DELETE during an incident, a constraint disabled mid-migration,
    # a partially-restored backup) rather than assuming it can't happen.
    result['ORPHAN_EMPLOYEE'] = fetch_all("""
        SELECT ws.id,ws.employee_id,ws.operation_id,ws.status,ws.started_at
        FROM work_sessions ws LEFT JOIN employees e ON e.id=ws.employee_id
        WHERE e.id IS NULL ORDER BY ws.id""")
    result['ORPHAN_OPERATION'] = fetch_all("""
        SELECT ws.id,ws.employee_id,ws.operation_id,ws.status,ws.started_at
        FROM work_sessions ws LEFT JOIN operations o ON o.id=ws.operation_id
        WHERE o.id IS NULL ORDER BY ws.id""")

    # DUPLICATE_CLOSE_EVENT / DUPLICATE_AUTO_CLOSE_EVENT: a session should
    # get exactly one SESSION_FINISHED (manual finish()) and/or exactly one
    # SESSION_AUTO_CLOSED (auto_close_for_shift_end()) production_trace_events
    # row -- finish_request_id's UNIQUE constraint and auto_close's
    # FOR UPDATE + status='OPEN' guard should make more than one of either
    # impossible, but this is exactly the kind of "manual finish raced
    # auto-close, both wrote a close event" bug Phase 9's own acceptance
    # criteria call out -- cheap to check directly rather than trust the
    # guards never regress.
    result['DUPLICATE_CLOSE_EVENT'] = fetch_all("""
        SELECT session_id,COUNT(*) close_event_count,array_agg(id ORDER BY id) event_ids
        FROM production_trace_events WHERE event_type='SESSION_FINISHED' AND session_id IS NOT NULL
        GROUP BY session_id HAVING COUNT(*)>1 ORDER BY session_id""")
    result['DUPLICATE_AUTO_CLOSE_EVENT'] = fetch_all("""
        SELECT session_id,COUNT(*) auto_close_event_count,array_agg(id ORDER BY id) event_ids
        FROM production_trace_events WHERE event_type='SESSION_AUTO_CLOSED' AND session_id IS NOT NULL
        GROUP BY session_id HAVING COUNT(*)>1 ORDER BY session_id""")

    return result
