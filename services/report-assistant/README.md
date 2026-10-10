# MESFlow report assistant

Standalone read-only service for `/reports` and `/reports-api/*`. It does not
replace the MES app, import its session signing key, or connect to its database.
A separate background worker uses a dedicated SELECT-only database role.
The root support dialog links here for report requests. No migrations.

## Security and semantics

- Anonymous `demo` always uses clearly labeled fixed sample rows; it never calls
  a business API. `live` requires the existing signed MES session. Each preview
  and download asks `/api/auth/me` again and applies the existing permissions
  plus the session endpoints' role restriction. Password-change-required users
  are denied. No service account or bearer token is used to fetch reports.
- Only `/api/auth/me` can be requested from `mesflow-app:8080`; the session
  cookie is forwarded solely for session/RBAC checks. A private live role check
  also rejects stale login-role claims after account changes. Business source
  reads are served by the private snapshot adapter, never by request-time HTTP.
  The deployment is a single workshop: there is no claimed multi-tenant feature.
  Clients cannot select a tenant, database, URL, user identity or SQL; snapshot
  ownership is checked against the current authenticated user ID.
- AI receives ONLY candidate report-type enums, public type definitions and a
  period enum. Local deterministic extraction handles text, explicit dates and
  numeric IDs. Raw questions, actual IDs, rows and sessions never leave MESFlow.
  Gateway schema and actual non-Claude/non-mock provider are validated, using
  `facebook-chat` at the verified real gateway. Rules fallback is labeled.
  Unsupported or missing filters require UI confirmation; no model prose/SQL
  executes. This is constrained intent classification, not an unrestricted agent.
- Dates: 1–31 days; 500 rows maximum, no silent truncation; 20 employees for
  detail projection and 20 sessions for exceptions. Productivity uses CLOSED
  session end dates; operation/exception activity uses session start dates,
  Asia/Ho_Chi_Minh. PO planned/done/status columns are explicitly CURRENT values;
  only `*_in_period` columns apply dates/employee filters. Scores come from
  existing report APIs. Operation codes are scoped by parent PO too.
- Never call `/api/session-exceptions`: that GET has auto-ignore write effects.
  Exceptions instead read `/api/session-management/<id>` and include current
  and historical exception records. No business writes or mutations.
- Max JSON 2 KiB / question 500 characters; same-origin POST checks; 6 intent
  or preview requests/min/user (anonymous IP); two concurrent previews;
  bounded API reads/timeouts; 20 AI attempts/hour and five-minute intent cache.
  Download grants last five minutes, max 3/user and 30 globally. Downloads recheck
  identity/RBAC, max 3/snapshot and 10/min/user. One worker keeps in-memory
  limits coherent. Restart clears download grants and rate budgets; private
  precomputed source files persist.
- Excel and UTF-8 BOM CSV use the exact preview snapshot, with source/filter
  metadata, formula-safe cells and SHA-256 verified by the browser. Server audit
  records user, filters, count and download hash, never rows/prompt/cookies/key;
  audit failures block downloads. Audit means granted/generated, not proof the
  user saved the file. Native PDF uses WeasyPrint 66 in a subprocess (one at a time, 12s,
  200 rows/1MB input). All URLs/files are denied by its resource fetcher.
  Browser Print/Save PDF remains a separate fallback.


## Precomputed snapshots (#45)

`Dockerfile.worker` starts only `snapshot_worker.py`, never Flask, migrations,
seeding or MES background jobs. The worker reuses `ReportRepository` queries
inside a single PostgreSQL REPEATABLE READ READ ONLY transaction per batch,
with 5s statement / 1s lock / 25s transaction timeouts. The credential has SELECT
only on the source tables and four user-scope columns (`id`, `role`, `active`,
`must_change_password`). It cannot read password, name or username columns
from `users`, or audit tables. The report service has no database credential.
Snapshot JSON is private (directory
0700, files 0600, UID 65534), mounted read-only into reports, with no nginx alias
or public file endpoint. This is the current single-workshop authorization
model, not tenant isolation: clients cannot override scope, tenant or database.

