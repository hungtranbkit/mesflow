"""0051's backfill, against data written under the OLD meaning of rework_qty.

The clean-DB upgrade path is covered by test_migration_matrix_blocker7. This
file covers the path that actually matters for the TEST/production upgrade:
rows that already exist, written while `rework_qty` absorbed both the
operator's declaration AND every repair resolved afterwards.

0051 has to unpick those two back apart, and the only trustworthy input is
rework_ledger -- append-only, one row per resolve, never rewritten. The
arithmetic is exact rather than a guess:

    repaired_qty := SUM(ledger.qty_reworked)
    rework_qty   := rework_qty - SUM(ledger.qty_reworked)

The awkward case is a row resolved THROUGH the inverted queue, where pieces
were "repaired" that had never been declared repairable at all (the old queue
offered a 5-NG / 0-repairable session for repair). For those the subtraction
goes negative, and the migration lifts the declaration to what was demonstrably
resolved instead. That branch is asserted here too, because it is the one that
cannot be re-derived if it goes wrong.
"""
from __future__ import annotations

import os
import subprocess
import uuid

import psycopg
import pytest
from psycopg.rows import dict_row

pytestmark = pytest.mark.postgres

APP_DIR = '/workspace/app'
BASE_DSN = os.environ.get('DATABASE_URL', 'postgresql://mesflow_test:mesflow_test_password@postgres-test:5432/mesflow_test')
BEFORE = '0050_user_session_epoch'
HEAD = '0051_repair_pending_semantics'


def _server_dsn(dbname: str) -> str:
    prefix, _, _ = BASE_DSN.rpartition('/')
    return f'{prefix}/{dbname}'


