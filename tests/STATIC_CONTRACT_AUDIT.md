# Static/String Contract Audit

Audit date: 2026-08-09. Scope: `tests/test_*.py` before the P3 migration.

- 52 files read/grep implementation source.
- 115 test functions were classified.
- A — UI behavior candidates: 52 tests. Keep temporarily until equivalent component/browser behavior exists.
- B — API/domain integration candidates: 30 tests. Migrate in P0 → P1 → P2 order.
- C — intentional static/package contracts: 33 tests. Keep for version synchronization, Linux/Docker/Nginx packaging, migration shape, no-SQLite policy and module/asset presence.

## Replaced in this change

Six redundant implementation-detail tests were removed after replacement by real PostgreSQL/HTTP coverage:

- `test_po_start_v6586.py`: four source-string assertions.
- `test_rework_flow_v65844.py`: two source-string assertions.

Their replacements are `integration/test_production_state_integrity.py`, `integration/test_production_consistency_p1.py`, and `integration/test_scheduling_time_p2.py`. These exercise authentication, HTTP routes, repositories, transactions, PostgreSQL state, idempotency, reconcile, audit/history and observable API results.

## Category A files

UI/dashboard/template/employee/QR/system-log source-copy contracts remain migration candidates. They are marked `static` today, not reported as behavioral coverage. Browser tests remain limited to critical journeys.

## Category B files

Production input dependency, ledger, kiosk compatibility/security, event, exception and reporting source contracts remain candidates for service/API integration. Critical P0/P1/P2 rules have already moved first.

## Category C rationale

Static assertions remain appropriate where the contract itself is static: synchronized release metadata, LF/Linux entrypoints, Docker/Nginx wiring, migration column/type constraints, absence of SQLite runtime paths, and required frontend module/asset inclusion.
