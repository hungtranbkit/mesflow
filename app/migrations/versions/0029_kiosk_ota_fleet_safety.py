"""Staged OTA rollout, health gates and fleet safety controls."""
from alembic import op

revision="0029_kiosk_ota_fleet_safety"
down_revision="0028_kiosk_ota_rollout_control"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN ota_hold BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN ota_hold_reason TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN boot_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN uptime_seconds BIGINT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN boot_reason TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN boot_seen_at TIMESTAMPTZ")
    op.execute("ALTER TABLE kiosk_firmware DROP CONSTRAINT kiosk_firmware_release_status_check")
    op.execute("ALTER TABLE kiosk_firmware ADD CONSTRAINT kiosk_firmware_release_status_check CHECK(release_status IN ('draft','active','blocked','disabled'))")
    op.execute("ALTER TABLE kiosk_firmware ADD COLUMN known_good BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("CREATE UNIQUE INDEX uq_kiosk_firmware_known_good ON kiosk_firmware(hardware_model) WHERE known_good")
    op.execute("ALTER TABLE kiosk_ota_deployments ADD COLUMN strategy TEXT NOT NULL DEFAULT 'manual' CHECK(strategy IN ('manual','staged'))")
    op.execute("ALTER TABLE kiosk_ota_deployments ADD COLUMN policy_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE kiosk_ota_deployments ADD COLUMN auto_advance BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE kiosk_ota_deployments ADD COLUMN maintenance_timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh'")
    op.execute("ALTER TABLE kiosk_ota_deployments ADD COLUMN maintenance_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE kiosk_ota_deployments ADD COLUMN emergency_stopped_at TIMESTAMPTZ")
    op.execute("ALTER TABLE kiosk_ota_deployments ADD COLUMN state_reason TEXT NOT NULL DEFAULT ''")
    op.execute("""CREATE TABLE kiosk_ota_stages(
      id BIGSERIAL PRIMARY KEY,deployment_id UUID NOT NULL REFERENCES kiosk_ota_deployments(id) ON DELETE CASCADE,
      stage_order INTEGER NOT NULL CHECK(stage_order>0),name TEXT NOT NULL,target_type TEXT NOT NULL CHECK(target_type IN ('device_count','percentage','all_remaining')),
      target_value NUMERIC(7,2),status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','waiting_health_gate','passed','failed','paused','cancelled')),
      started_at TIMESTAMPTZ,targets_completed_at TIMESTAMPTZ,observation_started_at TIMESTAMPTZ,completed_at TIMESTAMPTZ,
      success_count INTEGER NOT NULL DEFAULT 0,failure_count INTEGER NOT NULL DEFAULT 0,rollback_count INTEGER NOT NULL DEFAULT 0,
      health_gate_status TEXT NOT NULL DEFAULT 'pending',health_gate_reason TEXT NOT NULL DEFAULT '',UNIQUE(deployment_id,stage_order))""")
    op.execute("CREATE INDEX idx_kiosk_ota_stages_state ON kiosk_ota_stages(deployment_id,status,stage_order)")
    op.execute("ALTER TABLE kiosk_ota_deployment_targets ADD COLUMN stage_id BIGINT REFERENCES kiosk_ota_stages(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE kiosk_ota_deployment_targets ADD COLUMN assigned_at TIMESTAMPTZ")
    op.execute("ALTER TABLE kiosk_ota_deployment_targets ADD COLUMN next_retry_at TIMESTAMPTZ")
    op.execute("ALTER TABLE kiosk_ota_deployment_targets DROP CONSTRAINT kiosk_ota_deployment_targets_status_check")
    op.execute("""ALTER TABLE kiosk_ota_deployment_targets ADD CONSTRAINT kiosk_ota_deployment_targets_status_check CHECK(status IN
      ('unassigned','pending','waiting_device','waiting_idle','waiting_sync','waiting_maintenance','downloading','verifying','rebooting','healthcheck','success','failed','rollback','cancelled','timed_out','skipped_same_version','skipped_downgrade_blocked'))""")
    op.execute("CREATE INDEX idx_kiosk_ota_targets_stage_status ON kiosk_ota_deployment_targets(stage_id,status)")
    op.execute("""CREATE TABLE kiosk_ota_exclusions(deployment_id UUID NOT NULL REFERENCES kiosk_ota_deployments(id) ON DELETE CASCADE,
      kiosk_id TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(deployment_id,kiosk_id))""")
    op.execute("""CREATE TABLE kiosk_ota_settings(id SMALLINT PRIMARY KEY DEFAULT 1 CHECK(id=1),global_enabled BOOLEAN NOT NULL DEFAULT TRUE,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_by BIGINT REFERENCES users(id),reason TEXT NOT NULL DEFAULT '')""")
    op.execute("INSERT INTO kiosk_ota_settings(id) VALUES(1) ON CONFLICT DO NOTHING")
    op.execute("ALTER TABLE kiosk_ota_events ADD COLUMN client_event_id TEXT")
    op.execute("CREATE UNIQUE INDEX uq_kiosk_ota_event_idempotency ON kiosk_ota_events(kiosk_id,client_event_id) WHERE client_event_id IS NOT NULL AND client_event_id<>''")
    op.execute("""INSERT INTO rbac_permissions(code,module,name,page,action,sort_order) VALUES
      ('ota.approve_stage','ESP Kiosk OTA','Phê duyệt stage tiếp theo','esp-ota','approve',86),
      ('ota.emergency_stop','ESP Kiosk OTA','Emergency stop rollout','esp-ota','emergency',87),
      ('ota.manage_policy','ESP Kiosk OTA','Quản lý policy/hold/known-good','esp-ota','policy',88),
      ('ota.manage_global_switch','ESP Kiosk OTA','Quản lý global OTA switch','esp-ota','global',89) ON CONFLICT DO NOTHING""")
    op.execute("""INSERT INTO rbac_role_permissions(role_code,permission_code) SELECT r.code,p.code FROM rbac_roles r CROSS JOIN rbac_permissions p
      WHERE p.code IN ('ota.approve_stage','ota.emergency_stop','ota.manage_policy','ota.manage_global_switch') AND
      (r.code='admin' OR (r.code='manager' AND p.code IN ('ota.approve_stage','ota.manage_policy'))) ON CONFLICT DO NOTHING""")
    op.execute("UPDATE system_meta SET value='65.8.44.60',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_kiosk_ota_event_idempotency")
    op.execute("ALTER TABLE kiosk_ota_events DROP COLUMN IF EXISTS client_event_id")
    op.execute("DROP TABLE IF EXISTS kiosk_ota_settings")
    op.execute("DROP TABLE IF EXISTS kiosk_ota_exclusions")
    op.execute("ALTER TABLE kiosk_ota_deployment_targets DROP COLUMN IF EXISTS next_retry_at")
    op.execute("ALTER TABLE kiosk_ota_deployment_targets DROP COLUMN IF EXISTS assigned_at")
    op.execute("ALTER TABLE kiosk_ota_deployment_targets DROP COLUMN IF EXISTS stage_id")
    op.execute("DROP TABLE IF EXISTS kiosk_ota_stages")
