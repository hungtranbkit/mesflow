from alembic import op
import sqlalchemy as sa

revision = "0018_session_exception_workflow"
down_revision = "0017_work_shifts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "session_exception_reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("work_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exception_code", sa.String(40), nullable=False),
        sa.Column("exception_fingerprint", sa.String(120), nullable=False),
        sa.Column("workflow_status", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("resolution", sa.String(40), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("assigned_to", sa.String(120), nullable=False, server_default=""),
        sa.Column("started_by", sa.String(120), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(120), nullable=False, server_default=""),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("workflow_status IN ('NEW','IN_PROGRESS','RESOLVED','IGNORED')", name="ck_session_exception_review_status"),
        sa.UniqueConstraint("session_id", "exception_fingerprint", name="uq_session_exception_review_fingerprint"),
    )
    op.create_index("idx_session_exception_reviews_status", "session_exception_reviews", ["workflow_status", "updated_at"])
    op.create_index("idx_session_exception_reviews_session", "session_exception_reviews", ["session_id"])
    op.execute("UPDATE system_meta SET value='65.8.36',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.drop_table("session_exception_reviews")
