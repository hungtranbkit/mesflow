# MESFlow HA State

- Updated: 2026-09-19 13:12 +07
- Current phase: Phase 3 - live Patroni configuration design / pre-takeover audit
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
- Automatic failover: OFF
- Next: compare live PostgreSQL GUCs/config/connectivity against Patroni-managed settings, write live configs + rollback, then Gate 2 TEST takeover
