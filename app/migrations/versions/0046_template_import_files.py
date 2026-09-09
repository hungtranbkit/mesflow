"""Keep the Excel workbook every Template import was made from.

Today `templates.source_workbook` holds only the uploaded file's NAME, and a
re-import overwrites it -- so when a Template turns out to be wrong (TPL-6126
arrived with ten duplicate Operation codes, 2026-09-09) there is no way to
open the sheet that produced it, or even to tell which of several uploads was
responsible.

Two tables rather than one, on purpose:

- `template_import_blobs` is content-addressed by sha256, so re-importing the
  same workbook twice stores the bytes once. The file itself lives on the
  uploads volume (same place drawings already go); only the pointer and the
  digest live here.
- `template_import_events` is the append-only history: one row per import
  ATTEMPT, including the ones that failed. A failed import writes no template
  at all, which is exactly the case the old `source_workbook` column could
  never describe -- and the case someone debugging a bad sheet needs most.

`template_id` is nullable and ON DELETE SET NULL: the point is to survive the
template, not to disappear with it.
"""
from alembic import op
import sqlalchemy as sa

revision = "0046_template_import_files"
down_revision = "0045_rework_queue_permissions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "template_import_blobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_table(
        "template_import_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("blob_id", sa.BigInteger(), sa.ForeignKey("template_import_blobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_id", sa.BigInteger(), sa.ForeignKey("templates.id", ondelete="SET NULL")),
        # Kept as plain text as well: the code is what a person searches by,
        # and it must stay readable after the template row is gone.
        sa.Column("template_code", sa.Text(), nullable=False, server_default=""),
        sa.Column("original_filename", sa.Text(), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("part_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("operation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_operation_codes", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_user_id", sa.BigInteger()),
        sa.Column("actor_username", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_check_constraint(
        "ck_template_import_outcome", "template_import_events",
        "outcome IN ('CREATED','REPLACED','FAILED')")
    op.create_index("idx_template_import_events_template", "template_import_events", ["template_id"])
    op.create_index("idx_template_import_events_code", "template_import_events", ["template_code"])
    op.create_index("idx_template_import_events_created", "template_import_events", ["created_at"])
    op.execute("UPDATE system_meta SET value='72.0.6.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("UPDATE system_meta SET value='72.0.5.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
    op.drop_index("idx_template_import_events_created", table_name="template_import_events")
    op.drop_index("idx_template_import_events_code", table_name="template_import_events")
    op.drop_index("idx_template_import_events_template", table_name="template_import_events")
    op.drop_table("template_import_events")
    op.drop_table("template_import_blobs")
