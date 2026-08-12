"""Backfill zero operation plan quantity from production order.

Revision ID: 0011
Revises: 0010
"""
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE operations AS o
        SET plan_qty = po.planned_quantity,
            updated_at = CURRENT_TIMESTAMP
        FROM production_orders AS po
        WHERE o.production_order_id = po.id
          AND COALESCE(o.plan_qty, 0) = 0
          AND COALESCE(po.planned_quantity, 0) > 0
    """)


def downgrade():
    # Data backfill is intentionally not reversed.
    pass
