from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase5_files():
    for name in [
        'preflight.sh',
        'deploy.sh',
        'backup.sh',
        'restore.sh',
        'regression-test.sh',
    ]:
        assert (ROOT / 'scripts' / name).exists()
    assert (ROOT / 'nginx' / 'nginx.conf').exists()
    assert (ROOT / 'app' / 'migrations' / 'versions' / '0005_production_ops.py').exists()


def test_no_sqlite_runtime():
    source = '\n'.join(
        path.read_text(errors='ignore')
        for path in (ROOT / 'app' / 'mesflow').rglob('*.py')
    )
    assert 'sqlite3' not in source
    assert 'PRAGMA ' not in source
