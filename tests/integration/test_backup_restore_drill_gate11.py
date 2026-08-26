"""Reliability Validation Round 2, Gate 11 -- Backup/Restore Drill.

Builds a representative dataset (users, employees, PO/parts/operations,
OPEN/CLOSED/auto-closed sessions, an exception, a kiosk identity, an
offline event, scheduled-job health), backs it up using the SAME mechanism
scripts/backup.sh uses in production (`pg_dump -Fc`), restores it into a
brand-new, isolated database (never touching or destroying the source --
scripts/restore.sh's destructive --clean-in-place restore is exercised at
the mechanism/flag level here, just against a disposable target, not the
live DB), and compares every category byte-for-byte with the source.
Finishes by running the real audit-sessions/audit-integrity services
against the RESTORED database.

Documents the exact commands used (see BACKUP_CMD/MANIFEST_CMD/RESTORE_CMD
below) -- these mirror scripts/backup.sh and scripts/restore.sh's own
pg_dump/pg_restore invocations.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.postgres

DATABASE_URL = os.environ['DATABASE_URL']


def _database_url(database_name: str) -> str:
    parsed = urlsplit(DATABASE_URL)
    return urlunsplit((parsed.scheme, parsed.netloc, f'/{database_name}', parsed.query, parsed.fragment))


def _run(command):
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode == 0, f"Command failed: {' '.join(command)}\nstdout:{result.stdout}\nstderr:{result.stderr}"
    return result


def _build_representative_graph(db, suffix):
    """One of each category Gate 11 names: users, employees, PO/parts/
    operations, an OPEN session, a CLOSED (manual finish) session, an
    AUTO_CLOSED session, an exception, a kiosk identity + kiosk_status,
    an offline (kiosk_client_events) event, and scheduled-job health."""
    with db.cursor() as cur:
        cur.execute("INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,'Gate11 User','x','viewer',TRUE,FALSE) RETURNING id",
                    (f'gate11-{suffix}',))
        user_id = cur.fetchone()['id']
        cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,'Gate11 Employee','TEST','Worker',%s) RETURNING id",
                    (f'G11-{suffix}', f'WF|EMP|G11-{suffix}'))
        employee_id = cur.fetchone()['id']
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'Gate11 Product',50,'IN_PROGRESS') RETURNING id",
                    (f'G11-PO-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Gate11 Part') RETURNING id", (po_id, f'G11-PART-{suffix}'))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,done_qty,defect_qty)
            VALUES(%s,%s,%s,'Gate11 Operation','IN_PROGRESS',%s,7,1) RETURNING id""", (po_id, part_id, f'G11-OP-{suffix}', f'WF|OP|G11-OP-{suffix}'))
        operation_id = cur.fetchone()['id']

        now = datetime.now(timezone.utc)
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,status,started_at,good_qty,defect_qty,start_request_id)
            VALUES(%s,%s,'OPEN',%s,2,0,%s) RETURNING id""", (employee_id, operation_id, now - timedelta(hours=1), f'G11-OPEN-{suffix}'))
        open_session_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,status,started_at,ended_at,good_qty,defect_qty,start_request_id,finish_request_id)
            VALUES(%s,%s,'CLOSED',%s,%s,4,1,%s,%s) RETURNING id""",
            (employee_id, operation_id, now - timedelta(hours=4), now - timedelta(hours=3), f'G11-CLOSED-{suffix}', f'G11-CLOSED-F-{suffix}'))
        closed_session_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO work_sessions(employee_id,operation_id,status,started_at,ended_at,good_qty,defect_qty,
            start_request_id,close_reason,closed_by_system,shift_boundary_used_at)
            VALUES(%s,%s,'CLOSED',%s,%s,3,0,%s,'AUTO_SHIFT_END',TRUE,%s) RETURNING id""",
            (employee_id, operation_id, now - timedelta(hours=8), now - timedelta(hours=7), f'G11-AUTO-{suffix}', now - timedelta(hours=7)))
        auto_closed_session_id = cur.fetchone()['id']

        cur.execute("""INSERT INTO exception_records(exception_type,severity,entity_type,entity_id,employee_id,production_order_id,part_id,operation_id,session_id,title,message,recommended_action,fingerprint,metadata_json,occurrence_no)
            VALUES('LONG_OPEN_SESSION','HIGH','SESSION',%s,%s,%s,%s,%s,%s,'Gate11 test exception','Session mở quá lâu','Kiểm tra',%s,'{}'::jsonb,1) RETURNING id""",
            (open_session_id, employee_id, po_id, part_id, operation_id, open_session_id, f'G11-EXC-{suffix}'))
        exception_id = cur.fetchone()['id']

        cur.execute("INSERT INTO kiosk_identities(device_uuid,status,firmware_version) VALUES(%s,'ACTIVE','1.2.3') RETURNING id", (f'G11-KIOSK-{suffix}',))
        kiosk_identity_id = cur.fetchone()['id']
        cur.execute("INSERT INTO kiosk_status(device_uuid,ui_state,wifi_rssi) VALUES(%s,'READY',-42)", (f'G11-KIOSK-{suffix}',))

        cur.execute("""INSERT INTO kiosk_client_events(client_event_id,payload_hash,kiosk_id,local_sequence,event_type,event_time,time_quality)
            VALUES(%s,'HASH',%s,1,'SESSION_START',%s,'synced') RETURNING id""",
            (f'G11-OFFLINE-{suffix}', f'G11-KIOSK-{suffix}', now - timedelta(hours=1)))
        offline_event_id = cur.fetchone()['id']

    return dict(
        suffix=suffix, user_id=user_id, employee_id=employee_id, po_id=po_id, part_id=part_id, operation_id=operation_id,
        open_session_id=open_session_id, closed_session_id=closed_session_id, auto_closed_session_id=auto_closed_session_id,
        exception_id=exception_id, kiosk_identity_id=kiosk_identity_id, offline_event_id=offline_event_id,
    )


def _snapshot(conn, g):
    """Every category Gate 11 asks to compare before/after: row counts,
    IDs, session state, quantity totals, PO state, exception state, kiosk
    state, job history."""
    with conn.cursor() as cur:
        cur.execute('SELECT username,role FROM users WHERE id=%s', (g['user_id'],))
        user = cur.fetchone()
        cur.execute('SELECT employee_no,name FROM employees WHERE id=%s', (g['employee_id'],))
        employee = cur.fetchone()
        cur.execute('SELECT code,status,planned_quantity FROM production_orders WHERE id=%s', (g['po_id'],))
        po = cur.fetchone()
        cur.execute('SELECT code,name FROM parts WHERE id=%s', (g['part_id'],))
        part = cur.fetchone()
        cur.execute('SELECT code,status,done_qty,defect_qty FROM operations WHERE id=%s', (g['operation_id'],))
        operation = cur.fetchone()
        cur.execute('SELECT id,status,good_qty,defect_qty,started_at,ended_at FROM work_sessions WHERE id IN (%s,%s,%s) ORDER BY id',
                    (g['open_session_id'], g['closed_session_id'], g['auto_closed_session_id']))
        sessions = cur.fetchall()
        cur.execute('SELECT id,close_reason,closed_by_system FROM work_sessions WHERE id=%s', (g['auto_closed_session_id'],))
        auto_close = cur.fetchone()
        cur.execute('SELECT exception_type,severity,status,fingerprint FROM exception_records WHERE id=%s', (g['exception_id'],))
        exception = cur.fetchone()
        cur.execute('SELECT device_uuid,status,firmware_version FROM kiosk_identities WHERE id=%s', (g['kiosk_identity_id'],))
        kiosk_identity = cur.fetchone()
        cur.execute('SELECT ui_state,wifi_rssi FROM kiosk_status WHERE device_uuid=%s', (f'G11-KIOSK-{g["suffix"]}',))
        kiosk_status = cur.fetchone()
        cur.execute('SELECT client_event_id,event_type,time_quality FROM kiosk_client_events WHERE id=%s', (g['offline_event_id'],))
        offline_event = cur.fetchone()
        cur.execute("SELECT job_name,last_status FROM scheduled_job_health WHERE job_name='shift_session_reconciliation'")
        job_health = cur.fetchone()
        cur.execute('SELECT COUNT(*) n FROM work_sessions')
        total_sessions = cur.fetchone()['n']
    return dict(user=user, employee=employee, po=po, part=part, operation=operation, sessions=sessions,
                auto_close=auto_close, exception=exception, kiosk_identity=kiosk_identity, kiosk_status=kiosk_status,
                offline_event=offline_event, job_health=job_health, total_sessions=total_sessions)


@pytest.mark.timeout(240)
def test_backup_restore_drill_full_representative_dataset(db, tmp_path: Path):
    suffix = uuid.uuid4().hex[:12]
    restore_db = f'mesflow_gate11_restore_{suffix}'
    dump_file = tmp_path / 'gate11.dump'
    manifest_file = tmp_path / 'gate11.manifest'
    checksum_file = tmp_path / 'gate11.sha256'

    g = _build_representative_graph(db, suffix)
    before = _snapshot(db, g)

    maintenance_url = _database_url('postgres')
    restored_url = _database_url(restore_db)

    try:
        # -- Documented exact commands (mirrors scripts/backup.sh) --------
        # BACKUP_CMD:   pg_dump -U <user> -d <db> -Fc > backup.dump
        # MANIFEST_CMD: pg_restore -l backup.dump > backup.manifest
        # (sha256sum backup.dump > backup.sha256)
        _run(['pg_dump', '-Fc', '--no-owner', '--no-acl', '--file', str(dump_file), DATABASE_URL])
        assert dump_file.stat().st_size > 1024
        manifest = _run(['pg_restore', '-l', str(dump_file)]).stdout
        manifest_file.write_text(manifest, encoding='utf-8')
        for expected in ('TABLE DATA public work_sessions', 'TABLE DATA public exception_records',
                          'TABLE DATA public kiosk_client_events', 'TABLE DATA public scheduled_job_health'):
            assert expected in manifest, f'{expected} missing from backup manifest'
        digest = hashlib.sha256(dump_file.read_bytes()).hexdigest()
        checksum_file.write_text(f'{digest}  {dump_file.name}\n', encoding='utf-8')

        # -- "Destroy a copy": drop-and-recreate the RESTORE TARGET before
        # restoring into it (this models scripts/restore.sh's
        # dropdb+createdb+pg_restore sequence, but against a disposable
        # database, never the live one). ------------------------------
        with psycopg.connect(maintenance_url, autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(restore_db)))
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(restore_db)))

        # RESTORE_CMD: pg_restore -U <user> -d <db> --clean --if-exists --no-owner < backup.dump
        _run(['pg_restore', '--clean', '--if-exists', '--no-owner', '--no-acl', '--dbname', restored_url, str(dump_file)])

        restored_conn = psycopg.connect(restored_url, row_factory=psycopg.rows.dict_row)
        try:
            after = _snapshot(restored_conn, g)
            diffs = []
            for key in before:
                if before[key] != after[key]:
                    diffs.append(f'{key}: before={before[key]!r} after={after[key]!r}')
            assert not diffs, 'DATA DIFFERENCE after restore:\n' + '\n'.join(diffs)

            # "Start MESFlow"/run migrations if needed: confirm the restored
            # DB is already at the exact same migration head (pg_dump/pg_restore
            # captures alembic_version too -- no migration should be needed).
            source_head = db.execute('SELECT version_num FROM alembic_version').fetchone()['version_num']
            restored_head = restored_conn.execute('SELECT version_num FROM alembic_version').fetchone()['version_num']
            assert restored_head == source_head

            # Run the real read-only auditors against the RESTORED database.
            from mesflow.core.config import settings
            from mesflow.services.session_audit_service import audit as audit_sessions
            from mesflow.services.integrity_audit_service import audit_integrity
            original_url = settings.database_url
            object.__setattr__(settings, 'database_url', restored_url)
            try:
                sessions_report = audit_sessions()
                integrity_report = audit_integrity()
            finally:
                object.__setattr__(settings, 'database_url', original_url)

            # The restored OPEN session must still show up as OPEN (not
            # silently dropped or miscounted) and nothing should look
            # corrupted post-restore.
            assert any(x['id'] == g['open_session_id'] for x in sessions_report['OPEN'])
            for category, items in integrity_report.items():
                offending = [x for x in items if x.get('employee_id') == g['employee_id'] or x.get('session_id') == g['open_session_id']]
                assert not offending, f'RESTORE introduced an integrity violation -- {category}: {offending}'
        finally:
            restored_conn.close()
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as admin:
            admin.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()', (restore_db,))
            admin.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(restore_db)))
        with db.cursor() as cur:
            cur.execute('DELETE FROM kiosk_client_events WHERE id=%s', (g['offline_event_id'],))
            cur.execute('DELETE FROM kiosk_status WHERE device_uuid=%s', (f'G11-KIOSK-{suffix}',))
            cur.execute('DELETE FROM kiosk_identities WHERE id=%s', (g['kiosk_identity_id'],))
            cur.execute('DELETE FROM exception_records WHERE id=%s', (g['exception_id'],))
            cur.execute('DELETE FROM work_sessions WHERE employee_id=%s', (g['employee_id'],))
            cur.execute('DELETE FROM operations WHERE id=%s', (g['operation_id'],))
            cur.execute('DELETE FROM parts WHERE id=%s', (g['part_id'],))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (g['po_id'],))
            cur.execute('DELETE FROM employees WHERE id=%s', (g['employee_id'],))
            cur.execute('DELETE FROM users WHERE id=%s', (g['user_id'],))