- Active sessions refresh every 20s (TTL 60s); reports every 60s (TTL 150s).
  Daily partitions cover the latest 93 business dates in Asia/Ho_Chi_Minh,
  including today/yesterday/week/month windows before any question is asked.
  Custom 1–31 day ranges and allowed entity filters combine those partitions.
  Older dates return 422, never an unbounded synchronous historical rebuild.
- Daily employee cells retain unrounded database score sums/counts and duration
  sums. Merge first, round last, matching the existing productivity SQL AVG and
  bigint duration. Filtered productivity retains the assistant's existing
  per-session rounded-score semantics. No AI SQL or new KPI definition.
- Operation/session facts partition on start date; productivity facts on end
  date. PO/Part/OP planned/done/status remain explicitly CURRENT values. A
  worker restart rebuilds automatically without a question. Cold, corrupt,
  unknown-schema, future-dated or expired sources return 503 with retry text;
  they never fall back to rebuilding through live business APIs.
- Current-role security: the existing backend `/api/auth/me` returns the role
  stored in the signed login, even after `UserRepository.update_profile` changes
  the database role. Therefore reports additionally call the worker's private
  `/scope/<user_id>` checker for every authenticated operation. It reads only
  the four allowed columns in a read-only 1.5s-bounded query; changed role,
  inactive/missing user or required password change denies access. Role grants
  are still reread by the backend. Failure of either check fails closed. No
  changes to the MES app, session signing key or business tables are needed.
  This internal HTTP service requires a separate shared key, is on a private
  compose network with no published port, logs no requests and serves one read
  at a time (at most two worker DB connections including the background batch).
  The PDF subprocess inherits neither that key nor the AI Gateway key.
- One atomic replace publishes the entire reports generation; an independent
  active generation keeps its shorter cadence. The watermark is the UTC batch
  read time, not a source event sequence. Generated time, age, TTL and SHA-256
  are attached to preview, export metadata and audit. Downloading an existing
  preview preserves its exact original rows for its five-minute grant lifetime,
  even if a newer source generation exists. Export/audit metadata recomputes
  age and labels an old frozen preview stale instead of claiming it is fresh.
- Two published files, each <=24MiB; interrupted staging files are reaped by
  the single producer before the next publication. Sources fail closed at 10,000 sessions / 20,000
  productivity sessions / 5,000 exceptions / bounded catalogs; no silent
  truncation. One worker, 0.5 CPU/256MiB; report service also 0.5 CPU/256MiB.
  A failed build retains the last complete generation only until its TTL.
- `POST /reports-api/chat-data` takes `{intent: <same schema as preview>}` and
  returns report row count, productivity totals/average when applicable, and
  freshness metadata. `GET /reports-api/active-sessions` returns only active
  session/employee counts. Both authenticate and recheck dataset permissions;
  role restrictions match the existing session endpoints. No names, IDs,
  free-text rows or credentials in these responses. `external_ai_allowed:false`
  is a restriction, not sanitization approval: do not forward business facts
  to public support or the AI Gateway. #39 can render these locally; #40's
  public product Q&A contract stays unchanged.
- Native PDF renders the exact authorized preview snapshot, like XLSX/CSV,
  without querying PR #34's live-data export route. It shares WeasyPrint 66's
  deny-all-fetch approach; the separate engine's app/UI/deployment is unchanged.

