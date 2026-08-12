from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def text(path): return (ROOT/path).read_text(encoding='utf-8')

def test_retention_contract():
    cfg=text('app/mesflow/core/config.py')
    assert 'log_retention_success_days' in cfg
    assert 'log_retention_unresolved_error_days' in cfg
    service=text('app/mesflow/core/log_retention.py')
    assert "outcome='SUCCESS'" in service
    assert "outcome='SLOW'" in service
    assert 'DELETE FROM {table}' in service
    api=text('app/mesflow/web/action_logging.py')
    assert "@bp.get('/log-retention/preview')" in api
    assert "@bp.post('/log-retention/run')" in api

def test_retention_migration_and_scripts():
    migration=text('app/migrations/versions/0020_log_retention.py')
    assert "revision='0020_log_retention'" in migration
    assert "down_revision='0019_operation_input_consumption_ledger'" in migration
    assert "'error_traces'" in migration
    assert "'log_retention_runs'" in migration
    assert (ROOT/'scripts/cleanup-logs.sh').exists()
    assert (ROOT/'scripts/install-log-retention-cron.sh').exists()
