"""Durable idempotency and audit ledger for kiosk offline production events."""
from alembic import op
import sqlalchemy as sa

revision = '0023_kiosk_offline_sync'
down_revision = '0022_rework_flow'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'kiosk_client_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('client_event_id', sa.Text(), nullable=False, unique=True),
        sa.Column('payload_hash', sa.Text(), nullable=False),
        sa.Column('kiosk_id', sa.Text(), nullable=False),
        sa.Column('local_sequence', sa.BigInteger(), nullable=False),
        sa.Column('local_session_id', sa.Text(), nullable=False, server_default=''),
        sa.Column('session_trace_id', sa.Text(), nullable=False, server_default=''),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('event_time', sa.DateTime(timezone=True)),
        sa.Column('time_quality', sa.Text(), nullable=False, server_default='unknown'),
        sa.Column('device_uptime_ms', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('boot_id', sa.Text(), nullable=False, server_default=''),
        sa.Column('snapshot_revision', sa.Text(), nullable=False, server_default=''),
        sa.Column('source', sa.Text(), nullable=False, server_default='OFFLINE_SYNC'),
        sa.Column('status', sa.Text(), nullable=False, server_default='PROCESSING'),
        sa.Column('reason_code', sa.Text(), nullable=False, server_default=''),
        sa.Column('reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('server_session_id', sa.BigInteger(), sa.ForeignKey('work_sessions.id', ondelete='SET NULL')),
        sa.Column('payload_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('result_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('processed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('kiosk_id', 'local_sequence', name='uq_kiosk_client_event_sequence'),
    )
    op.create_index('idx_kiosk_client_events_kiosk_status', 'kiosk_client_events', ['kiosk_id', 'status', 'local_sequence'])
    op.create_index('idx_kiosk_client_events_local_session', 'kiosk_client_events', ['kiosk_id', 'local_session_id', 'event_type'])


def downgrade():
    op.drop_index('idx_kiosk_client_events_local_session', table_name='kiosk_client_events')
    op.drop_index('idx_kiosk_client_events_kiosk_status', table_name='kiosk_client_events')
    op.drop_table('kiosk_client_events')
