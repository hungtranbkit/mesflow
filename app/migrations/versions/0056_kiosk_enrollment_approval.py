"""Admin-approved, short-lived, single-device kiosk enrollment.

Before this, a hardware kiosk the instance had never seen (fresh install,
staging, a board moved from another MESFlow) could not get a token at all:
/api/kiosk/connect answered 403 "chưa được đăng ký" and recorded nothing,
/api/kiosk-identities/<id>/approve hands the token to the *admin's browser*
(fine for browser kiosks, useless for an ESP32), and the device's own
256-bit device_secret was ignored. Columns:

  enroll_secret_hash     sha256(device_secret) recorded on first contact
                         (proof of possession; never overwritten by a
                         different secret)
  enroll_station_code    station the device asked for (display only)
  enroll_station_id      station chosen by the admin at approval
  enroll_approved_until  approval window; the device claims its token with
                         the matching secret before this, exactly once
  enroll_approved_by     admin username (also in audit log)

Idempotent; downgrade drops only these columns.
"""
from alembic import op

revision = "0056_kiosk_enrollment_approval"
down_revision = "0055_mesflow_instance_identity"
branch_labels = None
depends_on = None

COLUMNS = (
    ("enroll_secret_hash", "TEXT NOT NULL DEFAULT ''"),
    ("enroll_station_code", "TEXT NOT NULL DEFAULT ''"),
    ("enroll_station_id", "INTEGER NULL"),
    ("enroll_approved_until", "TIMESTAMPTZ NULL"),
    ("enroll_approved_by", "TEXT NOT NULL DEFAULT ''"),
)


def upgrade():
    for name, ddl in COLUMNS:
        op.execute(f"ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS {name} {ddl}")


def downgrade():
    for name, _ in reversed(COLUMNS):
        op.execute(f"ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS {name}")
