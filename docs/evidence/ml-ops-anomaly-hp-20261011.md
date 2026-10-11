# ML operations adapter — HP verification, 2026-10-11

Isolated worktree `mesflow-ml-ops-anomaly-20261011`, requested branch
`feat/ml-ops-anomaly-20261011`, based on main `3bbc630`.
Read AGENTS.md, PROJECT.yaml, docs/CURRENT_STATE.md and PROJECT_CONTEXT.md.
The referenced workspace AGENTS.md is absent; existing CURRENT_STATE historical
infrastructure notes do not override the explicit no-production/no-kiosk scope.

## PASS locally

- 36 focused tests: numeric/version/schema gates, chronological holdout,
  no-data/variation, physical baseline evidence, ownership/scope/key rotation,
  request auth/rates, TTL/corrupt/future snapshots, explicit-only training,
  persistent cooldown, single-writer locking, staging cleanup and failure
  invalidation. Gateway timeout/error responses are sanitized; mocks rejected.
- Real PostgreSQL disposable integration: fixed approved OP view, confirmed
  non-excluded sessions only; out-of-scope query empty; restricted reader cannot
  UPDATE even after disabling transaction read-only, cannot read users password
  hashes, and broad/elevated credentials rejected. Provisioning happened only
  in isolated `mesflow-ml-ops-20261011` compose DB; no live MESFlow DDL/DML.
- Project preflight PASS. Full project/remote CI results recorded in final PR.
- Real authenticated ML pilot at 127.0.0.1:18788 (gateway PR #68 `efbe0e9`),
  no process restart or configuration change. Synthetic training/prediction
  took 2.207s: 192 train rows, 48 chronologically held-out rows. Strict final
  manifest/algorithm/schema validation rechecked against the existing model
  without another training run.
- Held-out synthetic labels: 36 normal, 12 injected anomalies. Detected 12/12
  injected cases, **4/36 false positives (11.11%)**, combined flag fraction
  33.33%. This is the IF-or-baseline rule on this synthetic fixture only.
  No threshold tuning against the holdout and no production accuracy claim.
- Held-out elapsed seconds min/median/p95/max: 526.37 / 613.23 / 7200 / 7200;
  total good+defect qty: 18 / 22 / 240 / 241; defect fraction:
  0 / 0 / .5769 / .625. See adjacent JSON for precise values.
- Actual adapter HTTP process bound only 127.0.0.1:18789: missing/wrong key 401,
  authorized synthetic snapshot 200, disabled config 503, same-scope reenable
  200. Snapshot reads did not train/change models. Stopped only that child
  process and verified its port closed. Protected ML/kiosk unit PID/start
  timestamps and kiosk edge/report/support container IDs/start times unchanged.
  No frontend keys, production changes, external provider calls or business
  writes. Adapter is not installed as a persistent service.
- Independent review found early engine-key loading could retain a success
  snapshot after credential failure. Fixed with lazy construction inside locked
  invalidation; regression proves subsequent authorized read returns 503.
  Corrected cohort wording: an OP may include sessions from multiple employees;
  this is not an employee performance model. Review findings resolved.

## BLOCKED: real-data assessment / real adapter enablement

No approved adapter-specific readonly MESFlow credential/view and operation
scope were supplied. Existing kiosk/admin/replication credentials were not
repurposed. No human-reviewed real normal/anomaly labels were available.
Therefore no real-data training, real distribution or real false-positive rate
is claimed. The implementation, synthetic real-engine smoke and disposable DB
integration are independently verifiable without taking those permissions.
A real rollout requires the reviewed scoped view/reader and data-label review
in the runbook; enabling it is not an implied production deployment.

## Reproduce / rollback

[Runbook](../../services/ml-ops-anomaly/README.md) includes schema, scope,
limits, key files, explicit training, inference-only timer and rollback.
Set `enabled:false`, stop only dedicated adapter units; leave kiosk and gateway
services alone. ML artifacts from synthetic smoke remain in the private pilot
store under its existing quota; do not delete that running store. Read-service
credentials/state stay outside git in a private evidence directory.
Raw local proof: `/tmp/mesflow-ml-ops-evidence/` (integration.log, smoke.log,
http-proof.json, preflight.log, full-python.log). No secret/data export is
attached; only synthetic statistics are committed.
