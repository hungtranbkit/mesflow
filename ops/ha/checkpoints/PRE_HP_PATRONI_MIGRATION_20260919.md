# PRE HP Patroni Migration - 2026-09-19

## Preconditions
- Gate 2 PASS: TEST is Patroni Leader mesflow-test, timeline 2.
- Public MESFlow ready; HP physical standby streaming from TEST with zero/low lag.
- HP standby system identifier must equal 7670577211936370723.
- Existing HP standby container: mesflow-ha-postgres-standby.
- Existing HP standby volume: mesflow-ha-postgres-data.
- Patroni HP image must match TEST digest.
- Patroni HP config and compose must validate before standby stop.
- Old HP mesflow-postgres / mesflow-app and pre-replica archive are out of scope and must not be touched.

## Migration
1. Record HP recovery state, system identifier, receive/replay LSN and data counts.
2. Set mesflow-ha-postgres-standby restart policy to no.
3. Stop only mesflow-ha-postgres-standby cleanly.
4. With DB stopped, create clone volume mesflow-ha-postgres-data-prepatroni-20260919.
5. Start mesflow-patroni-hp using original mesflow-ha-postgres-data.
6. Require same system identifier, role Replica, recovery=true, REST /replica=200, /primary!=200, streaming WAL, acceptable lag, and two-member patronictl list.

## Exact rollback
1. Stop/remove mesflow-patroni-hp; verify it owns no PostgreSQL process.
2. Do not delete either the original volume or the pre-Patroni clone.
3. If original volume remains safely usable, restore standby container restart policy and start it; verify recovery=true and streaming.
4. If Patroni changed original volume incompatibly, create a new standby volume from mesflow-ha-postgres-data-prepatroni-20260919, repoint/recreate only the HA standby container from recorded settings, then verify recovery=true and streaming.
5. Never touch old HP application/database containers or pre-replica archive as part of this rollback.
6. Do not promote HP during rollback; TEST Patroni remains Leader.

Automatic failover remains OFF.
