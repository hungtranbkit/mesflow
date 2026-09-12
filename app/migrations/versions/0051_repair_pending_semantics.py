"""One meaning for work_sessions.rework_qty: DECLARED REPAIRABLE (0051).

The bug (P0, reported 2026-09-12): an operator finishes a session declaring
3 NG of which 2 are repairable -- "chờ sửa = 2" in their own words -- and the
Tổng quan Operation row shows **1**.  Reproduced end-to-end on a clean stack
(tests/integration/test_repair_pending_semantics.py; the backfill below has its
own proof in tests/integration/test_repair_pending_migration_backfill.py): the number on screen was
the SCRAP remainder (3-2), i.e. the exact complement of the answer.  Declaring
5 NG with *zero* repairable put all 5 into the repair queue; declaring 2 NG
with both repairable emptied it.

Root cause -- one column, two meanings:

  WRITE side (every input path, and it has always been this way):
    rework_qty = "Lỗi sửa được" = of this session's NG, how many CAN be
    repaired.  Written by the ESP kiosk ("Nhập số lỗi sửa được", which then
    shows "Phế = NG - Sửa được"), kiosk v2, the web finish dialog, the admin
    session edit, the operation edit, and the offline-sync event
    (offline_sync.py maps the device's own `repairable_qty` onto it).
    0032's quantity_movements ledger records it under movement_type
    'REPAIRABLE' -- and that table's CHECK already carries a *separate*
    'REWORK_RECOVERED' type for "actually got fixed", which is the giveaway
    that the two were always meant to be different numbers.
    scheduling.py feeds a downstream operation from `src.rework_qty` when
    input_source_kind='REWORK' -- a pool of repairABLE pieces.

  READ side (0044_rework_queue and the analytics rollups built on it):
    rework_qty = "of these defects, how many were FIXED", so
    pending = defect_qty - rework_qty - scrap_qty.

Both cannot be true.  This migration settles it on the WRITE side's meaning,
because that is what the operator is actually typing, what the trace ledger
already calls it, what requirement REQ-RWK-001 defines "Chờ sửa" as, and what
every screen except the three rollups already assumes.  0044's reading is the
one that has to go.

After this migration:

  defect_qty     total NG found by this session                 (unchanged)
  rework_qty     of those, DECLARED REPAIRABLE at finish        (unchanged
                 on the write path; no longer mutated by a repair)
  repaired_qty   NEW -- of the repairable bucket, how many the SỬA HÀNG
                 queue actually recovered
  scrap_qty      of the repairable bucket, how many the queue wrote off
                 after triage (0044's meaning, unchanged)

  Chờ sửa  = rework_qty - repaired_qty - scrap_qty
  Phế      = (defect_qty - rework_qty) + scrap_qty
             i.e. written off at declaration, plus written off after a
             failed repair attempt.  The first term was missing entirely
             before: declaring 5 NG / 0 repairable reported "Phế 0".

Backfill is exact, not a guess.  rework_ledger is append-only and records
every resolution ever made (qty_reworked / qty_scrapped per source session),
and resolve() was the ONLY writer that ever added to rework_qty after the
finish.  So the declared value is recoverable arithmetic:

    repaired_qty := SUM(ledger.qty_reworked)
    rework_qty   := rework_qty - SUM(ledger.qty_reworked)

scrap_qty needs no backfill -- resolve() already wrote exactly the new
meaning into it.

KNOWN ISSUE, deliberately NOT fixed here (isolated per the P0 brief): rows
resolved *through the inverted queue* could have had pieces "repaired" that
were never declared repairable (the old queue listed sessions with
defect_qty > rework_qty + scrap_qty, so a 5-NG / 0-repairable session was
offered for repair).  For those rows repaired+scrapped > declared, which the
new invariant would reject.  The backfill lifts rework_qty to
repaired_qty+scrap_qty for exactly those rows -- a piece that demonstrably
was repaired was, in fact, repairable -- capped at defect_qty, and counts
them so the migration log says how many rows were touched.  This does not
attempt to reconstruct what the operator would have declared had the input
screen asked the right question; that history does not exist.
"""
from alembic import op
import sqlalchemy as sa