Deployment additionally needs `SNAPSHOT_IMAGE` and
`SNAPSHOT_DB_NETWORK=mesflow_network` in the report compose `.env`, a root-0600
`/opt/mesflow/report-snapshots.env` containing the SELECT-only DATABASE_URL and
private REPORT_SCOPE_KEY, `/opt/mesflow/report-scope.env` with only that scope
key for reports,
and `/opt/mesflow/report-snapshots` owned 65534:65534, mode 0700. Build both
images once and transfer the same artifacts to TEST. Verify current TEST role,
app/image/config and exclusive report ownership immediately before rollout.
Start the worker and check both private artifacts before replacing reports.
No nginx change or MES app restart is required. Preserve previous compose/env,
images and audit files. **Do not restore the pre-79eb346 report image:** authorization
verification found that the app can return an old login role after a downgrade;
legacy reports lack the private current-role check. Emergency rollback is to
stop only `reports` and `snapshots` (reports become unavailable, access fails
closed), keeping the app, support, nginx and private evidence unchanged. Recover
by starting the pinned worker, checking `snapshot_health.py`, then starting the
pinned report image and checking its health. Never recover reports against an
unhealthy worker or remove the current-role check.

The TEST-only guarded rollback script is saved at
`/opt/mesflow/report-assistant/rollback/issue45-20261010T0515Z/rollback.py`.
Run as root with `check`, `disable`, or `recover`; `exercise` disables then
recovers both report services. It checks TEST identity, exact image digests,
compose pins and unchanged app/support/nginx. The original pre-change files
remain available for investigation, not an authorization-safe restoration.
See [issue #45 TEST proof](../../reports/ISSUE45_TEST_SNAPSHOT_PROOF.md).

Tests: `tests/test_report_snapshots.py` (lifecycle/security) and
`tests/integration/test_report_snapshot_parity.py` (real PostgreSQL, five
filters, all five report kinds, simulated scan freshness, DB write rejection).
Live proof must separately record warm browser/API p50/p95 and compare rows
against the authorized source APIs; mocked tests cannot establish that.

## Initial TEST route installation (already deployed)

Use only the verified `vps-78ae7aec` (`148.113.207.13`), `/api/system/ready`
server role `PRODUCTION_TEST`. Keep live `mesflow-app` image/start time unchanged.
Build `docker build -f services/report-assistant/Dockerfile -t <immutable-tag> .`
after tests/merge. Install compose at `/opt/mesflow/report-assistant/compose.yml`
with `REPORT_IMAGE=<immutable-tag>` in its `.env`. Reuse the server-side dedicated
key env `/opt/mesflow/public-support.env`; never copy it into the image or repo.
Create `/opt/mesflow/report-audit` owner 65534:65534 mode 0700. Install
`logrotate.conf` into `/etc/logrotate.d/mesflow-report-assistant` (root owned).

Use `scripts/prepare-report-assistant-nginx.py` on the actual current gateway
config AFTER root support routing is installed. Save config, both landing HTML
copies and new service compose first. Run `nginx -t` on the candidate, update
`/opt/mesflow-gateway/nginx/nginx.conf` in place (preserve bind-mounted inode),
then reload nginx. Exact `/reports` and `/reports-api/` route to port 8089 on
`mesflow-edge`; no published ports. Report API forwards the browser session to
this service (which filters it); public support STILL strips all auth/cookies.
Sync welcome.html on host and running nginx, as documented in PROJECT_CONTEXT.

Rollback: restore the saved nginx config in place and both landing HTML copies,
`nginx -t && nginx -s reload`, then stop only the report service. Never recreate
or downgrade the existing MES app or nginx. Keep audit files for investigation.

## Verification

`pytest -q tests/test_report_assistant.py` covers permission denial/revocation,
owner isolation, forbidden scope overrides, exact source filters, read-only
exceptions, no model SQL/false fields, non-Claude policy, limits/audit failures,
CSV/XLSX integrity and formula safety. `tests/e2e/report-assistant.spec.js` uses
MOCK APIs to test mobile UI, clarification, downloads and expired sessions;
it is not evidence of live data or a real AI completion.

Before claiming deployment complete, verify the public root/chat and `/reports`
on desktop/mobile, anonymous demo versus live denial, an authenticated real
preview/download compared with existing source APIs, session-safe `/login` and
`/app`, and a real gateway result separately from rules fallback.
