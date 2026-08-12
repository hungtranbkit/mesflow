from alembic import op
import sqlalchemy as sa

revision = "0021_material_flow_trace"
down_revision = "0020_log_retention"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("operation_input_consumptions", sa.Column("origin", sa.String(24), nullable=False, server_default="RUNTIME"))
    op.execute("UPDATE operation_input_consumptions SET origin='BACKFILL'")
    op.create_table(
        "operation_input_consumption_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ledger_id", sa.BigInteger(), nullable=True),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("old_data", sa.JSON(), nullable=True),
        sa.Column("new_data", sa.JSON(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_input_consumption_history_ledger", "operation_input_consumption_history", ["ledger_id", "changed_at"])
    op.execute("""
    CREATE OR REPLACE FUNCTION audit_operation_input_consumption() RETURNS trigger AS $$
    BEGIN
      IF TG_OP='UPDATE' THEN
        INSERT INTO operation_input_consumption_history(ledger_id,session_id,action,old_data,new_data)
        VALUES(OLD.id,OLD.session_id,'UPDATE',to_jsonb(OLD),to_jsonb(NEW));
        RETURN NEW;
      ELSIF TG_OP='DELETE' THEN
        INSERT INTO operation_input_consumption_history(ledger_id,session_id,action,old_data,new_data)
        VALUES(OLD.id,OLD.session_id,'DELETE',to_jsonb(OLD),NULL);
        RETURN OLD;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_audit_operation_input_consumption
    AFTER UPDATE OR DELETE ON operation_input_consumptions
    FOR EACH ROW EXECUTE FUNCTION audit_operation_input_consumption();
    """)
    op.execute("UPDATE system_meta SET value='65.8.41',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_audit_operation_input_consumption ON operation_input_consumptions")
    op.execute("DROP FUNCTION IF EXISTS audit_operation_input_consumption()")
    op.drop_table("operation_input_consumption_history")
    op.drop_column("operation_input_consumptions", "origin")
