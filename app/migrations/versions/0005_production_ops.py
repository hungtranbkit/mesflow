"""production operations metadata

Revision ID: 0005_production_ops
Revises: 0004_analytics_events
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_production_ops'
down_revision = '0004_analytics_events'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'deployment_history',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('deployment_id', sa.Text(), nullable=False, unique=True),
        sa.Column('version', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='started'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('details', sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index('idx_deployment_history_started', 'deployment_history', ['started_at'])
    op.execute("INSERT INTO system_meta(key,value) VALUES('schema_version','65.4.0') ON CONFLICT(key) DO UPDATE SET value=excluded.value")


def downgrade():
    op.drop_index('idx_deployment_history_started', table_name='deployment_history')
    op.drop_table('deployment_history')
    op.execute("UPDATE system_meta SET value='65.3.0' WHERE key='schema_version'")
