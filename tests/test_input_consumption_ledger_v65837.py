from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def text(path): return (ROOT/path).read_text(encoding="utf-8")

def test_ledger_migration_and_atomic_repository_contract():
    migration=text("app/migrations/versions/0019_operation_input_consumption_ledger.py")
    execution=text("app/mesflow/db/repositories/execution.py")
    assert "operation_input_consumptions" in migration
    assert 'UniqueConstraint("session_id"' in migration
    assert "FOR UPDATE" in execution
    assert "_validate_and_upsert_input_consumption" in execution
    assert "source_operation_id=%s AND source_qty_kind=%s AND session_id<>%s" in execution

def test_duplicate_daily_operations_tab_removed():
    js=text("app/mesflow/web/static/app.js")
    assert "label:'Theo dõi OP theo ngày'" not in js
    assert "if(id==='daily-operations')" not in js
