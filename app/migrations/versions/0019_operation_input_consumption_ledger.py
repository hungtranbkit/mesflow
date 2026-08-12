from alembic import op
import sqlalchemy as sa

revision = "0019_operation_input_consumption_ledger"
down_revision = "0018_session_exception_workflow"
branch_labels = None
depends_on = None


def upgrade():
    # Alembic creates alembic_version.version_num as VARCHAR(32) by default.
    # This revision id is longer than 32 characters, so widen the column before
    # Alembic updates the version row at the end of this migration.
    op.execute(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(128)"
    )

    op.create_table(
        "operation_input_consumptions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_operation_id", sa.BigInteger(), sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_operation_id", sa.BigInteger(), sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("work_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("good_qty_consumed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("defect_qty_consumed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("good_qty_consumed >= 0", name="ck_input_consumption_good_nonnegative"),
        sa.CheckConstraint("defect_qty_consumed >= 0", name="ck_input_consumption_defect_nonnegative"),
        sa.UniqueConstraint("session_id", name="uq_input_consumption_session"),
    )
    op.create_index("idx_input_consumption_source", "operation_input_consumptions", ["source_operation_id", "created_at"])
    op.create_index("idx_input_consumption_target", "operation_input_consumptions", ["target_operation_id", "created_at"])

    # Backfill one ledger row for every existing closed downstream session.
    op.execute("""
        INSERT INTO operation_input_consumptions(
            source_operation_id,target_operation_id,session_id,good_qty_consumed,defect_qty_consumed
        )
        SELECT o.input_source_operation_id,o.id,ws.id,COALESCE(ws.good_qty,0),
               CASE WHEN o.defects_consume_input THEN COALESCE(ws.defect_qty,0) ELSE 0 END
        FROM work_sessions ws
        JOIN operations o ON o.id=ws.operation_id
        WHERE ws.status='CLOSED' AND o.input_flow_enabled=TRUE
          AND o.input_source_operation_id IS NOT NULL
        ON CONFLICT(session_id) DO NOTHING
    """)
    op.execute("UPDATE system_meta SET value='65.8.37',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.drop_table("operation_input_consumptions")
