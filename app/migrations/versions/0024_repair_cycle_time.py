"""Add explicit repair work standards without changing rework semantics."""
from alembic import op
import sqlalchemy as sa

revision = "0024_repair_cycle_time"
down_revision = "0023_kiosk_offline_sync"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("template_operations", sa.Column("repair_cycle_time_seconds_per_unit", sa.Numeric(12, 3), nullable=False, server_default="0"))
    op.add_column("operations", sa.Column("repair_cycle_time_seconds_per_unit", sa.Numeric(12, 3), nullable=False, server_default="0"))
    op.create_check_constraint("ck_template_operations_repair_cycle_nonnegative", "template_operations", "repair_cycle_time_seconds_per_unit >= 0")
    op.create_check_constraint("ck_operations_repair_cycle_nonnegative", "operations", "repair_cycle_time_seconds_per_unit >= 0")


def downgrade():
    op.drop_constraint("ck_operations_repair_cycle_nonnegative", "operations", type_="check")
    op.drop_constraint("ck_template_operations_repair_cycle_nonnegative", "template_operations", type_="check")
    op.drop_column("operations", "repair_cycle_time_seconds_per_unit")
    op.drop_column("template_operations", "repair_cycle_time_seconds_per_unit")
