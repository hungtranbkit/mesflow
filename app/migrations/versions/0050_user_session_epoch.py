"""users.session_epoch — makes a stateless login session revocable.

WHY THIS COLUMN EXISTS

MESFlow authenticates with a signed cookie and no server-side session store.
That is what makes login survive a container restart and an image redeploy with
nothing to persist — but it also means a cookie cannot be taken back: it stays
valid until it expires on its own. Measured before this change: a copy of the
cookie captured before /api/auth/logout still authenticated afterwards.

`session_epoch` is the session version. It is folded into the `auth_epoch`
stamp written into every session cookie at login and re-checked on each
request; bumping it makes every cookie issued under the previous value stop
validating at once. Bumped by: manual logout, password change, and account
deactivation.

Semantics worth knowing: the epoch is per USER, not per device, so a logout
signs that account out everywhere. For a factory account shared across a
supervisor's laptop and an office PC that is the safer default — "I logged out"
should mean it.

REVERSIBLE: downgrade drops the column. Sessions keep working across the
downgrade; they simply become non-revocable again (auth_epoch falls back to
password_hash + active, which is what it used before this migration).
"""
from alembic import op

revision = "0050_user_session_epoch"
down_revision = "0049_offline_event_retry_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    # NOT NULL DEFAULT 0 so every existing row gets a value without a backfill
    # pass, and no existing session is invalidated by deploying this: their
    # cookies carry no auth_epoch at all and are left alone until next login.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS session_epoch INTEGER NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS session_epoch")
