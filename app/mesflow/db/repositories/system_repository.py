from mesflow.db.connection import fetch_all, fetch_one


class SystemRepository:
    def database_info(self):
        return fetch_one("""
            SELECT current_database() database,
                   current_user username,
                   current_setting('server_version') server_version,
                   pg_database_size(current_database()) database_bytes,
                   now() server_time
        """)

    def schema_version(self):
        row = fetch_one("SELECT value FROM system_meta WHERE key='schema_version'")
        return row['value'] if row else None

    def readiness(self):
        return fetch_one("SELECT 1 AS ready, now() AS checked_at")

    def db_timezone(self):
        """The PostgreSQL session's own `timezone` GUC -- for
        observability only. MESFlow's own business
        calendar logic never reads this: TIMESTAMPTZ columns are stored in
        UTC internally regardless of this setting, and every business-facing
        conversion goes through core.time_policy.site_zone(), which is
        pinned to MESFLOW_TIMEZONE/settings.timezone_name, never to
        whatever this GUC (or the host/container OS locale) happens to be
        set to."""
        row = fetch_one("SELECT current_setting('TimeZone') AS tz")
        return row.get('tz') if row else None

    def table_counts(self):
        tables = (
            'users','employees','stations','equipment','sales_orders',
            'production_orders','parts','operations','templates',
            'kiosk_identities','work_sessions','qc_inspections',
            'operation_adjustments','penalty_tickets','kiosk_events',
            'notifications','audit_logs','action_logs'
        )
        result = {}
        for table in tables:
            row = fetch_one(f'SELECT COUNT(*) AS n FROM {table}')
            result[table] = int(row['n'])
        return result

    def connection_stats(self):
        return fetch_one("""
            SELECT COUNT(*) FILTER (WHERE datname=current_database()) AS total,
                   COUNT(*) FILTER (WHERE datname=current_database() AND state='active') AS active,
                   COUNT(*) FILTER (WHERE datname=current_database() AND state='idle') AS idle
            FROM pg_stat_activity
        """)

    def migration_head(self):
        row = fetch_one("SELECT version_num FROM alembic_version LIMIT 1")
        return row['version_num'] if row else None
