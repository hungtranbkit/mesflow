"""Sản phẩm chờ sửa (rework queue), V1: no QC workflow.

Design (see session notes / user's own written spec, 2026-09-08):

- Defects are NOT resolved in a separate table keyed by amount -- they stay
  exactly where they already lived (work_sessions.rework_qty / a new
  work_sessions.scrap_qty), because every existing report/dashboard already
  aggregates good_qty/defect_qty/rework_qty straight off work_sessions and
  none of that needs to change if the SAME columns keep meaning the same
  thing. "Pending" (chờ sửa) for one session is simply
  `defect_qty - rework_qty - scrap_qty`, computed on the fly -- never
  stored, so it can never drift out of sync with the columns it's derived
  from.
- rework_qty already existed (0022_rework_flow) for the OLD "fix it right
  at the kiosk, right now" path (REWORK_DECISION on the device -- entirely
  client-side firmware logic, confirmed by reading kiosk_runtime.cpp, not
  something this migration touches). Going forward the SAME column is also
  where a LATER fix via the new SỬA HÀNG queue gets credited -- one column,
  two ways to arrive at a value, always meaning "of this session's defects,
  how many got fixed" either way. scrap_qty is the new sibling: "of this
  session's defects, how many got written off," so a session's own defect
  bucket never has more than one truthful answer for "resolved" vs
  "pending."
- "SỬA HÀNG" is a real Operation row (is_rework_op=TRUE), one per
  (production_order_id, part_id), auto-created lazily by the repository
  layer the first time it's needed -- NOT created here. It gets a real
  code/qr like any operation (WF|OP|<code> convention, see
  OperationRepository.create()), so the EXISTING kiosk QR-scan session
  lifecycle needs zero changes to let an operator start/stop a rework
  session on it. Excluded from planned_quantity-based completion and from
  reconcile_production_order()'s completed/total rollup (see
  production_state.py) -- it is a workbench, not a routing step with its
  own target.
- rework_ledger is a separate, append-only AUDIT table -- who fixed/
  scrapped how many of which source session's defects, and when. It is
  intentionally NOT the source of truth for the running balance (that's
  still plain arithmetic on work_sessions, above): a "hôm nay" KPI like
  "Loại hôm nay" needs to be dated by when the fix/scrap action itself
  happened, which can be days after the original defect's own session
  date -- exactly what this table's own created_at gives for free, and
  what mutating a possibly-ancient session row in place could never give.

Safe migration: purely additive (2 new nullable-safe columns with
defaults, 1 new table); replaces one existing CHECK constraint on
work_sessions.rework_qty with a slightly broader one covering the new
scrap_qty column too (still permits every value the old constraint did,
only tightens the new dimension); touches no data (a backfill of
`is_rework_op` obviously has nothing to backfill against, since the
column and the rows it would describe are both new; existing rework_qty
values are untouched and remain valid under the new constraint since
scrap_qty defaults to 0).
"""
from alembic import op
import sqlalchemy as sa

revision = "0044_rework_queue"
down_revision = "0043_super_admin_role"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("operations", sa.Column("is_rework_op", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    # Keep the aggregate on Operation and the source-of-truth bucket on each
    # Session.  Both are additive and default to zero for old data.
    op.add_column("operations", sa.Column("scrap_qty", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("work_sessions", sa.Column("scrap_qty", sa.Integer(), nullable=False, server_default=sa.text("0")))

    op.drop_constraint("ck_work_sessions_rework_le_defect", "work_sessions", type_="check")
    op.create_check_constraint(
        "ck_work_sessions_scrap_nonnegative", "work_sessions", "scrap_qty >= 0")
    op.create_check_constraint(
        "ck_work_sessions_rework_scrap_le_defect", "work_sessions",
        "rework_qty + scrap_qty <= defect_qty")
    op.create_check_constraint(
        "ck_operations_scrap_nonnegative", "operations", "scrap_qty >= 0")
    # Operations are aggregates across source sessions.  Do not add an
    # operation-level rework+scrap<=defect check: its rows can contain old
    # data while a source session is being corrected, and the session-level
    # invariant is the authoritative anti-over-credit guard.

    op.create_table(
        "rework_ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_session_id", sa.BigInteger(), sa.ForeignKey("work_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_operation_id", sa.BigInteger(), sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rework_session_id", sa.BigInteger(), sa.ForeignKey("work_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rework_operation_id", sa.BigInteger(), sa.ForeignKey("operations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("qty_reworked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qty_scrapped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_check_constraint("ck_rework_ledger_reworked_nonnegative", "rework_ledger", "qty_reworked >= 0")
    op.create_check_constraint("ck_rework_ledger_scrapped_nonnegative", "rework_ledger", "qty_scrapped >= 0")
    op.create_check_constraint("ck_rework_ledger_not_empty", "rework_ledger", "qty_reworked + qty_scrapped > 0")
    op.create_index("idx_rework_ledger_source_session", "rework_ledger", ["source_session_id"])
    op.create_index("idx_rework_ledger_rework_session", "rework_ledger", ["rework_session_id"])
    op.create_index("idx_rework_ledger_created_at", "rework_ledger", ["created_at"])
    op.create_index("idx_operations_is_rework_op", "operations", ["production_order_id", "part_id", "is_rework_op"])

    op.execute("UPDATE system_meta SET value='72.0.4.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("UPDATE system_meta SET value='72.0.3.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
    op.drop_index("idx_operations_is_rework_op", table_name="operations")
    op.drop_index("idx_rework_ledger_created_at", table_name="rework_ledger")
    op.drop_index("idx_rework_ledger_rework_session", table_name="rework_ledger")
    op.drop_index("idx_rework_ledger_source_session", table_name="rework_ledger")
    op.drop_table("rework_ledger")
    op.drop_constraint("ck_operations_scrap_nonnegative", "operations", type_="check")
    op.drop_constraint("ck_work_sessions_rework_scrap_le_defect", "work_sessions", type_="check")
    op.drop_constraint("ck_work_sessions_scrap_nonnegative", "work_sessions", type_="check")
    op.create_check_constraint("ck_work_sessions_rework_le_defect", "work_sessions", "rework_qty <= defect_qty")
    op.drop_column("work_sessions", "scrap_qty")
    op.drop_column("operations", "scrap_qty")
    op.drop_column("operations", "is_rework_op")