def _alembic(*args: str, database_url: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env['DATABASE_URL'] = database_url
    return subprocess.run(['alembic', *args], cwd=APP_DIR, env=env, capture_output=True, text=True)


@pytest.fixture()
def scratch_db():
    name = f'mesflow_repair_backfill_{uuid.uuid4().hex[:12]}'
    with psycopg.connect(_server_dsn('postgres'), autocommit=True, row_factory=dict_row) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    dsn = _server_dsn(name)
    try:
        yield dsn
    finally:
        with psycopg.connect(_server_dsn('postgres'), autocommit=True, row_factory=dict_row) as admin:
            admin.execute(f'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s', (name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{name}"')


def _seed_old_world(conn, *, suffix):
    """A PO/Part/Operation/employee graph plus sessions in 0050's shape."""
    po = conn.execute("INSERT INTO production_orders(code,product,planned_quantity,status) "
                      "VALUES(%s,'P',100,'IN_PROGRESS') RETURNING id", (f'MIG-PO-{suffix}',)).fetchone()['id']
    part = conn.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Part') RETURNING id",
                        (po, f'MIG-PART-{suffix}')).fetchone()['id']
    op = conn.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
                         VALUES(%s,%s,%s,'OP','IN_PROGRESS',%s) RETURNING id""",
                      (po, part, f'MIG-OP-{suffix}', f'WF|OP|MIG-OP-{suffix}')).fetchone()['id']
    # is_rework_op is a GENERATED column since the operation_type convergence --
    # it derives from operation_type and cannot be written directly.
    bench = conn.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,
                              operation_type,sort_order)
                            VALUES(%s,%s,%s,'SỬA HÀNG','PLANNED',%s,'REWORK',2147483647) RETURNING id""",
                         (po, part, f'MIG-RW-{suffix}', f'WF|OP|MIG-RW-{suffix}')).fetchone()['id']
    emp = conn.execute("INSERT INTO employees(employee_no,name,qr) VALUES(%s,'W',%s) RETURNING id",
                       (f'MIG-E-{suffix}', f'WF|EMP|MIG-E-{suffix}')).fetchone()['id']
    return po, part, op, bench, emp


def _session(conn, *, emp, op, good, defect, rework, scrap, tag):
    return conn.execute("""INSERT INTO work_sessions(employee_id,operation_id,status,started_at,ended_at,
            good_qty,defect_qty,rework_qty,scrap_qty,start_request_id,finish_request_id)
        VALUES(%s,%s,'CLOSED',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (emp, op, good, defect, rework, scrap, f'MIG-S-{tag}', f'MIG-F-{tag}')).fetchone()['id']


def _ledger(conn, *, source_session, source_op, bench_session, bench_op, emp, reworked, scrapped):
    conn.execute("""INSERT INTO rework_ledger(source_session_id,source_operation_id,rework_session_id,
            rework_operation_id,employee_id,qty_reworked,qty_scrapped) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
        (source_session, source_op, bench_session, bench_op, emp, reworked, scrapped))


def test_backfill_splits_the_declaration_from_the_repairs(scratch_db):
    assert _alembic('upgrade', BEFORE, database_url=scratch_db).returncode == 0

    suffix = uuid.uuid4().hex[:8].upper()
    with psycopg.connect(scratch_db, autocommit=True, row_factory=dict_row) as conn:
        po, part, op, bench, emp = _seed_old_world(conn, suffix=suffix)

        # Every row below is a state 0050 could actually REACH -- its own
        # CHECK (rework_qty + scrap_qty <= defect_qty) rejects anything else,
        # so seeding an impossible row would prove nothing about a real upgrade.

        # A. Never resolved. rework_qty is purely the operator's declaration:
        #    10 NG, 6 declared repairable. Must survive untouched.
        untouched = _session(conn, emp=emp, op=op, good=90, defect=10, rework=6, scrap=0, tag=f'A{suffix}')

        # B. Declared 6 repairable, then the bench repaired 3 and scrapped 1.
        #    0050 stored rework_qty = 6 + 3 = 9 (declaration + repairs) and
        #    scrap_qty = 1, and credited the 3 repaired pieces to good.
        resolved = _session(conn, emp=emp, op=op, good=93, defect=10, rework=9, scrap=1, tag=f'B{suffix}')
        b_bench = _session(conn, emp=emp, op=bench, good=0, defect=0, rework=0, scrap=0, tag=f'BB{suffix}')
        _ledger(conn, source_session=resolved, source_op=op, bench_session=b_bench, bench_op=bench,
                emp=emp, reworked=3, scrapped=1)

        # C. The inverted-queue casualty: 5 NG, NONE declared repairable, yet
        #    the old queue listed the session anyway (it selected on
        #    defect > rework + scrap) and 2 were repaired. Subtracting the
        #    ledger goes to 0 < 2, so the declaration has to be lifted to what
        #    was demonstrably resolved rather than left below it.
        inverted = _session(conn, emp=emp, op=op, good=95, defect=5, rework=2, scrap=0, tag=f'C{suffix}')
        c_bench = _session(conn, emp=emp, op=bench, good=0, defect=0, rework=0, scrap=0, tag=f'CB{suffix}')
        _ledger(conn, source_session=inverted, source_op=op, bench_session=c_bench, bench_op=bench,
                emp=emp, reworked=2, scrapped=0)

    assert _alembic('upgrade', HEAD, database_url=scratch_db).returncode == 0

    with psycopg.connect(scratch_db, autocommit=True, row_factory=dict_row) as conn:
        rows = {r['id']: r for r in conn.execute(
            'SELECT id,good_qty,defect_qty,rework_qty,repaired_qty,scrap_qty FROM work_sessions').fetchall()}

        a = rows[untouched]
        assert (a['defect_qty'], a['rework_qty'], a['repaired_qty'], a['scrap_qty']) == (10, 6, 0, 0), \
            'a never-resolved session has nothing to unpick and must not be touched'

        b = rows[resolved]
        assert b['repaired_qty'] == 3, 'repaired pieces come from the ledger'
        assert b['rework_qty'] == 6, 'the declaration is 9 - 3, the value the operator actually typed'
        assert b['scrap_qty'] == 1, 'bench scrap already had the new meaning; no backfill needed'
        assert b['rework_qty'] - b['repaired_qty'] - b['scrap_qty'] == 2, 'Chờ sửa = 6 - 3 - 1'

        c = rows[inverted]
        assert c['repaired_qty'] == 2
        assert c['rework_qty'] == 2, 'lifted to what was resolved, never negative'
        assert c['rework_qty'] - c['repaired_qty'] - c['scrap_qty'] == 0

        # Every row must satisfy the new CHECKs -- if the backfill were wrong
        # the constraints below would have refused to be created at all, but
        # assert the property directly so the reason is legible.
        bad = conn.execute("""SELECT COUNT(*) n FROM work_sessions
            WHERE rework_qty > defect_qty OR repaired_qty + scrap_qty > rework_qty""").fetchone()['n']
        assert bad == 0

        # The Operation aggregate is rebuilt in the same migration, so the
        # Tổng quan number is right immediately, not after the next write.
        # Note the seeded operations row was left at all-zeros on purpose --
        # a lagging aggregate is a state 0044 explicitly allows, and rebuilding
        # only the three repair columns against a stale defect_qty tripped
        # ck_operations_rework_le_defect and aborted the whole upgrade.
        operation = conn.execute(
            'SELECT done_qty,defect_qty,rework_qty,repaired_qty,scrap_qty FROM operations WHERE id=%s', (op,)).fetchone()
        assert operation['defect_qty'] == 10 + 10 + 5, 'done/defect rebuilt too, so the row is self-consistent'
        assert (operation['rework_qty'], operation['repaired_qty'], operation['scrap_qty']) == (6 + 6 + 2, 3 + 2, 1)
        pending = operation['rework_qty'] - operation['repaired_qty'] - operation['scrap_qty']
        assert pending == 8, f'6 chưa xử lý (A) + 2 còn lại (B) + 0 (C), đang là {pending}'


def test_downgrade_restores_the_old_shape(scratch_db):
    """Rollback has to be real: a deploy that cannot go back is not shippable."""
    assert _alembic('upgrade', BEFORE, database_url=scratch_db).returncode == 0
    suffix = uuid.uuid4().hex[:8].upper()
    with psycopg.connect(scratch_db, autocommit=True, row_factory=dict_row) as conn:
        po, part, op, bench, emp = _seed_old_world(conn, suffix=suffix)
        sid = _session(conn, emp=emp, op=op, good=93, defect=10, rework=9, scrap=1, tag=f'D{suffix}')
        bsid = _session(conn, emp=emp, op=bench, good=0, defect=0, rework=0, scrap=0, tag=f'DB{suffix}')
        _ledger(conn, source_session=sid, source_op=op, bench_session=bsid, bench_op=bench,
                emp=emp, reworked=3, scrapped=1)

    assert _alembic('upgrade', HEAD, database_url=scratch_db).returncode == 0
    down = _alembic('downgrade', BEFORE, database_url=scratch_db)
    assert down.returncode == 0, down.stdout + down.stderr

    with psycopg.connect(scratch_db, autocommit=True, row_factory=dict_row) as conn:
        cols = {r['column_name'] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='work_sessions'")}
        assert 'repaired_qty' not in cols
        row = conn.execute('SELECT rework_qty,scrap_qty FROM work_sessions WHERE id=%s', (sid,)).fetchone()
        assert (row['rework_qty'], row['scrap_qty']) == (9, 1), \
            'downgrade folds repaired pieces back into rework_qty, restoring 0050 exactly'

    reup = _alembic('upgrade', HEAD, database_url=scratch_db)
    assert reup.returncode == 0, reup.stdout + reup.stderr
    with psycopg.connect(scratch_db, autocommit=True, row_factory=dict_row) as conn:
        row = conn.execute('SELECT rework_qty,repaired_qty,scrap_qty FROM work_sessions WHERE id=%s',
                           (sid,)).fetchone()
        assert (row['rework_qty'], row['repaired_qty'], row['scrap_qty']) == (6, 3, 1)
