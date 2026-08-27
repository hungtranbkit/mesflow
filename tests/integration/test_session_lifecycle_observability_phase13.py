"""Session Lifecycle Fix Plan Phase 13 -- observability. Confirms the new
SESSION_LIFECYCLE system-health component reports the plan's minimal metric
set through the EXISTING system health API (no new endpoint), and that
scheduled_job_health.last_success_at (Phase 13's own small schema addition,
migration 0041) survives a subsequent FAILED run instead of going blank."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.postgres
BASE = 'http://mesflow-test-api:8080'


def test_session_lifecycle_component_reports_minimal_metric_set(db, super_admin_api, seeded_factory):
    g = seeded_factory
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,
                   closed_by_system,ended_at,start_request_id,finish_request_id)
               VALUES(%s,%s,%s,'CLOSED',%s,TRUE,%s,%s,%s)""",
            (g['employee_id'], g['operation_id'], g['station_id'],
             datetime.now(timezone.utc) - timedelta(hours=2), datetime.now(timezone.utc) - timedelta(hours=1),
             f'P13-S-{g["suffix"]}', f'P13-F-{g["suffix"]}'),
        )
    r = super_admin_api.get(f'{BASE}/api/system-health', timeout=10)
    assert r.status_code == 200, r.text
    by = {x['component']: x for x in r.json()['components']}
    assert 'SESSION_LIFECYCLE' in by
    details = by['SESSION_LIFECYCLE']['details']
    for key in (
        'open_sessions', 'past_shift_end_sessions', 'auto_closed_sessions_last_24h',
        'oldest_open_session_age_hours', 'exception_reconcile_last_success', 'shift_reconcile_last_success',
    ):
        assert key in details
    assert details['auto_closed_sessions_last_24h'] >= 1


def test_job_last_success_at_survives_a_later_failure(db):
    from mesflow.core.scheduled_job import scheduled_job_run

    job = f'p13-test-{uuid.uuid4()}'
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO scheduled_job_health(job_name,display_name,enabled,expected_interval_seconds,grace_seconds,last_status)
               VALUES(%s,%s,TRUE,60,60,'UNKNOWN')""",
            (job, job),
        )
    with scheduled_job_run(job):
        pass  # succeeds
    first = db.execute('SELECT last_success_at FROM scheduled_job_health WHERE job_name=%s', (job,)).fetchone()
    assert first['last_success_at'] is not None

    with pytest.raises(RuntimeError):
        with scheduled_job_run(job):
            raise RuntimeError('boom')
    second = db.execute(
        'SELECT last_success_at,last_status FROM scheduled_job_health WHERE job_name=%s', (job,)
    ).fetchone()
    assert second['last_status'] == 'FAILED'
    # last_success_at must NOT have been cleared/advanced by the failed run.
    assert second['last_success_at'] == first['last_success_at']

    with db.cursor() as cur:
        cur.execute('DELETE FROM scheduled_job_health WHERE job_name=%s', (job,))
