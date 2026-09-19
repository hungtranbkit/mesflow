# MESFlow HA Recovery / Rollback

## Phase 1 wal_log_hints rollback
- Pre-change: wal_log_hints=off, data_checksums=off, full_page_writes=on.
- Rollback copy: /opt/mesflow/runtime/backups/postgresql.auto.conf.pre-wal-log-hints-20260919-1300 (mode 600, root:root).
- Current verified state: wal_log_hints=on and replication healthy.

If PostgreSQL fails because of this setting:
1. Do not promote HP.
2. Ensure no second PostgreSQL manager is running.
3. If PostgreSQL starts, ALTER SYSTEM RESET wal_log_hints and restart only mesflow-postgres.
4. If it cannot start, restore the rollback postgresql.auto.conf copy to PGDATA and start only mesflow-postgres.
5. Verify TEST recovery=false, public ready=200, mesflow_hp_slot active, HP walreceiver=streaming.

Never roll back by copying an older database over newer PGDATA.
