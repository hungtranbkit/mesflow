# MESFlow HA Runbook

## Current normal state
- TEST is the writable PostgreSQL primary and public MESFlow app node.
- HP is an asynchronous physical standby.
- m910 is etcd witness only.
- Patroni has NOT taken ownership of either live PostgreSQL instance yet.

## Live paths
- TEST compose: /opt/mesflow/compose.yml
- TEST PGDATA manager: mesflow-postgres
- TEST runtime: /opt/mesflow/runtime
- HP standby: mesflow-ha-postgres-standby / volume mesflow-ha-postgres-data
- HP old stack must be preserved.

## Management rules
- Always use ssh -F /home/dell/.ssh/config.
- Never print secrets or full env files.
- Before Patroni takeover, Docker remains the PostgreSQL manager.
- After Patroni takeover, never restart PostgreSQL independently of Patroni.
- Automatic failover remains OFF until all required gates pass.

## Completed gates
- Gate 0 backup/restore/streaming/DCS: PASS 2026-09-19.
- Phase 1 pg_rewind prerequisite: PASS after wal_log_hints enabled and controlled DB restart.

## Next gate
- Gate 1: isolated Patroni existing-PGDATA takeover lab. No public routing, loopback-only ports, separate DCS scope.
