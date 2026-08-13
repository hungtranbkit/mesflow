"""ESP32 kiosk OTA firmware inventory and event foundation."""
from alembic import op

revision = "0027_kiosk_ota_foundation"
down_revision = "0026_night_shift_same_day_midnight"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS firmware_build TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS hardware_model TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS ota_capable BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("""
    CREATE TABLE IF NOT EXISTS kiosk_firmware (
      id UUID PRIMARY KEY,
      version TEXT NOT NULL,
      build TEXT NOT NULL,
      hardware_model TEXT NOT NULL,
      filename TEXT NOT NULL,
      storage_path TEXT NOT NULL,
      file_size BIGINT NOT NULL CHECK(file_size > 0),
      sha256 CHAR(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
      release_status TEXT NOT NULL DEFAULT 'draft' CHECK(release_status IN ('draft','active','disabled')),
      mandatory BOOLEAN NOT NULL DEFAULT FALSE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
      UNIQUE(hardware_model,version,build)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_kiosk_firmware_active ON kiosk_firmware(hardware_model,created_at DESC) WHERE release_status='active'")
    op.execute("""
    CREATE TABLE IF NOT EXISTS kiosk_ota_events (
      id BIGSERIAL PRIMARY KEY,
      kiosk_id TEXT NOT NULL,
      firmware_id UUID REFERENCES kiosk_firmware(id) ON DELETE SET NULL,
      from_version TEXT NOT NULL DEFAULT '',
      to_version TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL,
      error_code TEXT NOT NULL DEFAULT '',
      message TEXT NOT NULL DEFAULT '',
      device_timestamp TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_kiosk_ota_events_device ON kiosk_ota_events(kiosk_id,created_at DESC)")
    op.execute("UPDATE system_meta SET value='65.8.44.58',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("DROP TABLE IF EXISTS kiosk_ota_events")
    op.execute("DROP TABLE IF EXISTS kiosk_firmware")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS ota_capable")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS hardware_model")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS firmware_build")
