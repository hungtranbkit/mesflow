"""Phase 1 Health Center: Active Alerts (fingerprinted, open/resolve
lifecycle) -- additive to the V69 System Health foundation
(component_health_state/component_health_history already cover per-component
current status and transitions; this table adds per-condition alerts such as
"KIOSK-07 offline" or "Disk usage 86%" that a single component-level status
row cannot represent)."""
from alembic import op
revision='0034_v69b_health_alerts';down_revision='0033_v69_system_health';branch_labels=None;depends_on=None
def upgrade():
 op.execute("""CREATE TABLE health_alerts(
   id BIGSERIAL PRIMARY KEY,
   fingerprint TEXT NOT NULL,
   component TEXT NOT NULL,
   severity TEXT NOT NULL CHECK(severity IN ('CRITICAL','HIGH','MEDIUM','LOW')),
   title TEXT NOT NULL,
   message TEXT NOT NULL DEFAULT '',
   metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
   correlation_id TEXT NOT NULL DEFAULT '',
   opened_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
   last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
   resolved_at TIMESTAMPTZ)""")
 op.execute("CREATE UNIQUE INDEX uq_health_alerts_open_fingerprint ON health_alerts(fingerprint) WHERE resolved_at IS NULL")
 op.execute("CREATE INDEX idx_health_alerts_resolved_time ON health_alerts(resolved_at DESC NULLS FIRST,opened_at DESC)")
 op.execute("UPDATE system_meta SET value='69.1.0.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
def downgrade():
 op.execute('DROP TABLE IF EXISTS health_alerts')
