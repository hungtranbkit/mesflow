"""Fixed SELECT from a DBA-approved scoped view; never boot the MES application."""
from datetime import datetime, timedelta, timezone
from .domain import DataError

VIEW = 'public.mesflow_ml_ops_sessions'


def read_sessions(dsn, operations):
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(dsn,connect_timeout=3,row_factory=dict_row,
            options='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=500') as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        role=conn.execute('SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
        if not role or any(role.values()):raise DataError('restricted_reader_required')
        # Reject broad credentials, including inherited base-table SELECT/DML.
        privileges=conn.execute("""SELECT EXISTS (
          SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
          WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m') AND (
            has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE') OR
            (c.relname<>'mesflow_ml_ops_sessions' AND has_any_column_privilege(c.oid,'SELECT'))
          )) AS broad""").fetchone()
        if privileges['broad']:raise DataError('broad_database_privileges_denied')
        now=datetime.now(timezone.utc)
        rows=conn.execute('''SELECT session_id,operation_id,ended_at,duration_seconds,good_qty,defect_qty
          FROM public.mesflow_ml_ops_sessions
          WHERE operation_id=ANY(%s) AND ended_at >= %s AND ended_at <= %s
          ORDER BY ended_at,session_id LIMIT 2001''',(list(operations),now-timedelta(days=90),now)).fetchall()
        if len(rows)>2000:raise DataError('source_limit_exceeded')
        for row in rows:
            row['duration_seconds']=float(row['duration_seconds'])
            row['ended_at']=row['ended_at'].isoformat()
        conn.rollback()
        return rows
