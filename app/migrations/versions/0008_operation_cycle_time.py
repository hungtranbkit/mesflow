from alembic import op
import sqlalchemy as sa

revision = "0008_operation_cycle_time"
down_revision = "0007_seed_sqlite_employees"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("template_operations", sa.Column("standard_seconds_per_unit", sa.Numeric(12,3), nullable=False, server_default="0"))
    op.add_column("operations", sa.Column("standard_seconds_per_unit", sa.Numeric(12,3), nullable=False, server_default="0"))
    op.create_index("idx_operations_cycle_time", "operations", ["standard_seconds_per_unit"])
    op.execute("UPDATE system_meta SET value='65.7.1',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.drop_index("idx_operations_cycle_time", table_name="operations")
    op.drop_column("operations", "standard_seconds_per_unit")
    op.drop_column("template_operations", "standard_seconds_per_unit")
