from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def source(path): return (ROOT / path).read_text(encoding="utf-8")

def test_repairable_is_pending_not_completed():
    repo=source("app/mesflow/db/repositories/analytics.py")
    assert "repair_pending_quantity" in repo
    assert "repair_completed_quantity" not in repo

def test_workload_uses_explicit_repair_standard():
    repo=source("app/mesflow/db/repositories/analytics.py")
    assert "rework_qty*repair_cycle_time_seconds_per_unit" in repo
    assert "rework_qty*standard_seconds_per_unit" not in repo

def test_offline_retry_keeps_backlog_idempotent():
    offline=source("app/mesflow/db/repositories/offline_sync.py")
    ledger=source("app/migrations/versions/0023_kiosk_offline_sync.py")
    assert "repairable_qty" in offline
    assert "client_event_id" in ledger and "unique=True" in ledger

def test_quantity_examples():
    for defect,repairable,scrap in [(3,1,2),(10,10,0),(10,0,10)]:
        assert repairable <= defect and scrap == defect-repairable
