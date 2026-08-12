from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_version_and_migration():
    version=(ROOT/'VERSION.txt').read_text().strip()
    assert f"__version__='{version}'" in (ROOT/'app/mesflow/__init__.py').read_text().replace(' ', '')
    m=(ROOT/'app/migrations/versions/0016_action_error_logs.py').read_text()
    assert "create_table('action_logs'" in m and 'traceback_text' in m and 'trace_id' in m
def test_hooks_and_masking():
    a=(ROOT/'app/mesflow/web/app.py').read_text();l=(ROOT/'app/mesflow/web/action_logging.py').read_text()
    assert 'before_request(begin_request)' in a and 'finish_request(response)' in a
    assert "'password'" in l and 'X-Trace-ID' in l and 'traceback.format_exception' in l
def test_ui():
    j=(ROOT/'app/mesflow/web/static/app.js').read_text()
    assert "page:'system-logs'" in j and 'renderSystemLogs' in j and '/api/system/action-logs' in j
