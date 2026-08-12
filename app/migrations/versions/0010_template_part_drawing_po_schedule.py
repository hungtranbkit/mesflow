from alembic import op
import sqlalchemy as sa

revision='0010'
down_revision='0009_working_calendar'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('template_parts', sa.Column('drawing_path', sa.Text(), nullable=False, server_default=''))
    op.add_column('production_orders', sa.Column('planned_start_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('production_orders', sa.Column('planned_end_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('idx_po_planned_window','production_orders',['planned_start_at','planned_end_at'])
    op.execute("UPDATE system_meta SET value='65.7.5.1',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.drop_index('idx_po_planned_window', table_name='production_orders')
    op.drop_column('production_orders','planned_end_at')
    op.drop_column('production_orders','planned_start_at')
    op.drop_column('template_parts','drawing_path')
