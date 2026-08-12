from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_long_revision_widens_alembic_version_before_schema_changes():
    source=(ROOT/'app/migrations/versions/0019_operation_input_consumption_ledger.py').read_text(encoding='utf-8')
    alter='ALTER COLUMN version_num TYPE VARCHAR(128)'
    assert alter in source
    assert source.index(alter) < source.index('op.create_table(')
    assert len('0019_operation_input_consumption_ledger') > 32


def test_runtime_version_matches_release():
    version=(ROOT/'VERSION.txt').read_text(encoding='utf-8').strip()
    init=(ROOT/'app/mesflow/__init__.py').read_text(encoding='utf-8').replace(' ','')
    assert f"__version__='{version}'" in init
