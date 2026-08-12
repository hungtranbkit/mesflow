from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_restore_backup_suite_is_wired_into_docker_tests():
    test = (ROOT / 'tests/integration/test_backup_restore.py').read_text(encoding='utf-8')
    runner = (ROOT / 'scripts/test/restore-backup-test.sh').read_text(encoding='utf-8')
    dockerfile = (ROOT / 'Dockerfile.test').read_text(encoding='utf-8')
    assert 'pg_dump' in test and 'pg_restore' in test
    assert 'CREATE DATABASE' in test and 'DROP DATABASE IF EXISTS' in test
    assert 'operation_input_consumptions' in test and 'error_traces' in test
    assert 'postgresql-client' in dockerfile
    assert 'backup-restore.xml' in runner
