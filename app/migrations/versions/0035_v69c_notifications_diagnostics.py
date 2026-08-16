"""Phase 2 Health Center: notification delivery audit trail (WEB/EMAIL/
TELEGRAM per health_alerts.fingerprint) and diagnostic snapshots. The WEB
channel itself reuses the existing `notifications` table (source_type=
'HEALTH_ALERT', deduped by its existing UNIQUE(source_type,source_id));
this migration only adds what does not already exist: per-channel delivery
status/audit, and captured diagnostic evidence."""
from alembic import op
revision='0035_v69c_notifications_diagnostics';down_revision='0034_v69b_health_alerts';branch_labels=None;depends_on=None
def upgrade():
 op.execute("""CREATE TABLE notification_deliveries(
   id BIGSERIAL PRIMARY KEY,
   alert_fingerprint TEXT NOT NULL,
   event_type TEXT NOT NULL CHECK(event_type IN ('OPENED','RESOLVED','TEST')),
   channel TEXT NOT NULL CHECK(channel IN ('WEB','EMAIL','TELEGRAM')),
   status TEXT NOT NULL CHECK(status IN ('PENDING','SENT','FAILED','SKIPPED')),
   attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
   delivered_at TIMESTAMPTZ,
   error TEXT NOT NULL DEFAULT '',
   correlation_id TEXT NOT NULL DEFAULT '')""")
 op.execute("CREATE INDEX idx_notification_deliveries_fp ON notification_deliveries(alert_fingerprint,event_type,channel)")
 op.execute("CREATE INDEX idx_notification_deliveries_time ON notification_deliveries(attempted_at DESC)")
 op.execute("""CREATE TABLE health_diagnostics_snapshots(
   id BIGSERIAL PRIMARY KEY,
   component TEXT NOT NULL,
   alert_fingerprint TEXT NOT NULL DEFAULT '',
   level TEXT NOT NULL CHECK(level IN ('SUMMARY','DETAIL')),
   requested_by_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
   data_json JSONB NOT NULL DEFAULT '{}'::jsonb,
   captured_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
   correlation_id TEXT NOT NULL DEFAULT '')""")
 op.execute("CREATE INDEX idx_health_diag_component_time ON health_diagnostics_snapshots(component,captured_at DESC)")
 op.execute("CREATE INDEX idx_health_diag_alert ON health_diagnostics_snapshots(alert_fingerprint) WHERE alert_fingerprint<>''")
 op.execute("UPDATE system_meta SET value='69.2.0.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
def downgrade():
 op.execute('DROP TABLE IF EXISTS health_diagnostics_snapshots')
 op.execute('DROP TABLE IF EXISTS notification_deliveries')
