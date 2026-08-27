"""Session Management upgrade: quantity confirmation + reporting exclusion.

Two additive, non-destructive columns on work_sessions -- same style as
0040_shift_lifecycle_scheduler_health.py's close_reason/closed_by_system
(a new fact recorded going forward, every existing row keeps its current
meaning unchanged):

- quantity_confirmed BOOLEAN NOT NULL DEFAULT TRUE: work_sessions.good_qty/
  defect_qty are NOT NULL (server_default '0') and changing that would touch
  every read site that already defensively COALESCE()s them -- a real
  schema-break risk for no real gain. Instead, this column carries the
  "0 = confirmed vs never-entered" distinction the task asks for:
  auto_close_for_shift_end() is the ONLY place that ever sets it FALSE (a
  human never confirmed the final numbers for that close), and any
  admin/supervisor correction (SupervisorRepository.adjust()/edit_session())
  sets it back TRUE (their action IS the confirmation). Defaulting existing
  rows to TRUE is correct: every session that exists today either came from
  a real operator finish or an admin correction, both genuinely confirmed.

- excluded_from_reports/exclusion_reason/excluded_by/excluded_at: "Loai
  khoi bao cao" (spec section 7). A session stays in history/audit forever
  (no delete); reconcile_operation() and ReportRepository.employee_
  performance() are updated to skip excluded_from_reports=TRUE rows so
  time/quantity/KPI/progress never counts them, without touching the
  session's own OPEN/CLOSED status.
"""
from alembic import op

revision = '0042_session_review_and_exclusion'
down_revision = '0041_job_health_last_success'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE work_sessions
        ADD COLUMN quantity_confirmed BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN excluded_from_reports BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN exclusion_reason TEXT NOT NULL DEFAULT '',
        ADD COLUMN excluded_by TEXT NOT NULL DEFAULT '',
        ADD COLUMN excluded_at TIMESTAMPTZ""")
    op.execute("CREATE INDEX idx_work_sessions_unconfirmed ON work_sessions(closed_by_system) "
               "WHERE status='CLOSED' AND NOT quantity_confirmed")
    op.execute("CREATE INDEX idx_work_sessions_excluded ON work_sessions(excluded_from_reports) "
               "WHERE excluded_from_reports")
    op.execute("UPDATE system_meta SET value='72.0.3.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("UPDATE system_meta SET value='72.0.2.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
    op.execute("DROP INDEX IF EXISTS idx_work_sessions_excluded")
    op.execute("DROP INDEX IF EXISTS idx_work_sessions_unconfirmed")
    op.execute("""ALTER TABLE work_sessions
        DROP COLUMN IF EXISTS quantity_confirmed,
        DROP COLUMN IF EXISTS excluded_from_reports,
        DROP COLUMN IF EXISTS exclusion_reason,
        DROP COLUMN IF EXISTS excluded_by,
        DROP COLUMN IF EXISTS excluded_at""")