revision = "0051_repair_pending_semantics"
down_revision = "0050_user_session_epoch"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("work_sessions", sa.Column("repaired_qty", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("operations", sa.Column("repaired_qty", sa.Integer(), nullable=False, server_default=sa.text("0")))

    # The old invariant rework_qty+scrap_qty<=defect_qty described 0044's
    # reading (fixed+written-off<=found). Under the declared-repairable
    # reading the true invariants are rework_qty<=defect_qty (you cannot
    # declare more repairable than you found) and repaired+scrapped<=rework
    # (you cannot resolve a piece that was never in the bucket). Dropped
    # BEFORE the backfill: de-inflating rework_qty is safe under both, but
    # the lift-to-resolved step below is not.
    op.drop_constraint("ck_work_sessions_rework_scrap_le_defect", "work_sessions", type_="check")

    op.execute("""
        WITH resolved AS (
          SELECT source_session_id,
                 COALESCE(SUM(qty_reworked),0)::int qty_reworked,
                 COALESCE(SUM(qty_scrapped),0)::int qty_scrapped
            FROM rework_ledger GROUP BY source_session_id
        )
        UPDATE work_sessions ws
           SET repaired_qty = resolved.qty_reworked,
               rework_qty = LEAST(
                 GREATEST(ws.rework_qty - resolved.qty_reworked,
                          resolved.qty_reworked + resolved.qty_scrapped),
                 ws.defect_qty)
          FROM resolved
         WHERE resolved.source_session_id = ws.id
    """)

    op.create_check_constraint(
        "ck_work_sessions_repaired_nonnegative", "work_sessions", "repaired_qty >= 0")
    op.create_check_constraint(
        "ck_work_sessions_rework_le_defect", "work_sessions", "rework_qty <= defect_qty")
    op.create_check_constraint(
        "ck_work_sessions_resolved_le_rework", "work_sessions",
        "repaired_qty + scrap_qty <= rework_qty")
    op.create_check_constraint(
        "ck_operations_repaired_nonnegative", "operations", "repaired_qty >= 0")
    # No operations-level rework/repaired/scrap relation check, for 0044's own
    # stated reason: operation rows are aggregates that can legitimately lag a
    # source session mid-correction. The session-level constraints above are
    # the authoritative guard.

    # Rebuild every Operation aggregate so operations.repaired_qty (and the
    # de-inflated rework_qty) are live immediately, rather than waiting for the
    # next session write on each operation to reconcile it.
    #
    # done_qty and defect_qty are rebuilt in the SAME statement even though
    # neither changes meaning here, and that is not tidiness -- it is what
    # makes this migration safe to run on a database that has drifted. An
    # operations row whose aggregate lags its sessions (0044's docstring says
    # outright that it can) would otherwise get a fresh rework_qty against a
    # stale defect_qty and trip ck_operations_rework_le_defect, aborting the
    # whole upgrade. Rebuilding all five from the same rows makes both
    # operation-level CHECKs true by construction, because each holds per
    # session and sums preserve them. Caught by
    # tests/integration/test_repair_pending_migration_backfill.py; the
    # clean-database upgrade path cannot see it, having no rows to drift.
    #
    # Identical filters to reconcile_operation() on purpose -- this is that
    # function's arithmetic, applied in bulk once.
    op.execute("""
        UPDATE operations o SET
          done_qty = COALESCE(s.good_qty,0),
          defect_qty = COALESCE(s.defect_qty,0),
          rework_qty = COALESCE(s.rework_qty,0),
          repaired_qty = COALESCE(s.repaired_qty,0),
          scrap_qty = COALESCE(s.scrap_qty,0)
        FROM (SELECT operation_id,
                COALESCE(SUM(good_qty) FILTER (WHERE status='CLOSED'),0) good_qty,
                COALESCE(SUM(defect_qty) FILTER (WHERE status='CLOSED'),0) defect_qty,
                COALESCE(SUM(rework_qty) FILTER (WHERE status='CLOSED'),0) rework_qty,
                COALESCE(SUM(repaired_qty) FILTER (WHERE status='CLOSED'),0) repaired_qty,
                COALESCE(SUM(scrap_qty) FILTER (WHERE status='CLOSED'),0) scrap_qty
              FROM work_sessions
              WHERE COALESCE(excluded_from_reports,FALSE)=FALSE
              GROUP BY operation_id) s
        WHERE s.operation_id = o.id
    """)

    op.execute("UPDATE system_meta SET value='72.0.10.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("UPDATE system_meta SET value='72.0.9.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
    # Fold repaired pieces back into rework_qty, restoring 0044's reading.
    op.execute("UPDATE work_sessions SET rework_qty = rework_qty + repaired_qty WHERE repaired_qty > 0")
    op.drop_constraint("ck_operations_repaired_nonnegative", "operations", type_="check")
    op.drop_constraint("ck_work_sessions_resolved_le_rework", "work_sessions", type_="check")
    op.drop_constraint("ck_work_sessions_rework_le_defect", "work_sessions", type_="check")
    op.drop_constraint("ck_work_sessions_repaired_nonnegative", "work_sessions", type_="check")
    op.create_check_constraint(
        "ck_work_sessions_rework_scrap_le_defect", "work_sessions",
        "rework_qty + scrap_qty <= defect_qty")
    op.drop_column("operations", "repaired_qty")
    op.drop_column("work_sessions", "repaired_qty")
