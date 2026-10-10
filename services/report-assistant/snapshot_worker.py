"""Standalone TEST snapshot producer. Never starts the MES app or its jobs."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import logging
import os
import secrets
import time
from zoneinfo import ZoneInfo

from snapshot_store import SCHEMA, days, employee_cells, publish

ZONE = ZoneInfo('Asia/Ho_Chi_Minh')
DIRECTORY = os.environ.get('REPORT_SNAPSHOT_DIR', '/snapshots')
SESSION_FIELDS = ('session_id', 'employee_id', 'operation_id', 'po_id', 'part_id',
                  'employee_code', 'employee_name', 'po_code', 'operation_code',
                  'status', 'started_at', 'ended_at', 'good_qty', 'defect_qty',
                  'rework_qty', 'duration_seconds', 'excluded_from_reports')
PRODUCTIVITY_FIELDS = ('session_id', 'employee_id', 'employee_code', 'employee_name',
                       'po_code', 'part_code', 'operation_code', 'started_at', 'ended_at',
                       'good_qty', 'defect_qty', 'actual_seconds', 'expected_seconds',
                       'completion_percent')
EXCEPTION_FIELDS = ('exception_code', 'severity', 'workflow_status', 'exception_message')


def select(row, fields):
    value = {key: format_datetime(row[key].astimezone(timezone.utc), usegmt=True)
             if isinstance(row.get(key), datetime) else row.get(key) for key in fields}
    if 'started_at' in fields:
        value['_started_at'] = row['started_at'].isoformat()
    return value


def bounded(rows, cap):
    if len(rows) >= cap: raise ValueError('source cap reached; refusing incomplete snapshot')
    return rows


def local_day(value):
    return value.astimezone(ZONE).date().isoformat()


def stamp(now):
    return {'schema': SCHEMA, 'generated_at': now.isoformat(), 'watermark': now.isoformat()}


def build_reports(repo, fetch, now):
    """One consistent transaction, fixed horizon and bounded source rows."""
    today = now.astimezone(ZONE).date()
    start, end = (today - timedelta(days=92)).isoformat(), today.isoformat()
    partitions = {day: {'sessions': [], 'productivity': [], 'employees': []} for day in days(start, end)}
    sessions = bounded(repo.session_management(date_from=start, date_to=end, limit=10000)['items'], 10000)
    result = repo.employee_productivity_sessions(start, end, limit=20000, raw_scores=True)
    if result['truncated']: raise ValueError('productivity cap reached')
    for row in sessions:
        partitions[local_day(row['started_at'])]['sessions'].append(select(row, SESSION_FIELDS))
    for row in result['sessions']:
        partitions[local_day(row['ended_at'])]['productivity'].append(select(row, PRODUCTIVITY_FIELDS))
    for partition in partitions.values():
        partition['employees'] = employee_cells(partition['productivity'])
    # These are the authoritative current values used by production_order();
    # no new progress formula and no QC/user/activity payload is retained.
    pos = {str(row['id']): {'production_order': row, 'parts': [], 'operations': []}
           for row in bounded(fetch('SELECT id,code FROM production_orders ORDER BY id LIMIT 2001'), 2001)}
    for row in bounded(fetch('SELECT id,production_order_id,code,planned_quantity FROM parts ORDER BY id LIMIT 10001'), 10001):
        pos[str(row['production_order_id'])]['parts'].append(row)
    operations = {}
    for row in bounded(fetch('SELECT id,production_order_id,part_id,code,status,done_qty FROM operations ORDER BY id LIMIT 20001'), 20001):
        operations[str(row['id'])] = row
        pos[str(row['production_order_id'])]['operations'].append(row)
    exceptions = {}
    session_ids = {row['session_id'] for row in sessions}
    # Repository detection is read-only. Never invoke auto_ignore or the web
    # /session-exceptions route, whose before-read workflow mutates records.
    for row in bounded(repo.session_exceptions(inbox_only=False, limit=5000), 5000):
        if row['session_id'] in session_ids:
            exceptions.setdefault(str(row['session_id']), []).append(select(row, EXCEPTION_FIELDS))
    return {**stamp(now), 'days': partitions, 'pos': pos, 'operations': operations, 'exceptions': exceptions}


def build_active(repo, now):
    rows = bounded(repo.session_management(status='OPEN', limit=10000)['items'], 10000)
    return {**stamp(now), 'sessions': [select(row, SESSION_FIELDS) for row in rows if not row.get('excluded_from_reports')]}


@contextmanager
def readonly_source():
    """Database-enforced read-only transaction, shared by repository helpers.

    The worker has one thread. Patching only this process's transaction adapter
    preserves existing repository SQL while giving the batch one DB snapshot.
    The deployed credential must also have SELECT-only grants (defence in depth).
    """
    # Core config requires a secret in production even for repository imports.
    # This process never serves/signs sessions; do not load the app's real key.
    os.environ.setdefault('MESFLOW_SECRET_KEY', secrets.token_urlsafe(32))
    import psycopg
    from psycopg.rows import dict_row
    from mesflow.db import connection
    from mesflow.db.repositories.analytics import ReportRepository
    original = connection.transaction
    with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=5,
                         options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000 -c transaction_timeout=25000') as conn:
        conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL TIME ZONE 'UTC'")
        assert conn.execute('SHOW transaction_read_only').fetchone()['transaction_read_only'] == 'on'
        @contextmanager
        def shared():
            yield conn
        connection.transaction = shared
        try:
            yield ReportRepository(), connection.fetch_all
        finally:
            connection.transaction = original
            conn.rollback()


def main():
    from scope_auth import start_scope_server
    start_scope_server()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    next_reports = 0
    while True:
        started = time.monotonic()
        try:
            with readonly_source() as (repo, fetch):
                active = build_active(repo, datetime.now(timezone.utc))
            publish(DIRECTORY, 'active.json', active)
            if started >= next_reports:
                with readonly_source() as (repo, fetch):
                    reports = build_reports(repo, fetch, datetime.now(timezone.utc))
                publish(DIRECTORY, 'reports.json', reports)
                next_reports = started + 60
            logging.info('snapshot_refresh_ok elapsed_seconds=%.3f', time.monotonic() - started)
        except Exception as error:
            # Never log DSNs, SQL, values or exception messages from drivers.
            logging.error('snapshot_refresh_failed kind=%s', type(error).__name__)
        time.sleep(max(1, 20 - (time.monotonic() - started)))


if __name__ == '__main__':
    main()
