"""Controlled ESP kiosk OTA deployments and durable targets."""
from alembic import op

revision = "0028_kiosk_ota_rollout_control"
down_revision = "0027_kiosk_ota_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO rbac_permissions(code,module,name,page,action,sort_order) VALUES
      ('ota.view','ESP Kiosk OTA','Xem thiết bị, firmware và lịch sử OTA','esp-ota','view',82),
      ('ota.firmware.manage','ESP Kiosk OTA','Upload, activate và disable firmware','esp-ota','edit',83),
      ('ota.deploy','ESP Kiosk OTA','Tạo và bắt đầu deployment OTA','esp-ota','deploy',84),
      ('ota.control','ESP Kiosk OTA','Pause, resume, cancel và retry OTA','esp-ota','control',85)
      ON CONFLICT(code) DO NOTHING""")
    op.execute("""INSERT INTO rbac_role_permissions(role_code,permission_code)
      SELECT r.code,p.code FROM rbac_roles r CROSS JOIN rbac_permissions p
      WHERE p.code LIKE 'ota.%' AND (r.code='admin' OR r.code='manager' OR (r.code='supervisor' AND p.code='ota.view'))
      ON CONFLICT DO NOTHING""")
    op.execute("""
    CREATE TABLE kiosk_ota_deployments (
      id UUID PRIMARY KEY,
      deployment_code TEXT NOT NULL UNIQUE,
      firmware_id UUID NOT NULL REFERENCES kiosk_firmware(id),
      status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN
        ('draft','scheduled','running','paused','completed','completed_with_errors','cancelled')),
      created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      started_at TIMESTAMPTZ,
      completed_at TIMESTAMPTZ,
      notes TEXT NOT NULL DEFAULT ''
    )
    """)
    op.execute("CREATE INDEX idx_kiosk_ota_deployments_firmware ON kiosk_ota_deployments(firmware_id)")
    op.execute("CREATE INDEX idx_kiosk_ota_deployments_status_created ON kiosk_ota_deployments(status,created_at DESC)")
    op.execute("""
    CREATE TABLE kiosk_ota_deployment_targets (
      id BIGSERIAL PRIMARY KEY,
      deployment_id UUID NOT NULL REFERENCES kiosk_ota_deployments(id) ON DELETE CASCADE,
      kiosk_id TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN
        ('pending','waiting_device','waiting_idle','waiting_sync','downloading','verifying',
         'rebooting','healthcheck','success','failed','rollback','cancelled',
         'skipped_same_version','skipped_downgrade_blocked')),
      from_version TEXT NOT NULL DEFAULT '',
      to_version TEXT NOT NULL,
      requested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      started_at TIMESTAMPTZ,
      completed_at TIMESTAMPTZ,
      last_event TEXT NOT NULL DEFAULT '',
      error_code TEXT NOT NULL DEFAULT '',
      error_message TEXT NOT NULL DEFAULT '',
      retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
      UNIQUE(deployment_id,kiosk_id)
    )
    """)
    op.execute("CREATE INDEX idx_kiosk_ota_targets_deployment_status ON kiosk_ota_deployment_targets(deployment_id,status)")
    op.execute("CREATE INDEX idx_kiosk_ota_targets_kiosk ON kiosk_ota_deployment_targets(kiosk_id,requested_at DESC)")
    op.execute("CREATE INDEX idx_kiosk_ota_targets_status ON kiosk_ota_deployment_targets(status)")
    op.execute("""CREATE UNIQUE INDEX uq_kiosk_ota_one_open_target
      ON kiosk_ota_deployment_targets(kiosk_id)
      WHERE status IN ('pending','waiting_device','waiting_idle','waiting_sync','downloading',
                       'verifying','rebooting','healthcheck')""")
    op.execute("ALTER TABLE kiosk_ota_events ADD COLUMN deployment_id UUID REFERENCES kiosk_ota_deployments(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE kiosk_ota_events ADD COLUMN deployment_target_id BIGINT REFERENCES kiosk_ota_deployment_targets(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX idx_kiosk_ota_events_deployment ON kiosk_ota_events(deployment_id,created_at DESC)")
    op.execute("CREATE INDEX idx_kiosk_ota_events_status_created ON kiosk_ota_events(status,created_at DESC)")
    op.execute("UPDATE system_meta SET value='65.8.44.59',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("ALTER TABLE kiosk_ota_events DROP COLUMN IF EXISTS deployment_target_id")
    op.execute("ALTER TABLE kiosk_ota_events DROP COLUMN IF EXISTS deployment_id")
    op.execute("DROP TABLE IF EXISTS kiosk_ota_deployment_targets")
    op.execute("DROP TABLE IF EXISTS kiosk_ota_deployments")
    op.execute("DELETE FROM rbac_permissions WHERE code LIKE 'ota.%'")
