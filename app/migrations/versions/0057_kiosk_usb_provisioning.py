"""One-time USB proof for trusted kiosk enrollment.

The ESP proves possession of its existing device secret over its physical
serial connection. The server stores only nonce hashes and never returns the
kiosk token to the operator; the kiosk claims that token through its normal
HTTPS connect retry.
"""
from alembic import op

revision = "0057_kiosk_usb_provisioning"
down_revision = "0056_kiosk_enrollment_approval"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS device_id TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS usb_provision_challenge_hash TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS usb_provision_challenge_until TIMESTAMPTZ NULL")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS usb_provision_station_id INTEGER NULL")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS usb_provision_challenge_by TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS usb_provision_challenge_used BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS usb_provision_mac TEXT NOT NULL DEFAULT ''")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_kiosk_identities_usb_provision_mac ON kiosk_identities(usb_provision_mac) WHERE usb_provision_mac <> ''")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_kiosk_identities_usb_provision_mac")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS usb_provision_mac")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS usb_provision_challenge_used")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS usb_provision_challenge_by")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS usb_provision_station_id")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS usb_provision_challenge_until")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS usb_provision_challenge_hash")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS device_id")
