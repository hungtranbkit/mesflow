"""Codex audit Blocker 7 -- full migration proof, not just "container
started successfully" (which only ever exercises clean-DB -> head).
Exercises, against a real scratch PostgreSQL database on the same server
(created/dropped by this test, never touching the shared mesflow_test
database other tests use):

  clean DB -> head
  previous realistic schema (0039) + realistic data -> head (0040, 0041)
  head -> downgrade (back to 0039)
  downgrade -> re-upgrade (back to head)

with assertions on: no unintended work_sessions mutation, existing
scheduled_job_health rows preserved, last_success_at backfill semantics,
the new index, and downgrade correctness.
"""
from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.rows import dict_row

pytestmark = pytest.mark.postgres

APP_DIR = '/workspace/app'
BASE_DSN = os.environ.get('DATABASE_URL', 'postgresql://mesflow_test:mesflow_test_password@postgres-test:5432/mesflow_test')


def _server_dsn(dbname: str) -> str:
    # Swap the database name in BASE_DSN's DSN, keep host/user/password.
    prefix, _, _ = BASE_DSN.rpartition('/')
    return f'{prefix}/{dbname}'


def _admin_conn():
    # Connect to the always-present `postgres` maintenance DB to run
    # CREATE/DROP DATABASE (cannot do that while connected to the DB itself).
    return psycopg.connect(_server_dsn('postgres'), autocommit=True, row_factory=dict_row)


def _run_alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env['DATABASE_URL'] = database_url
    return subprocess.run(['alembic', *args], cwd=APP_DIR, env=env, capture_output=True, text=True)


@pytest.fixture()
def scratch_db():
    name = f'mesflow_migration_scratch_{uuid.uuid4().hex[:12]}'
    with _admin_conn() as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    dsn = _server_dsn(name)
    try:
        yield name, dsn
    finally:
        with _admin_conn() as admin:
            admin.execute(f"""SELECT pg_terminate_backend(pid) FROM pg_stat_activity
                WHERE datname='{name}' AND pid<>pg_backend_pid()""")
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')


