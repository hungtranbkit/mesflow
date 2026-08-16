"""V66: additive audit_logs columns for the transactional audit foundation
(actor_user_id, employee_id, correlation_id, before/after snapshot, source).
Existing rows and existing AuditRepository.log() call sites are unaffected --
every new column is nullable or has a default."""
from alembic import op

revision="0030_v66_audit_foundation"
down_revision="0029_kiosk_ota_fleet_safety"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("ALTER TABLE audit_logs ADD COLUMN actor_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE audit_logs ADD COLUMN employee_id BIGINT REFERENCES employees(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE audit_logs ADD COLUMN correlation_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE audit_logs ADD COLUMN before_json TEXT NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE audit_logs ADD COLUMN after_json TEXT NOT NULL DEFAULT '{}'")
    op.execute("ALTER TABLE audit_logs ADD COLUMN source TEXT NOT NULL DEFAULT ''")
    op.execute("CREATE INDEX idx_audit_logs_correlation ON audit_logs(correlation_id) WHERE correlation_id<>''")
    op.execute("UPDATE system_meta SET value='65.8.44.71',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_audit_logs_correlation")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS after_json")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS before_json")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS correlation_id")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS employee_id")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS actor_user_id")
