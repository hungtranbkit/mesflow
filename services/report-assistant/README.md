# MESFlow report assistant

Standalone read-only service for `/reports` and `/reports-api/*`. It does not
replace the MES app, import its session signing key, or connect to its database.
The root support dialog links here for report requests. No migrations.

## Security and semantics

- Anonymous `demo` always uses clearly labeled fixed sample rows; it never calls
  a business API. `live` requires the existing signed MES session. Each preview
  and download asks `/api/auth/me` again and applies the existing permissions
  plus the session endpoints' role restriction. Password-change-required users
  are denied. No service account or bearer token is used to fetch reports.
- Source requests are fixed GET-only paths against `mesflow-app:8080`. Only the
  session cookie is forwarded. Backend authorization remains authoritative.
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
  Snapshots last five minutes, max 3/user and 30 globally. Downloads recheck
  identity/RBAC, max 3/snapshot and 10/min/user. One worker keeps in-memory
  limits coherent. Restart clears snapshots and resets rate budgets.
- Excel and UTF-8 BOM CSV use the exact preview snapshot, with source/filter
  metadata, formula-safe cells and SHA-256 verified by the browser. Server audit
  records user, filters, count and download hash, never rows/prompt/cookies/key;
  audit failures block downloads. Audit means granted/generated, not proof the
  user saved the file. PDF is browser Print/Save PDF, not native server output.

## TEST deployment only

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
