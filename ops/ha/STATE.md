# MESFlow HA State

- Updated: 2026-09-19 13:02 +07
- Current phase: Phase 2 - isolated Patroni takeover lab
- Last successful gates: Gate 0 PASS; Phase 1 pg_rewind prerequisite PASS
- Current DB leader: TEST standalone Docker PostgreSQL (not Patroni-managed yet)
- Current replica: HP physical standby
- DCS: etcd TEST + HP + m910, 3/3 healthy
- PostgreSQL system identifier: 7670577211936370723; timeline 1
- Replication: async; mesflow_hp_slot active; streaming; observed lag_bytes=0
- DB counts: 69 tables; operations=454; work_sessions=41
- Public app: ready 71.0.0.341; schema 72.0.11.0; migration 0054_multi_open_session_per_employee
- Fresh backup: mesflow-auto-20260919-125715.dump; service success; dump/globals/files SHA256 PASS
- HP offsite pull: PASS; fresh dump present
- HP restore verify: PASS; 0054_multi_open_session_per_employee|69|53 MB
- pg_rewind: PostgreSQL 17.10; wal_log_hints=on; data_checksums=off; full_page_writes=on
- Controlled DB restart: DB healthy after ~6s; app recovered; HP streaming resumed; lag 0
- Automatic failover: OFF
- Next: build pinned Patroni 4.1.5/PG17 image and prove isolated existing-PGDATA takeover before touching live PGDATA