def test_clean_db_upgrades_to_head(scratch_db):
    _name, dsn = scratch_db
    r = _run_alembic('upgrade', 'head', database_url=dsn)
    assert r.returncode == 0, r.stdout + r.stderr

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        head = conn.execute('SELECT version_num FROM alembic_version').fetchone()
        assert head['version_num'] == '0043_super_admin_role'
        version = conn.execute("SELECT value FROM system_meta WHERE key='schema_version'").fetchone()
        assert version['value'] == '72.0.3.0'
        cols = {r['column_name'] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='work_sessions'")}
        for expected in ('close_reason', 'closed_by_system', 'shift_boundary_used_at', 'started_at_trusted', 'ended_at_trusted'):
            assert expected in cols
        job_cols = {r['column_name'] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='scheduled_job_health'")}
        assert 'last_success_at' in job_cols
        idx = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='work_sessions' AND indexname='idx_work_sessions_open_started'").fetchone()
        assert idx is not None
        jobs = {r['job_name'] for r in conn.execute('SELECT job_name FROM scheduled_job_health')}
        assert {'exception_reconciliation', 'shift_session_reconciliation'} <= jobs


def test_realistic_pre_0040_data_survives_upgrade_to_head(scratch_db):
    _name, dsn = scratch_db
    r = _run_alembic('upgrade', '0039_kiosk_v2_protocol', database_url=dsn)
    assert r.returncode == 0, r.stdout + r.stderr

    now = datetime.now(timezone.utc)
    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as conn:
        emp = conn.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES('M7-EMP','M7 Worker','TEST','Worker','WF|EMP|M7') RETURNING id").fetchone()
        station = conn.execute("INSERT INTO stations(code,name,workshop,production_line) VALUES('M7-ST','M7 Station','TEST','TEST') RETURNING id").fetchone()
        po = conn.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES('M7-PO','M7 PRODUCT',100,'IN_PROGRESS') RETURNING id").fetchone()
        part = conn.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,'M7-PART','M7 Part') RETURNING id", (po['id'],)).fetchone()
        op = conn.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,'M7-OP','M7 Operation','IN_PROGRESS','WF|OP|M7') RETURNING id""", (po['id'], part['id'])).fetchone()

        open_session = conn.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,good_qty,defect_qty,start_request_id)
            VALUES(%s,%s,%s,'OPEN',%s,0,0,'M7-START-OPEN') RETURNING *""",
            (emp['id'], op['id'], station['id'], now - timedelta(hours=2))).fetchone()
        closed_start = now - timedelta(hours=5)
        closed_end = now - timedelta(hours=4)
        closed_session = conn.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
            VALUES(%s,%s,%s,'CLOSED',%s,%s,17,2,'M7-START-CLOSED','M7-FINISH-CLOSED') RETURNING *""",
            (emp['id'], op['id'], station['id'], closed_start, closed_end)).fetchone()

        # Realistic scheduled_job_health history: exception_reconciliation
        # already has a real SUCCESS history (seeded by 0033, but give it a
        # concrete last run); a second, custom job with a FAILED last run
        # and an OLDER success before that -- exactly the case 0041's
        # last_success_at backfill (last_finished_at WHERE last_status=
        # 'SUCCESS') must get right, and must NOT clobber on a later FAILED.
        conn.execute("""UPDATE scheduled_job_health SET last_started_at=%s,last_finished_at=%s,last_status='SUCCESS',consecutive_failures=0
            WHERE job_name='exception_reconciliation'""", (now - timedelta(minutes=10), now - timedelta(minutes=9)))
        conn.execute("""INSERT INTO scheduled_job_health(job_name,display_name,enabled,expected_interval_seconds,grace_seconds,
            last_started_at,last_finished_at,last_status,consecutive_failures)
            VALUES('m7_custom_job','M7 Custom Job',TRUE,300,60,%s,%s,'FAILED',3)""",
            (now - timedelta(minutes=1), now))

    r2 = _run_alembic('upgrade', 'head', database_url=dsn)
    assert r2.returncode == 0, r2.stdout + r2.stderr

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        # No unintended work_sessions mutation: every pre-existing column's
        # value is byte-for-byte unchanged; only the new columns appear,
        # with their documented defaults (manual data is never retroactively
        # marked as auto-closed/trusted).
        reread_open = conn.execute('SELECT * FROM work_sessions WHERE id=%s', (open_session['id'],)).fetchone()
        reread_closed = conn.execute('SELECT * FROM work_sessions WHERE id=%s', (closed_session['id'],)).fetchone()
        for original, reread in ((open_session, reread_open), (closed_session, reread_closed)):
            for key in ('employee_id', 'operation_id', 'station_id', 'status', 'started_at', 'ended_at', 'good_qty', 'defect_qty'):
                assert reread[key] == original[key], (key, original[key], reread[key])
            assert reread['close_reason'] == ''
            assert reread['closed_by_system'] is False
            assert reread['shift_boundary_used_at'] is None
            assert reread['started_at_trusted'] is False
            assert reread['ended_at_trusted'] is False

        # Existing scheduled_job_health rows preserved + last_success_at
        # backfill semantics: SUCCESS row got last_success_at == its
        # last_finished_at; FAILED row's last_success_at stays NULL (it had
        # no prior SUCCESS finish to backfill from).
        exc_job = conn.execute("SELECT * FROM scheduled_job_health WHERE job_name='exception_reconciliation'").fetchone()
        assert exc_job['last_status'] == 'SUCCESS'
        assert exc_job['last_success_at'] == exc_job['last_finished_at']
        custom_job = conn.execute("SELECT * FROM scheduled_job_health WHERE job_name='m7_custom_job'").fetchone()
        assert custom_job['last_status'] == 'FAILED'
        assert custom_job['consecutive_failures'] == 3
        assert custom_job['last_success_at'] is None
        # New job seeded by 0040 present alongside the pre-existing ones.
        assert conn.execute("SELECT 1 FROM scheduled_job_health WHERE job_name='shift_session_reconciliation'").fetchone() is not None


def test_downgrade_then_reupgrade_is_clean(scratch_db):
    _name, dsn = scratch_db
    assert _run_alembic('upgrade', 'head', database_url=dsn).returncode == 0

    with psycopg.connect(dsn, row_factory=dict_row, autocommit=True) as conn:
        conn.execute("UPDATE scheduled_job_health SET last_started_at=CURRENT_TIMESTAMP,last_finished_at=CURRENT_TIMESTAMP,last_status='SUCCESS' WHERE job_name='exception_reconciliation'")

    down1 = _run_alembic('downgrade', '0040_shift_lifecycle_scheduler_health', database_url=dsn)
    assert down1.returncode == 0, down1.stdout + down1.stderr
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        job_cols = {r['column_name'] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='scheduled_job_health'")}
        assert 'last_success_at' not in job_cols
        # exception_reconciliation row itself (pre-existing, from 0033) must
        # survive a downgrade of a LATER migration untouched.
        assert conn.execute("SELECT 1 FROM scheduled_job_health WHERE job_name='exception_reconciliation'").fetchone() is not None

    down2 = _run_alembic('downgrade', '0039_kiosk_v2_protocol', database_url=dsn)
    assert down2.returncode == 0, down2.stdout + down2.stderr
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        cols = {r['column_name'] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='work_sessions'")}
        for removed in ('close_reason', 'closed_by_system', 'shift_boundary_used_at', 'started_at_trusted', 'ended_at_trusted'):
            assert removed not in cols
        assert conn.execute("SELECT 1 FROM scheduled_job_health WHERE job_name='shift_session_reconciliation'").fetchone() is None
        idx = conn.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='work_sessions' AND indexname='idx_work_sessions_open_started'").fetchone()
        assert idx is None

    reup = _run_alembic('upgrade', 'head', database_url=dsn)
    assert reup.returncode == 0, reup.stdout + reup.stderr
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        head = conn.execute('SELECT version_num FROM alembic_version').fetchone()
        assert head['version_num'] == '0043_super_admin_role'
        cols = {r['column_name'] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='work_sessions'")}
        assert {'close_reason', 'closed_by_system', 'started_at_trusted', 'ended_at_trusted'} <= cols
        job_cols = {r['column_name'] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='scheduled_job_health'")}
        assert 'last_success_at' in job_cols
        # The pre-downgrade SUCCESS run's last_success_at is correctly
        # re-backfilled on re-upgrade, not left NULL.
        exc_job = conn.execute("SELECT * FROM scheduled_job_health WHERE job_name='exception_reconciliation'").fetchone()
        assert exc_job['last_status'] == 'SUCCESS'
        assert exc_job['last_success_at'] is not None
