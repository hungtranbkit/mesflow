"""One shared scheduled_job_health
reporting helper, generalized from the pattern `mesflow.cli.run_predictive`
already used inline (report()/started_at/duration_ms/consecutive_failures).

Before this module, exception reconciliation ran INLINE inside the
`GET /api/exceptions` HTTP handler with zero scheduled_job_health reporting
at all -- an architecture bug (it only ever ran as a side effect of that
one GET request) compounded by a truthfulness bug: a job that has NEVER actually
run (via `mesflow.cli reconcile-exceptions`/a cron entry) still shows
whatever the seed migration wrote (`last_status='UNKNOWN'`,
`next_expected_at=NULL`), and system_health_service.py's old
`normalized_status` CASE treated that as "not bad" -- a job that's never
once executed showed up in an overall-HEALTHY JOBS card. See
mesflow.web.system_health / system_health_service.py's `_jobs()` for the
read-side fix (NEVER_RUN is now its own real status, not folded into
"whatever last_status already says").

Usage:
    with scheduled_job_run('exception_reconciliation'):
        ExceptionDetectionService().reconcile(correlation_id=...)

Marks RUNNING at entry (so a process that crashes mid-job, never reaching
the with-block's exit, leaves an honest 'RUNNING' row rather than a stale
'SUCCESS' from its last good run -- system_health_service.py's read side
additionally treats a RUNNING row that's far older than its own expected
interval+grace as MISSED/stuck, not perpetually "currently running").
Marks SUCCESS/FAILED on exit, always recomputing next_expected_at.

Deliberately UNGATED by MESFLOW_LEGACY_HEALTH_WRITER_ENABLED -- that flag
covers the 2026-08 "Deploy Agent is now authoritative for SYSTEM/
INFRASTRUCTURE monitoring" cutover (component_health_state/predictive/etc,
see that flag's own docstring in core/config.py). Exception/shift-session
reconciliation are business-domain jobs, not infrastructure metrics, and
were never part of that cutover decision -- their scheduled_job_health rows
must always be truthful, in every environment.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone

from mesflow.db.connection import execute


def _mark_running(job_name: str, started_at: datetime) -> None:
    execute(
        """UPDATE scheduled_job_health SET last_started_at=%s,last_status='RUNNING',updated_at=CURRENT_TIMESTAMP
           WHERE job_name=%s""",
        (started_at, job_name),
    )


def _mark_finished(job_name: str, started_at: datetime, status: str, duration_ms: int, error: str) -> None:
    execute(
        """UPDATE scheduled_job_health SET last_started_at=%s,last_finished_at=CURRENT_TIMESTAMP,
               last_status=%s,duration_ms=%s,last_error=%s,
               last_success_at=CASE WHEN %s='SUCCESS' THEN CURRENT_TIMESTAMP ELSE last_success_at END,
               consecutive_failures=CASE WHEN %s='SUCCESS' THEN 0 ELSE consecutive_failures+1 END,
               next_expected_at=CURRENT_TIMESTAMP+(GREATEST(COALESCE(expected_interval_seconds,60),1)||' seconds')::interval,
               updated_at=CURRENT_TIMESTAMP
           WHERE job_name=%s""",
        (started_at, status, duration_ms, error, status, status, job_name),
    )


@contextmanager
def scheduled_job_run(job_name: str):
    """Context manager: mark RUNNING, run the caller's body, mark SUCCESS on
    a clean exit or FAILED (with the exception's message) on any exception
    -- then RE-RAISES, so callers (a CLI command's own exit code, a cron
    job's non-zero exit) still see the failure; this only adds truthful
    reporting on top, it never swallows an error.
    """
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    _mark_running(job_name, started_at)
    try:
        yield
    except Exception as exc:
        _mark_finished(job_name, started_at, 'FAILED', int((time.monotonic() - t0) * 1000), f'{type(exc).__name__}: {exc}')
        raise
    else:
        _mark_finished(job_name, started_at, 'SUCCESS', int((time.monotonic() - t0) * 1000), '')
