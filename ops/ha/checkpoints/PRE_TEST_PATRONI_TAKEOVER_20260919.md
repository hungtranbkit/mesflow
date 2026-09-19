# PRE TEST Patroni takeover checkpoint — 2026-09-19

## Gates
- Gate 0 backup/restore/DCS/streaming: PASS.
- Phase 1 pg_rewind prerequisite: PASS (`wal_log_hints=on`).
- Gate 1 isolated existing-PGDATA Patroni lab: PASS.
- Production Patroni DCS scope `/mesflow-ha/mesflow-pg` verified empty before takeover staging.

## Live TEST before takeover
- PostgreSQL 17.10, system identifier `7670577211936370723`, timeline 1.
- Current manager: container `mesflow-postgres`, image `postgres:17-alpine`, restart `unless-stopped`.
- PGDATA: bind `/opt/mesflow/runtime/postgres-v65` -> `/var/lib/postgresql/data`.
- Host PostgreSQL binding: `100.127.10.29:5432` only.
- Docker network alias used by app: `postgres` on `mesflow_network`.
- App DATABASE target: `postgres:5432/mesflow`.
- Public app: 71.0.0.341 / schema 72.0.11.0 / migration 0054.
- HP standby streaming async through `mesflow_hp_slot`; observed lag 0 bytes.

## Live settings intentionally preserved
- max_connections=100
- max_wal_senders=10
- max_replication_slots=10
- max_worker_processes=8
- max_slot_wal_keep_size=4096MB
- wal_keep_size=256MB
- wal_level=replica
- hot_standby=on
- wal_log_hints=on
- full_page_writes=on
- shared_buffers=163848kB (existing postgresql.conf; Patroni does not override)
- work_mem=4096kB (existing/default; Patroni does not override)
- archive_mode=off for this phase
- timezone=UTC, encoding=UTF8, database collation/ctype=en_US.utf8
- no shared_preload_libraries

## Patroni TEST runtime
- Image `mesflow-patroni:4.1.5-pg17.10`, image id `sha256:6c8799f07d252996d782ca781ca342fb2897e21455886d31ff7316d2d76e7651`.
- Config `/opt/mesflow/ha/patroni-test.yml` validated by Patroni.
- Compose `/opt/mesflow/ha/compose-patroni.yml` validated by Docker Compose.
- PostgreSQL bind remains `100.127.10.29:5432` only.
- Patroni REST binds host Tailscale only: `100.127.10.29:8008`.
- Container joins `mesflow_network` with alias `postgres` so application DB hostname does not change.
- Initial replication mode asynchronous; watchdog off pending fencing audit; automatic failover not enabled.
- Existing physical slot `mesflow_hp_slot` is declared as a permanent Patroni DCS slot (`type: physical`) during migration, so the working HP standby slot is preserved while HP is not yet a Patroni member.
- TEST initial takeover uses existing local trust HBA and existing roles; no credential values are added to git/logs.

## Exact takeover sequence
1. Verify public app, HP streaming, slot active, etcd 3/3, backup/restore evidence.
2. Stop `mesflow-app` to quiesce writes.
3. `docker update --restart=no mesflow-postgres`.
4. Record final live LSN/system identifier and stop `mesflow-postgres` cleanly.
5. Verify legacy DB is stopped and Tailscale port 5432 is free.
6. Start `/opt/mesflow/ha/compose-patroni.yml`.
7. Require Patroni leader lock, `/primary=200`, read/write PostgreSQL, unchanged system identifier, exactly one DB manager.
8. Require HP WAL receiver to reconnect/stream.
9. Start `mesflow-app`; require container health and public readiness 200.
10. If any acceptance check fails, execute rollback below; do not improvise promotion/failover.

## Exact rollback
1. Stop/remove Patroni TEST service: `sudo docker compose -f /opt/mesflow/ha/compose-patroni.yml down`.
2. Verify `mesflow-patroni-test` is absent/stopped and no PostgreSQL process owns the PGDATA.
3. Verify legacy `mesflow-postgres` remains stopped before restoring its restart policy.
4. `docker update --restart=unless-stopped mesflow-postgres`.
5. `docker start mesflow-postgres`; wait for healthy.
6. Verify TEST `pg_is_in_recovery=false`, system identifier unchanged, HP receiver streaming and slot active.
7. `docker start mesflow-app`; require public `/api/system/ready` 200.
8. Never copy an older backup over newer PGDATA as rollback.
