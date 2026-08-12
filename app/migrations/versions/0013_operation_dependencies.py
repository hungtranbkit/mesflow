"""operation dependencies and scheduling

Revision ID: 0013
Revises: 0012_single_planned_quantity
"""
from alembic import op
import sqlalchemy as sa

revision='0013'
down_revision='0012'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('operations',sa.Column('predecessor_operation_id',sa.BigInteger(),nullable=True))
    op.create_foreign_key('fk_operations_predecessor','operations','operations',['predecessor_operation_id'],['id'],ondelete='SET NULL')
    op.add_column('operations',sa.Column('dependency_type',sa.Text(),nullable=False,server_default='FS'))
    op.add_column('operations',sa.Column('lag_minutes',sa.Integer(),nullable=False,server_default='0'))
    op.add_column('operations',sa.Column('planned_start_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('operations',sa.Column('planned_end_at',sa.DateTime(timezone=True),nullable=True))
    op.create_index('idx_operations_predecessor','operations',['predecessor_operation_id'])
    op.execute("UPDATE system_meta SET value='65.7.6',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.drop_index('idx_operations_predecessor',table_name='operations')
    op.drop_constraint('fk_operations_predecessor','operations',type_='foreignkey')
    for c in ('planned_end_at','planned_start_at','lag_minutes','dependency_type','predecessor_operation_id'):
        op.drop_column('operations',c)
    op.execute("UPDATE system_meta SET value='65.7.5.4',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
