"""Session Lifecycle Fix Plan Phase 13 (Observability): scheduled_job_health
needs a `last_success_at` that survives a SUBSEQUENT failure.

Without this column, "when did this job last actually succeed" can only be
derived as `last_finished_at WHERE last_status='SUCCESS'` -- which goes
blank/stale the moment a job fails once, even though the plan's own metric
list (Phase 13: `exception_reconcile_last_success`,
`shift_reconcile_last_success`) is explicitly about the last SUCCESS, not
the last attempt. `_mark_finished()` (core/scheduled_job.py) now sets this
column only on the SUCCESS branch, leaving it untouched on FAILED -- so a
run of failures after a real success still reports a truthful, non-null
"last known good" timestamp instead of going blank.
"""
from alembic import op

revision = '0041_job_health_last_success'
down_revision = '0040_shift_lifecycle_scheduler_health'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE scheduled_job_health ADD COLUMN last_success_at TIMESTAMPTZ")
    # Backfill: any row whose last recorded run already succeeded gets its
    # last_finished_at carried over as a best-effort last_success_at, so
    # existing (pre-column) SUCCESS rows don't regress to NULL/"never
    # succeeded" on upgrade.
    op.execute("UPDATE scheduled_job_health SET last_success_at=last_finished_at WHERE last_status='SUCCESS'")
    op.execute("UPDATE system_meta SET value='72.0.2.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("UPDATE system_meta SET value='72.0.1.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
    op.execute("ALTER TABLE scheduled_job_health DROP COLUMN IF EXISTS last_success_at")
