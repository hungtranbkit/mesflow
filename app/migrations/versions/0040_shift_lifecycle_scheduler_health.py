"""Session Lifecycle Fix Plan: shift auto-close, scheduled_job_health
truthfulness, offline event trusted timestamps.

Adds the schema this task's own principle requires ("Auto-close phải là
một lifecycle riêng... không được vá nhanh bằng cách gọi
WorkSessionRepository.finish(...good_qty=0...)") -- an auto-closed session
must be DISTINGUISHABLE from a real operator finish, not just a FINISH with
zero quantities and no trace of who/what closed it.

- work_sessions: close_reason/closed_by_system/shift_boundary_used_at --
  see WorkSessionRepository.auto_close_for_shift_end()
  (app/mesflow/db/repositories/execution.py). Manual finish() leaves these
  at their defaults ('', FALSE, NULL); only the auto-close path sets them,
  so a query can always tell the two apart after the fact.
- kiosk_client_events: event_occurred_at/server_recorded_at split (Phase 7)
  -- the existing `event_time`/`processed_at` columns already carry this
  distinction at the ledger level; these are the WorkSessionRepository-
  facing names threaded through from OfflineSyncRepository once a trusted
  device timestamp is actually applied to started_at/ended_at, so a session
  row itself (not just its originating ledger entry) can show what time
  was trusted and when the server actually received it.
- scheduled_job_health: seeds a real row for shift_session_reconciliation
  (exception_reconciliation already exists from 0033) so Phase 6's
  NEVER_RUN/HEALTHY/RUNNING/MISSED/FAILED/DISABLED contract has something
  real to report against for both scheduled jobs this task adds/refits.
"""
from alembic import op

revision = '0040_shift_lifecycle_scheduler_health'
down_revision = '0039_kiosk_v2_protocol'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE work_sessions
        ADD COLUMN close_reason TEXT NOT NULL DEFAULT '',
        ADD COLUMN closed_by_system BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN shift_boundary_used_at TIMESTAMPTZ,
        ADD COLUMN started_at_trusted BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN ended_at_trusted BOOLEAN NOT NULL DEFAULT FALSE""")
    op.execute("CREATE INDEX idx_work_sessions_open_started ON work_sessions(started_at) WHERE status='OPEN'")

    # Advisory-lock namespace for the shift-session reconciliation job
    # (Phase 3: two concurrent runs must not double-close the same session).
    # No new table needed -- pg_advisory_xact_lock(hashtextextended(...)) on
    # a per-session key, same pattern lock_idempotency_key() already uses
    # for kiosk_idempotency (see production_state.py). Documented here so
    # the convention is discoverable from schema history, not just code.

    op.execute("""INSERT INTO scheduled_job_health(job_name,display_name,enabled,expected_interval_seconds,grace_seconds,last_status)
        VALUES ('shift_session_reconciliation','Đóng ca tự động (session quá giờ)',TRUE,60,120,'UNKNOWN')
        ON CONFLICT (job_name) DO NOTHING""")

    op.execute("UPDATE system_meta SET value='72.0.1.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("DELETE FROM scheduled_job_health WHERE job_name='shift_session_reconciliation'")
    op.execute("DROP INDEX IF EXISTS idx_work_sessions_open_started")
    op.execute("""ALTER TABLE work_sessions
        DROP COLUMN IF EXISTS close_reason,
        DROP COLUMN IF EXISTS closed_by_system,
        DROP COLUMN IF EXISTS shift_boundary_used_at,
        DROP COLUMN IF EXISTS started_at_trusted,
        DROP COLUMN IF EXISTS ended_at_trusted""")
