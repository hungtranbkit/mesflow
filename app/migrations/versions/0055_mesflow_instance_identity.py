"""Stable MESFlow instance identity + kiosk hardware profile / running artifact.

`mesflow_instance_id` is the ownership key the Deploy Agent binds its OTA
fleet to. It is generated ONCE per database (random UUID), survives domain
changes and VPS moves (it lives in the DB), and is never derived from a
domain, IP, build timestamp or server generation. `cluster_id` from 0038 is
not usable for this: it defaults to the same 'MESFLOW-PROD' on every install.

A cloned database on a NEW install keeps the same id, so the runtime also
binds the id to an install secret fingerprint (see core/instance_identity.py);
a mismatch reports UNVERIFIED_CLONE and the Agent refuses OTA until the owner
explicitly runs `adopt` (same system moved) or `new-install` (fresh identity).

Idempotent: ON CONFLICT DO NOTHING / ADD COLUMN IF NOT EXISTS.
Downgrade drops the two kiosk columns but deliberately KEEPS the instance id:
re-upgrading must not mint a new identity and orphan the fleet.
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0055_mesflow_instance_identity"
down_revision = "0054_multi_open_session_per_employee"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("INSERT INTO system_meta(key,value) VALUES('mesflow_instance_id',:v) ON CONFLICT(key) DO NOTHING")
               .bindparams(v=str(uuid.uuid4())))
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS hardware_profile TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE kiosk_identities ADD COLUMN IF NOT EXISTS firmware_artifact_id TEXT NOT NULL DEFAULT ''")


def downgrade():
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS firmware_artifact_id")
    op.execute("ALTER TABLE kiosk_identities DROP COLUMN IF EXISTS hardware_profile")
