from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_phase4_files():
    assert (ROOT/'app/migrations/versions/0004_analytics_events.py').exists()
    assert (ROOT/'app/mesflow/db/repositories/analytics.py').exists()
    assert (ROOT/'app/mesflow/web/analytics.py').exists()

def test_no_sqlite_phase4():
    for rel in ('app/mesflow/db/repositories/analytics.py','app/mesflow/web/analytics.py'):
        text=(ROOT/rel).read_text(encoding='utf-8').lower()
        assert 'sqlite' not in text
        assert 'pragma' not in text
