from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def source(path): return (ROOT / path).read_text(encoding="utf-8")

# Updated 2026-09-09 (rework audit). These contracts used to pin the OLD
# model, in which "chờ sửa" was read straight off rework_qty and scrap was
# inferred as `defect - rework`. Migration 0044 settled the real model:
# rework_qty = pieces FIXED, scrap_qty = pieces WRITTEN OFF, and pending is
# whatever is left over -- so the pinned formulas here were locking in the
# very inversion the audit found on live TEST data.

def test_repair_pending_is_derived_not_read_off_rework_qty():
    repo=source("app/mesflow/db/repositories/analytics.py")
    assert "repair_pending_quantity" in repo
    assert "repair_completed_quantity" not in repo
    # Pending must be defect minus what has already been resolved.
    assert "defect_qty-rework_qty-scrap_qty" in repo
    # ...and must never be plain SUM(rework_qty) again.
    assert "SUM(rework_qty),0)::bigint repair_pending_quantity" not in repo

def test_workload_uses_explicit_repair_standard():
    repo=source("app/mesflow/db/repositories/analytics.py")
    # Remaining repair workload is priced off the PENDING quantity, using the
    # repair standard -- never the production standard.
    assert "defect_qty-rework_qty-scrap_qty,0)*repair_cycle_time_seconds_per_unit" in repo
    assert "rework_qty*standard_seconds_per_unit" not in repo

def test_support_operations_excluded_from_po_progress():
    """P0 regression guard (see tests/integration/test_rework_overview_rollup.py).

    Neither support Operation -- the SỬA HÀNG workbench nor a SETUP row --
    may reach the terminal-operation set, the operation counts or the repair
    rollup: they have no target and are never reconciled, so counting one
    collapsed PO progress to zero. Widened 2026-09-09 from the rework-only
    flag to operation_type, which is now the single classification (0047).
    """
    repo=source("app/mesflow/db/repositories/analytics.py")
    assert repo.count("COALESCE(operation_type,'PRODUCTION')='PRODUCTION'") >= 2
    assert "COALESCE(o.operation_type,'PRODUCTION')='PRODUCTION'" in repo
    # The old rework-only filter would silently let SETUP through.
    assert "COALESCE(is_rework_op,FALSE)=FALSE" not in repo
    assert "COALESCE(o.is_rework_op,FALSE)=FALSE" not in repo

def test_offline_retry_keeps_backlog_idempotent():
    offline=source("app/mesflow/db/repositories/offline_sync.py")
    ledger=source("app/migrations/versions/0023_kiosk_offline_sync.py")
    assert "repairable_qty" in offline
    assert "client_event_id" in ledger and "unique=True" in ledger

def test_quantity_examples():
    # defect splits into three disjoint buckets; scrap is never inferred.
    for defect,repaired,scrapped in [(3,1,2),(10,10,0),(10,0,10),(10,4,2),(0,0,0)]:
        pending=defect-repaired-scrapped
        assert pending >= 0
        assert repaired+scrapped+pending == defect
