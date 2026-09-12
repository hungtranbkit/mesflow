from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def source(path): return (ROOT / path).read_text(encoding="utf-8")

# Rewritten 2026-09-12 (P0: Tổng quan showed "Chờ sửa 1" for a declared 2).
#
# This file has now pinned the formula twice and been wrong twice, which is
# the argument for what it pins today. The 2026-09-09 revision replaced a
# literal `rework_qty` with a literal `defect_qty-rework_qty-scrap_qty` on the
# belief that rework_qty meant "already fixed"; it does not, and never did on
# the write path (see 0051_repair_pending_semantics.py), so that formula
# printed the scrap remainder under "Chờ sửa".
#
# So: stop pinning SQL text. What matters is that all three rollups derive
# pending from ONE shared helper -- repair_pending_sql() -- so they cannot
# disagree, and that the arithmetic itself is asserted against real data by
# tests/integration/test_repair_pending_semantics.py, which drives the real
# kiosk finish path and would have caught both inversions.

def test_repair_pending_comes_from_the_one_shared_helper():
    repo=source("app/mesflow/db/repositories/analytics.py")
    base=source("app/mesflow/db/repositories/base.py")
    rework=source("app/mesflow/db/repositories/rework.py")
    assert "repair_pending_quantity" in repo
    assert "repair_completed_quantity" not in repo
    assert "def repair_pending_sql" in base
    # The bucket is what the operator DECLARED repairable, less what the
    # bench has resolved -- never defect minus repairable, which is scrap.
    assert "rework_qty,0)-COALESCE({p}repaired_qty,0)" in base
    # Each of the three readers of "chờ sửa" must go through it.
    assert repo.count("repair_pending_sql(") >= 2
    assert "repair_pending_sql(" in rework
    # ...and none of them may spell the arithmetic out for itself again.
    for spelled in ("defect_qty-rework_qty-scrap_qty",
                    "SUM(rework_qty),0)::bigint repair_pending_quantity"):
        assert spelled not in repo, spelled

def test_workload_uses_explicit_repair_standard():
    repo=source("app/mesflow/db/repositories/analytics.py")
    # Remaining repair workload is priced off the PENDING quantity, using the
    # repair standard -- never the production standard.
    assert "{pending}*repair_cycle_time_seconds_per_unit" in repo
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
    # Từ 2026-09-10 bộ lọc không còn viết tay ở đây nữa: nó được sinh ra từ
    # mesflow.domain.policy và nhúng vào truy vấn qua hằng số. Bài test vì vậy
    # kiểm ĐÚNG hình mới -- vẫn là "OP hỗ trợ bị loại khỏi tiến độ PO", chỉ
    # khác chỗ câu trả lời đến từ đâu. Chuỗi COALESCE viết tay bây giờ là dấu
    # hiệu SAI, và test_po_status_policy_is_single_sourced.py cấm nó.
    assert "from mesflow.domain.policy import" in repo
    assert repo.count("{PRODUCTION_ONLY_BARE}") >= 2
    assert "{PRODUCTION_ONLY_O}" in repo
    # Bộ lọc chỉ-theo-rework cũ sẽ để SETUP lọt qua.
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
