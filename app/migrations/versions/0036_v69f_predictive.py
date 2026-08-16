"""Phase 3 Predictive / AI: bounded metric history for forecasting,
predictive insights (capacity/anomaly/recurrence) with an ACTIVE/CLEARED
lifecycle mirroring Phase 2's health_alerts, and cached AI incident
analyses. All additive."""
from alembic import op
revision='0036_v69f_predictive';down_revision='0035_v69c_notifications_diagnostics';branch_labels=None;depends_on=None
def upgrade():
 op.execute("""CREATE TABLE health_metric_samples(
   id BIGSERIAL PRIMARY KEY,
   metric TEXT NOT NULL,
   component TEXT NOT NULL DEFAULT '',
   value DOUBLE PRECISION NOT NULL,
   unit TEXT NOT NULL DEFAULT '',
   sampled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
   metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb)""")
 op.execute("CREATE INDEX idx_health_metric_samples_lookup ON health_metric_samples(metric,component,sampled_at DESC)")
 # Bounded retention (section 5): a scheduled cleanup keeps only recent
 # high-resolution rows -- enforced by the collector job, not by the schema.
 op.execute("""CREATE TABLE predictive_insights(
   id BIGSERIAL PRIMARY KEY,
   fingerprint TEXT NOT NULL,
   category TEXT NOT NULL CHECK(category IN ('CAPACITY','ANOMALY','RECURRENCE')),
   risk TEXT NOT NULL CHECK(risk IN ('INFO','LOW','MEDIUM','HIGH')),
   title TEXT NOT NULL,
   message TEXT NOT NULL DEFAULT '',
   confidence TEXT NOT NULL DEFAULT 'INSUFFICIENT_DATA' CHECK(confidence IN ('HIGH','MEDIUM','LOW','INSUFFICIENT_DATA')),
   evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
   status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','CLEARED','SUPERSEDED')),
   opened_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
   last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
   cleared_at TIMESTAMPTZ,
   correlation_id TEXT NOT NULL DEFAULT '')""")
 op.execute("CREATE UNIQUE INDEX uq_predictive_insights_active_fp ON predictive_insights(fingerprint) WHERE status='ACTIVE'")
 op.execute("CREATE INDEX idx_predictive_insights_time ON predictive_insights(opened_at DESC)")
 op.execute("""CREATE TABLE ai_incident_analyses(
   id BIGSERIAL PRIMARY KEY,
   alert_fingerprint TEXT NOT NULL,
   incident_stage TEXT NOT NULL CHECK(incident_stage IN ('OPEN','RECOVERED')),
   context_hash TEXT NOT NULL,
   provider TEXT NOT NULL DEFAULT '',
   model TEXT NOT NULL DEFAULT '',
   status TEXT NOT NULL CHECK(status IN ('SUCCESS','FAILED','INVALID_OUTPUT','TIMEOUT','DISABLED')),
   result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
   error TEXT NOT NULL DEFAULT '',
   requested_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
   generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
 op.execute("CREATE INDEX idx_ai_analyses_fp ON ai_incident_analyses(alert_fingerprint,incident_stage,generated_at DESC)")
 op.execute("INSERT INTO scheduled_job_health(job_name,display_name,enabled,expected_interval_seconds,grace_seconds,last_status) VALUES ('predictive_metrics_collection','Thu thập chỉ số dự đoán',TRUE,900,600,'UNKNOWN') ON CONFLICT(job_name) DO NOTHING")
 op.execute("UPDATE system_meta SET value='69.3.0.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
def downgrade():
 op.execute("DELETE FROM scheduled_job_health WHERE job_name='predictive_metrics_collection'")
 op.execute('DROP TABLE IF EXISTS ai_incident_analyses')
 op.execute('DROP TABLE IF EXISTS predictive_insights')
 op.execute('DROP TABLE IF EXISTS health_metric_samples')
