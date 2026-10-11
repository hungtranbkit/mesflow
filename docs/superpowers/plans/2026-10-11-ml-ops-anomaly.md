# MESFlow operational anomaly adapter implementation plan

Goal: opt-in private backend/worker using PR #68's real IsolationForest with
numeric MESFlow session/OP/quantity features, baseline evidence and no business
writes. Execute inline per explicit user request; do not stop at planning.

Architecture: independent `mesflow.ml_ops` entrypoints, no registration in the
kiosk Flask app or existing compose. Fixed loopback ML endpoint, backend-only
key files, explicit operation scope and restricted SELECT credential. A batch
worker alone trains with explicit `--train`; scheduled runs only predict from
persisted models. Private atomic result snapshots served by a separate bounded
read-only API, never a train endpoint. One scope/service credential per pilot,
not a browser authentication replacement or multi-tenant service.

- [x] Test then implement finite numeric features, chronological holdout and
      median/MAD baseline with physical-unit evidence (elapsed time, not IoT).
- [x] Test then implement bounded authenticated PR #68 client, readonly SQL,
      private snapshot/control persistence, no-data and model-version gates.
- [x] Test then implement opt-in worker and scope-authenticated read-only API;
      no request-time train, rate limits, cooldown, failure/TTL handling.
- [x] Verify PostgreSQL scoped reads/write rejection on disposable DB; real
      gateway smoke with synthetic labels and held-out distribution/FPR.
- [ ] Run project gates/CI, review security and failure paths, document exact
      PASS/blocked evidence and rollback; commit, push and open PR.

Data: confirmed CLOSED, non-excluded, non-system-closed PRODUCTION sessions;
no employee identity, names, free text, shift mutation or order mutation.
Features: log1p elapsed seconds, log1p good+defect quantity, defect fraction.
Cohorts are operation IDs; do not mix unlike OPs. Historical samples are not
normal labels. Human labels are required for real false-positive measurement.
No real data training without an explicitly scoped readonly DSN. Failing that,
real assessment is blocked, not replaced with synthetic accuracy claims.
