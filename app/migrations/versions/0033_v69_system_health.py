"""V69 System Health transitions and job state."""
from alembic import op
revision='0033_v69_system_health';down_revision='0032_v68_production_trace';branch_labels=None;depends_on=None
def upgrade():
 op.execute("CREATE TABLE component_health_state(component TEXT PRIMARY KEY,status TEXT NOT NULL CHECK(status IN ('HEALTHY','DEGRADED','DOWN','UNKNOWN')),message TEXT NOT NULL DEFAULT '',details_json JSONB NOT NULL DEFAULT '{}'::jsonb,checked_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
 op.execute("CREATE TABLE component_health_history(id BIGSERIAL PRIMARY KEY,component TEXT NOT NULL,old_status TEXT,new_status TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,correlation_id TEXT NOT NULL DEFAULT '',changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
 op.execute("CREATE INDEX idx_health_history_component_time ON component_health_history(component,changed_at DESC)")
 op.execute("CREATE INDEX idx_health_history_status_time ON component_health_history(new_status,changed_at DESC)")
 op.execute("CREATE TABLE scheduled_job_health(job_name TEXT PRIMARY KEY,display_name TEXT NOT NULL,enabled BOOLEAN NOT NULL DEFAULT TRUE,expected_interval_seconds INTEGER,grace_seconds INTEGER NOT NULL DEFAULT 60,last_started_at TIMESTAMPTZ,last_finished_at TIMESTAMPTZ,last_status TEXT NOT NULL DEFAULT 'UNKNOWN',duration_ms INTEGER,last_error TEXT NOT NULL DEFAULT '',consecutive_failures INTEGER NOT NULL DEFAULT 0,next_expected_at TIMESTAMPTZ,updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)")
 op.execute("CREATE INDEX idx_job_health_status_expected ON scheduled_job_health(last_status,next_expected_at)")
 op.execute("INSERT INTO scheduled_job_health(job_name,display_name,enabled,expected_interval_seconds,grace_seconds,last_status) VALUES ('exception_reconciliation','Đối soát ngoại lệ',TRUE,300,120,'UNKNOWN'),('log_retention','Dọn nhật ký theo retention',TRUE,86400,3600,'UNKNOWN')")
 op.execute("UPDATE system_meta SET value='69.0.0.1',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
def downgrade():
 op.execute('DROP TABLE IF EXISTS scheduled_job_health');op.execute('DROP TABLE IF EXISTS component_health_history');op.execute('DROP TABLE IF EXISTS component_health_state')
