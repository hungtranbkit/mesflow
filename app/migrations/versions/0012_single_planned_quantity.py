"""Use production_orders.planned_quantity as the single production target.

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

def upgrade():
    # Recover a PO target from legacy operations only when the PO target is missing.
    op.execute("""
        UPDATE production_orders po
        SET planned_quantity = src.max_plan_qty, updated_at = CURRENT_TIMESTAMP
        FROM (
            SELECT production_order_id, MAX(plan_qty) AS max_plan_qty
            FROM operations
            WHERE COALESCE(plan_qty, 0) > 0
            GROUP BY production_order_id
        ) src
        WHERE po.id = src.production_order_id
          AND COALESCE(po.planned_quantity, 0) <= 0
    """)
    op.drop_column('operations', 'plan_qty')
    op.drop_column('template_operations', 'plan_qty')
    op.execute("UPDATE system_meta SET value='65.7.5.3',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.add_column('template_operations', sa.Column('plan_qty', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('operations', sa.Column('plan_qty', sa.Integer(), nullable=False, server_default='0'))
    op.execute("""
        UPDATE operations o SET plan_qty = po.planned_quantity
        FROM production_orders po WHERE po.id=o.production_order_id
    """)
