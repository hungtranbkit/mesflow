"""One printable instruction sheet instead of a step-by-step checklist.

0047 modelled setup as an ordered checklist the operator ticked off on the
device. That was the wrong shape for the hardware: the ESP kiosk has a small
fixed screen, and a scrolling list of steps is unreadable on it. The workshop
already works from paper, so the detailed procedure belongs on an A4 sheet at
the machine, and the kiosk only has to control STATE -- start setup, confirm
done.

So the checklist tables are dropped rather than left as dead weight, and a
single free-text field takes their place. Operators number their own steps
inside it; line breaks are preserved when it is printed.

Dropping is safe here: the checklist shipped to the TEST host only, was never
used for real work, and production does not exist yet. Keeping three unused
tables plus their API and UI would cost more than it saves.
"""
from alembic import op
import sqlalchemy as sa

revision = "0048_setup_note_replaces_checklist"
down_revision = "0047_setup_operations"
branch_labels = None
depends_on = None


def upgrade():
    # The whole setup procedure, free text, newlines significant.
    op.add_column("operations", sa.Column("setup_note", sa.Text(), nullable=False, server_default=""))
    op.add_column("template_operations", sa.Column("setup_note", sa.Text(), nullable=False, server_default=""))
    op.drop_table("setup_step_results")
    op.drop_table("setup_steps")
    op.drop_table("template_setup_steps")
    op.execute("UPDATE system_meta SET value='72.0.8.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("UPDATE system_meta SET value='72.0.7.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
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
    op.drop_column("template_operations", "setup_note")
    op.drop_column("operations", "setup_note")
