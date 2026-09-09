"""SETUP as a linked support Operation, plus one classification for all of them.

Design (agreed 2026-09-09):

- No new hierarchy. SETUP is a real row in `operations`, so it reuses the QR,
  session, employee-activity, station and timeline machinery unchanged. It
  hangs off its production Operation through parent_operation_id.

- `operation_type` (PRODUCTION | SETUP | REWORK) becomes the ONE piece of
  state that says what an Operation is. `is_rework_op` shipped in 0044 and is
  read in a dozen queries, so rather than leave two flags that can disagree,
  it is dropped and re-added as a GENERATED column over operation_type. Every
  existing reader keeps working untouched; divergence stops being possible.
  It only ever had one real write site (rework.py), which now sets the type.

- The flag lives on the PRODUCTION Operation (requires_setup), and so does the
  validity state (setup_completed_at). The linked SETUP row holds the config
  (expected minutes, checklist). One source of truth per fact.

Setup validity, V1, deliberately boring and testable: a production session may
start when the main Operation's setup_completed_at is set. Completing a setup
session with every required step ticked sets it; an admin can clear it to
demand a fresh setup. No shift/batch/timeout concept is invented here -- there
is no data model for "đợt" today, and guessing one would be worse than a rule
you can state in one sentence.

SETUP never carries production quantity: no target, no good/NG, excluded from
rollups exactly the way REWORK already is. Its TIME is real work and stays in
the employee day view.
"""
from alembic import op
import sqlalchemy as sa

revision = "0047_setup_operations"
down_revision = "0046_template_import_files"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("operations", sa.Column("operation_type", sa.String(16), nullable=False,
                                          server_default="PRODUCTION"))
    op.execute("UPDATE operations SET operation_type='REWORK' WHERE is_rework_op")
    op.create_check_constraint(
        "ck_operations_operation_type", "operations",
        "operation_type IN ('PRODUCTION','SETUP','REWORK')")
    # One classification, not two that can drift. Everything that already
    # filters on is_rework_op keeps reading the same column name.
    op.drop_column("operations", "is_rework_op")
    op.execute("""ALTER TABLE operations ADD COLUMN is_rework_op BOOLEAN
        GENERATED ALWAYS AS (operation_type='REWORK') STORED""")
    # Dropping the column took 0044's index with it. Recreate it under the
    # same name: it is still worth having, and 0044's own downgrade expects
    # to find it.
    op.create_index("idx_operations_is_rework_op", "operations",
                    ["production_order_id", "part_id", "is_rework_op"])

    op.add_column("operations", sa.Column("parent_operation_id", sa.BigInteger(),
                                          sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=True))
    op.add_column("operations", sa.Column("requires_setup", sa.Boolean(), nullable=False,
                                          server_default=sa.text("false")))
    op.add_column("operations", sa.Column("expected_setup_minutes", sa.Integer(), nullable=True))
    op.add_column("operations", sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("operations", sa.Column("setup_completed_session_id", sa.BigInteger(),
                                          sa.ForeignKey("work_sessions.id", ondelete="SET NULL"), nullable=True))
    op.create_check_constraint("ck_operations_no_self_parent", "operations",
                               "parent_operation_id IS NULL OR parent_operation_id <> id")
    # A SETUP row is meaningless without its parent, and a routing step must
    # never acquire one -- this is what keeps the model flat.
    op.create_check_constraint(
        "ck_operations_setup_has_parent", "operations",
        "(operation_type='SETUP') = (parent_operation_id IS NOT NULL)")
    # V1 is 1-1: exactly one SETUP per production Operation.
    op.execute("""CREATE UNIQUE INDEX uq_operations_one_setup_per_parent
        ON operations(parent_operation_id) WHERE operation_type='SETUP'""")
    op.create_index("idx_operations_parent", "operations", ["parent_operation_id"])

    op.create_table(
        "setup_steps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("setup_operation_id", sa.BigInteger(), sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_setup_steps_operation", "setup_steps", ["setup_operation_id", "sort_order"])

    op.create_table(
        "setup_step_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("work_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("setup_step_id", sa.BigInteger(), sa.ForeignKey("setup_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("session_id", "setup_step_id", name="uq_setup_step_result"),
    )

    # Template side: the checklist travels with the Template so a cloned PO
    # arrives ready to run, rather than needing the setup re-entered per PO.
    op.add_column("template_operations", sa.Column("requires_setup", sa.Boolean(), nullable=False,
                                                   server_default=sa.text("false")))
    op.add_column("template_operations", sa.Column("expected_setup_minutes", sa.Integer(), nullable=True))
    op.create_table(
        "template_setup_steps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("template_operation_id", sa.BigInteger(), sa.ForeignKey("template_operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("idx_template_setup_steps_operation", "template_setup_steps",
                    ["template_operation_id", "sort_order"])
    op.execute("UPDATE system_meta SET value='72.0.7.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("UPDATE system_meta SET value='72.0.6.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
    op.drop_index("idx_template_setup_steps_operation", table_name="template_setup_steps")
    op.drop_table("template_setup_steps")
    op.drop_column("template_operations", "expected_setup_minutes")
    op.drop_column("template_operations", "requires_setup")
    op.drop_table("setup_step_results")
    op.drop_index("idx_setup_steps_operation", table_name="setup_steps")
    op.drop_table("setup_steps")
    op.drop_index("idx_operations_parent", table_name="operations")
    op.execute("DROP INDEX IF EXISTS uq_operations_one_setup_per_parent")
    op.drop_constraint("ck_operations_setup_has_parent", "operations", type_="check")
    op.drop_constraint("ck_operations_no_self_parent", "operations", type_="check")
    op.drop_column("operations", "setup_completed_session_id")
    op.drop_column("operations", "setup_completed_at")
    op.drop_column("operations", "expected_setup_minutes")
    op.drop_column("operations", "requires_setup")
    op.drop_column("operations", "parent_operation_id")
    op.drop_column("operations", "is_rework_op")
    op.add_column("operations", sa.Column("is_rework_op", sa.Boolean(), nullable=False,
                                          server_default=sa.text("false")))
    op.execute("UPDATE operations SET is_rework_op=TRUE WHERE operation_type='REWORK'")
    # Same reason as upgrade(): hand 0044 back the index it created.
    op.create_index("idx_operations_is_rework_op", "operations",
                    ["production_order_id", "part_id", "is_rework_op"])
    op.drop_constraint("ck_operations_operation_type", "operations", type_="check")
    op.drop_column("operations", "operation_type")
