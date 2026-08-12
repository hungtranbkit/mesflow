"""link production order to source template

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision='0015'
down_revision='0014'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('production_orders', sa.Column('source_template_id', sa.BigInteger(), nullable=True))
    op.add_column('production_orders', sa.Column('source_template_code', sa.Text(), nullable=False, server_default=''))
    op.add_column('production_orders', sa.Column('source_template_version', sa.Text(), nullable=False, server_default=''))
    op.create_foreign_key(
        'fk_production_orders_source_template',
        'production_orders','templates',
        ['source_template_id'],['id'],
        ondelete='SET NULL',
    )
    op.create_index('idx_production_orders_source_template','production_orders',['source_template_id'])
    op.execute("UPDATE system_meta SET value='65.8.7',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.drop_index('idx_production_orders_source_template',table_name='production_orders')
    op.drop_constraint('fk_production_orders_source_template','production_orders',type_='foreignkey')
    op.drop_column('production_orders','source_template_version')
    op.drop_column('production_orders','source_template_code')
    op.drop_column('production_orders','source_template_id')
    op.execute("UPDATE system_meta SET value='65.8.6',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
