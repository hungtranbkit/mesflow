"""material flow constraints

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision='0014'
down_revision='0013'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('template_operations', sa.Column('input_flow_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('template_operations', sa.Column('input_source_code', sa.String(length=96), nullable=True))
    op.add_column('template_operations', sa.Column('defects_consume_input', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('operations', sa.Column('input_flow_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('operations', sa.Column('input_source_operation_id', sa.BigInteger(), nullable=True))
    op.add_column('operations', sa.Column('defects_consume_input', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.create_foreign_key('fk_operations_input_source','operations','operations',['input_source_operation_id'],['id'],ondelete='SET NULL')
    op.create_index('idx_operations_input_source','operations',['input_source_operation_id'])

def downgrade():
    op.drop_index('idx_operations_input_source',table_name='operations')
    op.drop_constraint('fk_operations_input_source','operations',type_='foreignkey')
    op.drop_column('operations','defects_consume_input')
    op.drop_column('operations','input_source_operation_id')
    op.drop_column('operations','input_flow_enabled')
    op.drop_column('template_operations','defects_consume_input')
    op.drop_column('template_operations','input_source_code')
    op.drop_column('template_operations','input_flow_enabled')
