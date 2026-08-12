import hashlib
import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ['DATABASE_URL']
REQUIRED_TABLES = {
    'users', 'employees', 'production_orders', 'parts', 'operations',
    'work_sessions', 'operation_input_consumptions', 'work_shifts',
    'session_exception_reviews', 'action_logs', 'error_traces',
    'log_retention_runs', 'alembic_version',
}


def _database_url(database_name: str) -> str:
    parsed = urlsplit(DATABASE_URL)
    return urlunsplit((parsed.scheme, parsed.netloc, f'/{database_name}', parsed.query, parsed.fragment))


def _run(command: list[str], *, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(command, text=True, capture_output=True, env=env, cwd=cwd)
    assert result.returncode == 0, (
        f"Command failed ({result.returncode}): {' '.join(command)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


@pytest.mark.timeout(240)
def test_postgres_backup_can_restore_into_isolated_database(db, tmp_path: Path):
    """Create a real custom-format backup and prove it restores without touching the source DB."""
    marker = f'RESTORE-{uuid.uuid4().hex[:16]}'
    restore_db = f"mesflow_restore_{uuid.uuid4().hex[:12]}"
    dump_file = tmp_path / 'mesflow-restore-test.dump'
    manifest_file = tmp_path / 'mesflow-restore-test.manifest'
    checksum_file = tmp_path / 'mesflow-restore-test.sha256'

    # Use a normal MESFlow table as the data-integrity marker.
    row = db.execute(
        """INSERT INTO employees(employee_no,name,department,position,qr)
           VALUES(%s,'Restore Test Marker','TEST','TEST',%s) RETURNING id""",
        (marker, f'WF|EMP|{marker}'),
    ).fetchone()
    marker_id = row['id']
    source_heads = db.execute('SELECT version_num FROM alembic_version').fetchall()
    assert len(source_heads) == 1, f'Expected one source migration head, got {source_heads!r}'
    source_head = source_heads[0]['version_num']

    maintenance_url = _database_url('postgres')
    restored_url = _database_url(restore_db)
    try:
        _run(['pg_dump', '--format=custom', '--no-owner', '--no-acl', '--file', str(dump_file), DATABASE_URL])
        assert dump_file.stat().st_size > 1024

        manifest = _run(['pg_restore', '--list', str(dump_file)]).stdout
        manifest_file.write_text(manifest, encoding='utf-8')
        assert 'TABLE DATA public employees' in manifest
        assert 'TABLE DATA public alembic_version' in manifest

        digest = hashlib.sha256(dump_file.read_bytes()).hexdigest()
        checksum_file.write_text(f'{digest}  {dump_file.name}\n', encoding='utf-8')
        assert len(digest) == 64

        with psycopg.connect(maintenance_url, autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(restore_db)))

        _run([
            'pg_restore', '--exit-on-error', '--no-owner', '--no-acl',
            '--dbname', restored_url, str(dump_file),
        ])

        with psycopg.connect(restored_url, row_factory=psycopg.rows.dict_row) as restored:
            restored_marker = restored.execute(
                'SELECT id,employee_no,name FROM employees WHERE employee_no=%s', (marker,)
            ).fetchone()
            assert restored_marker is not None
            assert restored_marker['id'] == marker_id
            assert restored_marker['name'] == 'Restore Test Marker'

            head = restored.execute('SELECT version_num FROM alembic_version').fetchone()['version_num']
            assert head == source_head

            tables = restored.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            ).fetchall()
            assert REQUIRED_TABLES <= {row['tablename'] for row in tables}

            # Validate restored constraints rather than only table presence.
            fk_count = restored.execute(
                "SELECT count(*) AS n FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace"
            ).fetchone()['n']
            assert fk_count > 0
            restored.execute('SELECT count(*) FROM operation_input_consumptions').fetchone()
            restored.execute('SELECT count(*) FROM error_traces').fetchone()

        # Prove the restored DB is already at the current migration head.
        migration_env = os.environ.copy()
        migration_env['DATABASE_URL'] = restored_url
        migration_env['WORKSHOP_DATABASE_URL'] = restored_url
        current = _run(['alembic', 'current'], env=migration_env, cwd=Path('/workspace/app')).stdout
        assert source_head in current
    finally:
        db.execute('DELETE FROM employees WHERE id=%s', (marker_id,))
        with psycopg.connect(maintenance_url, autocommit=True) as admin:
            admin.execute(
                'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()',
                (restore_db,),
            )
            admin.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(restore_db)))
