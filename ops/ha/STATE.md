# MESFlow HA State

- Updated: 2026-09-19 13:12 +07
- Current phase: Phase 4 - Gate 2 TEST Patroni takeover ready
- Last successful gates: Gate 0 PASS; Phase 1 pg_rewind prerequisite PASS; Gate 1 isolated Patroni takeover lab PASS
- Current live DB leader: TEST standalone Docker PostgreSQL (`mesflow-postgres`), not Patroni-managed yet
- Current live replica: HP `mesflow-ha-postgres-standby`
- DCS: etcd TEST + HP + m910, 3/3 healthy
- Live PostgreSQL system identifier: 7670577211936370723; timeline 1
- Live replication: async; `mesflow_hp_slot` active; streaming; observed lag_bytes=0
- Live data counts: 69 tables; operations=454; work_sessions=41
- Public app: ready 71.0.0.341; schema 72.0.11.0; migration 0054_multi_open_session_per_employee
- Fresh backup: mesflow-auto-20260919-125715.dump; service success; dump/globals/files SHA256 PASS
- HP offsite pull + restore verification: PASS
- pg_rewind prerequisite: PASS; TEST wal_log_hints=on, pg_rewind 17.10
- Gate 1 lab: PASS with Patroni 4.1.5; same lab system ID before/after adoption; no initdb; REST/patronictl/lifecycle/HBA/single-manager checks PASS
- Migration safety: existing `mesflow_hp_slot` pinned as permanent physical slot in Patroni bootstrap DCS config and restaged on TEST.
- Automatic failover: OFF
- Live TEST Patroni config/compose validated and image staged; exact rollback checkpoint written.
- Next: final preflight then controlled Gate 2 TEST takeover
