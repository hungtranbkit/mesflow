# Private MESFlow operational anomaly adapter

Opt-in, backend-only pilot. It is not registered in MESFlow's Flask application,
nginx, kiosk compose or existing services. No production rollout is implied.
The gateway dependency is [PR #68](https://github.com/hungtranbkit/chatgpt-ai-gateway/pull/68)
(`efbe0e9`), fixed at **127.0.0.1:18788/v1/ml**. No external provider or LLM.

## What is measured

Confirmed CLOSED PRODUCTION sessions, excluding excluded/system-closed sessions,
setup/rework OPs and known QA/tutorial rows. Duration is **elapsed wall time**
between session start/end, including breaks; not active machine time, shift
performance or IoT sensor data. Quantity is declared good+defect, and defect
fraction is defect/(good+defect), defined as zero when quantity is zero.
No employee names, IDs, notes, PO codes or session/OP identifiers leave MESFlow
for the engine. The engine receives three ordered numbers per row:
`log_elapsed_seconds`, `log_total_qty`, `defect_fraction`.

Each explicitly approved operation ID has its own cohort/model. No mixing OPs,
product units or factories. Sessions for the same OP may involve multiple
employees; results are not employee performance scores. Minimum 100 valid unique sessions,
chronological 80/20 train/holdout, at least 80 training and 20 held-out rows;
equal end timestamps never cross the split. At least ten distinct training
vectors are required. History is 90 days, maximum 2,000 source rows across up to
four OPs. Exceeding limits fails closed; it does not silently truncate.

Real IsolationForest uses 64 trees, contamination .05 and gateway's fixed seed.
That .05 is a model parameter, **not** a measured failure probability or target
false-positive rate. Independent median/MAD rules use four robust standard
scales and practical floors of 60 seconds / two units / .02 fraction. Evidence
includes observed values, units, medians and baseline bounds. A finding is the
union of IF and baseline flags; an IF-only finding can have all marginal values
inside baseline bounds (a joint statistical pattern). Human review is required.
No automatic session, shift, quantity, production order or equipment action.

Snapshots record provenance `synthetic` or `real`, feature/schema versions,
model ID, training cutoff, held-out sample counts, distributions and flag
fractions. Real means operator-approved source provenance, not certified labels.
The view filters known QA/tutorial patterns, but source provenance still needs
operator review; heuristic exclusion cannot prove every row is real.
`false_positive_rate` stays null without human-reviewed normal labels. A flag
fraction is never reported as model accuracy. Historical training data is not
assumed to carry normal/anomaly labels.

## Permission boundary and installation

1. Use an isolated checkout/release and venv, install this repo's pinned
   `requirements.txt`. Do not reuse or restart the kiosk checkout/service.
2. A DBA must review `scripts/ml-ops-reader.sql`, select approved OP IDs, and
   provision a new non-superuser/no-create/no-bypass role with **only** SELECT on
   `public.mesflow_ml_ops_sessions`. The security-barrier view embeds those IDs
   and filters; the worker repeats the scope filter. Role limit one connection,
   default read-only. The worker rejects elevated roles, base-table SELECT or
   any public-table DML rights, including inherited grants. No migration/role
   provisioning is performed automatically. Never use an app/admin DSN.
3. Store the scoped DSN, a separate random read-service key (>=32 characters),
   and the approved private gateway key in distinct owner-only files (0600).
   Do not copy keys into frontend JS, query parameters, commits or command-line
   arguments. Config is 0600; state directory 0700, JSON 0600. Leaf symlinks for these files/directories are rejected.
4. Copy `config.example.json` outside the checkout; replace USER and example OP
   with approved absolute paths/scope. Keep `enabled:false` until approved.
   One config/read key/state directory is one workshop/scope. This is not a
   multi-tenant API and does not replace MES user/RBAC checks for future UI use.
   A future MES route must check current session/RBAC before proxying permitted
   facts. Do not publish this endpoint or send its data to public chat/AI.
5. Set `enabled:true` to opt in, then run one explicit training batch:

   ```sh
   PYTHONPATH=app /path/to/venv/bin/python -m mesflow.ml_ops.worker --config /private/config.json --train
   ```

   The worker issues REPEATABLE READ READ ONLY transactions, 3s connect/5s
   statement/0.5s lock limits. It does not boot Flask, seed users, migrate or
   invoke business HTTP endpoints. Error output is sanitized.
6. Subsequent scheduled batches omit `--train`. No automatic initial training,
   request-time training or silent retraining. Examples in this directory are
   **not installed/enabled automatically**; install under dedicated unit names
   only after reviewing paths/resource limits. Inference every five minutes;
   model expiry seven days; manual retraining at most once/24h/OP. A durable
   attempt timestamp is written before submission: ambiguous submit/timeouts
   are not retried. Failed/retired gateway models count toward PR #68's 16/key
   quota. Manage retention with the ML pilot owner; never delete active stores.
7. Launch the optional read service with `python -m mesflow.ml_ops.api --config
   /private/config.json`. Fixed **127.0.0.1:18789** only; two threads, 16
   connections, request body max 1KiB. `GET /v1/ops-anomalies` uses the separate
   Bearer read key. No query/body overrides, browser Origin or CORS, no train
   route. All responses no-store. Config/key are reread for every request:
   disabling, key rotation or scope changes revoke access immediately. New
   scope requires new state; previous-scope models/results cannot be served.

## Failure behavior, lifecycle and rollback

- Only the worker calls ML. Fixed loopback HTTP, no proxy environment, redirects
  or automatic retry. 12s socket timeout, 256KiB request/response limit, <=256
  prediction rows/call. Strict version/feature/model/source/is_mock checks;
  unknown/retired/missing models and gateway auth/quota/outage fail closed.
- One nonblocking file lock; minimum 300s between batches, persisted across
  process restarts. Control/results publish atomically with fsync. Max 2MiB/file; interrupted staging files are reaped under the worker lock.
  The example worker unit bounds total execution to 600s, memory 512MiB and CPU
  50%; API 128MiB/25%. Do not schedule overlapping workers on different hosts.
- Snapshots expire after 600s. Cold, corrupt, future or scope/version mismatch
  returns 503. A failed batch publishes `unavailable`, not an old success.
  Insufficient data/variation, model-required/expired and no-unseen-data are
  explicit cohort statuses, not fabricated normal readings. Only post-training
  observations are evaluated; changing historical data needs reviewed retrain.
- API limits: 30 authenticated reads/minute and 120 total attempts/minute per
  process; this is a single private process, not a distributed rate limiter.
- Models encode business-derived statistics. Keep gateway artifacts and local
  evidence private. OS account/DBA/gateway operator are trusted boundaries.
  Training changes ML artifacts, never MES business rows.
- Rollback: set config `enabled:false` (API immediately 503), stop only the
  dedicated adapter API and worker timer/worker. Leave kiosk, MES app, gateway
  :8788 and ML pilot :18788 untouched. Preserve scoped state for investigation,
  or securely remove only this pilot's files after review. Re-enable only with
  matching scope/key/contract and fresh results. Revoking the dedicated DB/view
  grants is a separate authorized DBA action. No business migration to undo.

## Verification

`pytest -q tests/test_ml_ops.py`; disposable Docker integration:
`tests/integration/test_ml_ops_reader.py`. Existing full PostgreSQL/Playwright CI
runs both. `scripts/ml-ops-smoke.py --engine-key-file /private/key --out /new/private/evidence`
uses labeled synthetic session fixtures with real ML HTTP train/poll/predict,
chronological held-out FPR/distribution evidence and read-only API checks. It
never provisions real DB access or restarts any existing service. An additional
actual loopback API smoke/disable/stop check is recorded in the delivery evidence.
