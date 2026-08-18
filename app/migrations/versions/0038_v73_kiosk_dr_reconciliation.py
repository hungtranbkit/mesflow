"""Server generation/cluster identity + kiosk DR reconciliation bookkeeping.

Adds the durable "generation" concept a kiosk needs to detect that it is now
talking to a server that was restored/failed-over (Server B) rather than the
one it last synced against (Server A) -- see
reports/KIOSK_OFFLINE_DR_SYNC_AUDIT.md section 6/7. `server_generation` is a
deliberately single-row table (id CHECK'd to 1): the cluster has exactly one
current generation at a time, bumped only by an explicit admin action
(ServerGenerationRepository.bump), never inferred/guessed from server state.

kiosk_identities gains three columns used by the reconciliation protocol and
the Kiosk Management admin view: last_generation_id (what generation this
device last reconciled against), last_sequence_received (high-water mark
across accepted/duplicate/rejected events, used to compute the reconcile
sequence range), duplicate_replay_count (previously silently discarded --
now a real counter for the admin view, per audit section 11).
"""
from alembic import op
import sqlalchemy as sa

revision = '0038_v73_kiosk_dr_reconciliation'
down_revision = '0037_v72_audit_operations_separation'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'server_generation',
        sa.Column('id', sa.SmallInteger(), primary_key=True),
        sa.Column('cluster_id', sa.Text(), nullable=False, server_default='MESFLOW-PROD'),
        sa.Column('generation_id', sa.Text(), nullable=False),
        sa.Column('bumped_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('bumped_by', sa.Text(), nullable=False, server_default=''),
        sa.Column('reason', sa.Text(), nullable=False, server_default=''),
        sa.CheckConstraint('id = 1', name='ck_server_generation_singleton'),
    )
    # Seed the one row so ServerGenerationRepository.current() never has to
    # special-case "no row yet". generation_id is a fresh random token, not
    # derived from anything server-identity-shaped (host/IP) -- see audit
    # section 6 ("Do not use physical server IP as identity").
    op.execute(
        "INSERT INTO server_generation(id, cluster_id, generation_id, reason) "
        "VALUES (1, 'MESFLOW-PROD', substr(md5(random()::text || clock_timestamp()::text), 1, 16), "
        "'initial migration seed')"
    )

    op.add_column('kiosk_identities', sa.Column('last_generation_id', sa.Text(), nullable=False, server_default=''))
    op.add_column('kiosk_identities', sa.Column('last_sequence_received', sa.BigInteger(), nullable=False, server_default='0'))
    op.add_column('kiosk_identities', sa.Column('duplicate_replay_count', sa.BigInteger(), nullable=False, server_default='0'))

    # kiosk_client_events.source already exists (0023) with default
    # 'OFFLINE_SYNC' -- reused as-is to tag reconciliation-triggered replays
    # ('RECONCILE_REPLAY') so the Session Exceptions view can single out DR
    # reconciliation conflicts specifically without a new column.


def downgrade():
    op.drop_column('kiosk_identities', 'duplicate_replay_count')
    op.drop_column('kiosk_identities', 'last_sequence_received')
    op.drop_column('kiosk_identities', 'last_generation_id')
    op.drop_table('server_generation')
