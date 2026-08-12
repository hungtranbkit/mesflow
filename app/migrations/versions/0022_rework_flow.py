from alembic import op
import sqlalchemy as sa

revision = "0022_rework_flow"
down_revision = "0021_material_flow_trace"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("work_sessions", sa.Column("rework_qty", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("operations", sa.Column("rework_qty", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("operations", sa.Column("input_source_kind", sa.String(16), nullable=False, server_default="GOOD"))
    op.add_column("template_operations", sa.Column("input_source_kind", sa.String(16), nullable=False, server_default="GOOD"))
    op.add_column("operation_input_consumptions", sa.Column("source_qty_kind", sa.String(16), nullable=False, server_default="GOOD"))
    op.add_column("operation_adjustments", sa.Column("old_rework_qty", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("operation_adjustments", sa.Column("new_rework_qty", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_work_sessions_rework_nonnegative", "work_sessions", "rework_qty >= 0")
    op.create_check_constraint("ck_work_sessions_rework_le_defect", "work_sessions", "rework_qty <= defect_qty")
    op.create_check_constraint("ck_operations_rework_nonnegative", "operations", "rework_qty >= 0")
    op.create_check_constraint("ck_operations_rework_le_defect", "operations", "rework_qty <= defect_qty")
    op.create_check_constraint("ck_operations_input_source_kind", "operations", "input_source_kind IN ('GOOD','REWORK')")
    op.create_check_constraint("ck_template_operations_input_source_kind", "template_operations", "input_source_kind IN ('GOOD','REWORK')")
    op.create_check_constraint("ck_input_consumption_source_kind", "operation_input_consumptions", "source_qty_kind IN ('GOOD','REWORK')")
    op.execute("UPDATE operation_input_consumptions c SET source_qty_kind=COALESCE(o.input_source_kind,'GOOD') FROM operations o WHERE o.id=c.target_operation_id")
    op.execute("UPDATE system_meta SET value='65.8.44.2',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.drop_constraint("ck_input_consumption_source_kind", "operation_input_consumptions", type_="check")
    op.drop_constraint("ck_template_operations_input_source_kind", "template_operations", type_="check")
    op.drop_constraint("ck_operations_input_source_kind", "operations", type_="check")
    op.drop_constraint("ck_operations_rework_le_defect", "operations", type_="check")
    op.drop_constraint("ck_operations_rework_nonnegative", "operations", type_="check")
    op.drop_constraint("ck_work_sessions_rework_le_defect", "work_sessions", type_="check")
    op.drop_constraint("ck_work_sessions_rework_nonnegative", "work_sessions", type_="check")
    op.drop_column("operation_adjustments", "new_rework_qty")
    op.drop_column("operation_adjustments", "old_rework_qty")
    op.drop_column("operation_input_consumptions", "source_qty_kind")
    op.drop_column("template_operations", "input_source_kind")
    op.drop_column("operations", "input_source_kind")
    op.drop_column("operations", "rework_qty")
    op.drop_column("work_sessions", "rework_qty")
