# Lead-auditor findings (verified personally, not from subagents)

## EDGE-01 | P1 | Edge/TLS | CONFIRMED
`http://mesflow.net/login` serves a working login form over cleartext (HTTP 200,
1870 bytes), and `http://mesflow.net/kiosk` serves the full kiosk page (200,
12603 bytes). No HSTS header anywhere.
- Evidence: `curl -sS -o /dev/null -D - http://mesflow.net/login` -> `HTTP/1.1 200 OK`,
  `Server: cloudflare`, `CF-RAY: a3ab406ebb3506f0-HKG`; no `Strict-Transport-Security`
  in the HTTP or the HTTPS response. `grep -rniE 'content-security-policy|strict-transport-security'`
  over the whole repo returns nothing.
- The repo's own origin config is CORRECT: nginx/nginx.conf:109-110 has
  `location / { return 301 https://mesflow.net$request_uri; }` on the :80 server.
  Cloudflare terminates :80 itself, so that origin redirect never runs.
  => this is a Cloudflare edge setting ("Always Use HTTPS" is OFF), not a code bug.
- Impact: password typed into `http://.../login` is POSTed to `/api/auth/login`
  in cleartext to the CF edge. `/kiosk?token=<kiosk device token>` enrollment
  (static/kiosk.js:31-38) would also travel in cleartext. Without HSTS a user
  already on HTTPS can be downgraded on a hostile network.
- Secondary failure mode: cookie is `SESSION_COOKIE_SECURE=settings.cookie_secure`
  (app.py:91). If Secure=1 in production, a cleartext login "succeeds" (ok:true)
  but the browser drops the cookie -> user bounced back to /login with no
  explanation.
- Fix: Cloudflare "Always Use HTTPS" + "Automatic HTTPS Rewrites" ON; add HSTS
  (`max-age=31536000; includeSubDomains`, preload later) at CF or origin. Keep the
  deliberate plain-HTTP ESP32 carve-outs (`/api/kiosk/`, `/api/station/`,
  nginx.conf:44-95) — devices, not browsers.
- Confidence: CONFIRMED (live observation, read-only).

## LOG-01 | P1 | Logging/PII | CONFIRMED
Employee badge QR values — which this codebase itself calls a credential
("dumps the whole employee roster INCLUDING every badge QR value, which is a
credential", app/mesflow/web/kiosk.py demo-data docstring) — plus employee name,
department and position are written verbatim into `action_logs.request_json`
and `action_logs.response_json` on every kiosk scan, and kept 30 days.
- Evidence (my stack, mesflow-app:71.0.0.310):
  `POST /api/kiosk-web/scan {"qr":"WF|EMP|NV001"}` (anonymous, public surface) then
  `SELECT path,request_json,response_json FROM action_logs ...` returns:
    request_json  = {"qr": "WF|EMP|NV001"}
    response_json = {"employee": {..., "employee_no": "NV001", "name": "Huỳnh Thị Mơ",
                     "position": "Tổng Giám Đốc", "qr": "WF|EMP|NV001"}, ...}
- Root cause: redaction is key-name based only —
  `SENSITIVE=('password','token','authorization','cookie','secret','api_key')`
  at app/mesflow/web/action_logging.py:10, applied by `_clean()` (:20-25).
  'qr' is not in the list. Passwords ARE correctly redacted (verified).
- Retention: `log_retention_success_days` default 30 (core/config.py:119);
  action logging on by default (:112). Readable by any admin via
  `GET /api/system/action-logs/<id>` (action_logging.py:90-92, @admin_required).
- Impact: a store of badge credentials nobody designed, sitting in the main DB
  for 30 days, in every backup, readable by every admin. Anyone with one of these
  values can identify as that worker at any terminal — exactly the reason
  /api/kiosk-web/demo-data was locked down in 2026-09-09.
- Fix: add 'qr' to SENSITIVE (one line). Small, low risk. Regression test:
  scan an employee QR, assert the persisted action_logs row contains '***' and
  not the raw payload.
- Confidence: CONFIRMED.

## ERR-01 | P2 | Error handling / observability | CONFIRMED
`_error()` in app/mesflow/web/kiosk.py:51 maps `KeyError` and `TypeError` —
which are programming bugs, not client mistakes — to HTTP 400 `INVALID_REQUEST`
with the raw Python exception text as the worker-facing `message`.
- Evidence (anonymous, public surface):
    POST /api/kiosk-web/start {}                       -> 400 message "'employee_id'"
    POST /api/kiosk-web/start {"employee_id":"abc",...} -> 400 message
        "invalid literal for int() with base 10: 'abc'"
    POST /api/kiosk-web/start {"employee_id":null,...}  -> 400 message
        "int() argument must be a string, a bytes-like object or a real number, not 'NoneType'"
- Two impacts, the second is the important one:
  (a) Python internals leak to anonymous callers on an internet-facing surface.
  (b) The bug becomes INVISIBLE: action_logging.py:59 only writes `error_traces`
      when `status>=500 or exc`. Confirmed on my stack — after all three calls,
      `SELECT count(*) FROM error_traces` = 0, and the action_logs rows are
      outcome='FAILED', not 'ERROR'. A real defect never reaches the error
      dashboard the System Console is built around.
  Also the shop-floor screen shows a raw Python message to a worker, defeating the
  whole point of the `message`/`action` pair.
- Fix: drop KeyError/TypeError from the 400 branch so they fall through to the
  500 branch (which already returns a generic message and no internals), and
  validate required fields explicitly with a real worker-facing message.
  Note app/mesflow/web/errors.py:78 has the same shape for TypeError; kiosk_v2.py:348
  correctly does NOT include KeyError/TypeError.
- Confidence: CONFIRMED.

## SEC-CSP-01 | P2 | Headers | CONFIRMED
No Content-Security-Policy is set anywhere — not by the app
(`@app.after_request security_headers`, app/mesflow/web/app.py:225-243, sets
X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy and
Cache-Control but no CSP) and not by nginx (`grep -c add_header nginx/nginx.conf` = 0).
Confirmed absent on the live response headers too.
- Impact: any XSS anywhere is completely unmitigated, on a surface that includes
  a PUBLIC page (/kiosk) rendering server-side data.
- Fix: start with a report-only CSP to find violations, then enforce. The app
  serves only same-origin scripts, so a strict policy is realistic.
- Confidence: CONFIRMED.

## AUTH-RATE-01 | P2 | Auth | CONFIRMED (with mitigation noted)
No application-level login throttling or account lockout. 12 consecutive wrong
passwords, all 401, then the correct password succeeded immediately.
- Evidence: loop against my stack -> `401 401 401 401 401 401 401 401 401 401 401 401`
  then `200`. The `users` table has no failed-attempt/lockout column
  (`\d users`: id, username, display_name, password_hash, role, active,
  must_change_password, created_at, updated_at, session_epoch).
  `grep -rniE 'failed_login|lockout|rate.?limit|throttle'` over app/ finds only
  the unrelated offline-event `attempt_count`.
- MITIGATION THAT EXISTS: nginx/nginx.conf:19 `limit_req_zone ... rate=10r/m`
  and :132 `limit_req zone=auth_limit burst=5 nodelay`. So the edge does throttle
  per source IP — but 10/min is still ~14k attempts/day/IP, it is per-IP so a
  distributed attempt is unlimited, and it is the ONLY layer: anything reaching
  the app directly (internal network, a misrouted CF rule) has no limit at all.
- Fix: per-account exponential backoff + temporary lockout in the app, and log
  the lockout to the security audit trail.
- Confidence: CONFIRMED.

## LOG-02 | P3 | Audit trail | CONFIRMED (tech debt)
`system_audit_service.record()` — the append-only privileged-action audit trail
(SUPER_ADMIN grant/revoke, service restarts) — wraps its INSERT in
`except Exception: pass` with NO logging at all
(app/mesflow/services/system_audit_service.py:39-40).
- The "best-effort, must not fail the action" intent is documented and defensible;
  the missing `logger.exception(...)` is not. A privileged action can go
  unrecorded with zero trace anywhere.
- Same shape without logging: services/metrics_service.py:63-64,
  db/repositories/offline_sync.py:410-411, web/kiosk_v2.py:834-835 (the last two
  are documented deliberate best-effort paths; kiosk_v2 already carves out the
  case that mattered, PermissionDeniedError).
- Contrast: action_logging.py:60 does this correctly —
  `except Exception: logger.exception('Unable to persist action log trace_id=%s', ...)`.
- Fix: one line each. Low risk.
- Confidence: CONFIRMED.

## Codebase hygiene observations (context, not findings)
- ZERO TODO/FIXME/HACK/XXX markers in app/ (grep over *.py/*.js/*.html).
- 175 `except Exception` in app/, of which only 5 swallow with a bare
  pass/continue, and 4 of those 5 are documented deliberate best-effort paths.
- Regression-prone subsystems by fix-commit frequency over the last 10 weeks:
  ui (29), kiosk (11), dashboard (11), tutorial (8), router-export (5), rework (5).
- Churn over 8 weeks (app/ only): ui.css 93, app.js 90, analytics.py 39,
  kiosk.js 25, kiosk.py 17, kiosk.html 16, execution.py 16, production_state.py 16.

## Test baseline at 2e81515 (71.0.0.310)
- static+unit: 962 passed, 2 failed in 120s. Both failures are
  tests/test_autologin_guard_unit.py::{test_non_production_enabled_flag_passes_the_guard,
  test_production_with_explicit_override_passes_the_guard} — they expect HTTP 503
  AUTO_LOGIN_USER_NOT_FOUND, which needs a reachable PostgreSQL. Reproduced
  identically on the pristine parent commit 2481f8c, so: ENVIRONMENT, not a regression.

## SESSION-01 | P2 | Session policy | CONFIRMED
Default web-session lifetimes are very generous for a system that can
force-delete a PO, manage users and reach a SUPER_ADMIN console:
  session_idle_minutes    = 14*24*60 = 14 DAYS   (core/config.py:64)
  session_absolute_hours  = 30*24    = 30 DAYS   (core/config.py:65)
  kiosk_session_idle_minutes = 15 minutes        (core/config.py:69)  <- sensible
- Verified on the wire: `Set-Cookie: session=...; Expires=Wed, 14 Oct 2026 ...;
  HttpOnly; Path=/; SameSite=Lax` — i.e. a 30-day cookie.
- The whole point of core/session_policy.py is expiry; a 14-day idle window makes
  it close to a no-op against the realistic threat (an unattended browser on a
  shared workshop/office machine).
- Fix: 8-12h idle for admin/manager roles, keep the 15-minute kiosk window,
  and consider a shorter absolute ceiling. Config-only change, no code.
- Confidence: CONFIRMED (defaults read + cookie observed).

## CSRF-NOTE | context for the security findings | CONFIRMED
There is no CSRF token, but `SESSION_COOKIE_SAMESITE='Lax'` (app.py:93, observed
on the wire) blocks the cookie on cross-site POST/fetch in modern browsers, so
the classic cross-site form POST is already mitigated. The residual exposure is
narrow and specific: SameSite=Lax DOES send the cookie on top-level GET
navigation, so any STATE-CHANGING GET route is CSRF-able via a plain link/img.
=> the actionable question is "are there state-changing GET endpoints", not
"add CSRF tokens everywhere". Cross-check against the route inventory.

## Test environment note (important for classifying integration results)
My first integration run against an ad-hoc stack produced hundreds of errors.
Root cause was MY stack, not the product: compose.test.yml's API service sets
MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND=1, MESFLOW_TEST_AUTO_LOGIN=1,
MESFLOW_ENABLE_FORCE_DELETE_PO=1, MESFLOW_INTERNAL_API_TOKEN,
MESFLOW_LEGACY_HEALTH_WRITER_ENABLED=1, MESFLOW_ESP_TUTORIAL_DIR and a
tutorials volume; without them whole test files fail by design (e.g.
tests/integration/test_kiosk_rebind_security_blocker2.py documents its own
dependency on the autobind flag). Re-ran with the canonical env replicated.

## RBAC-DRIFT-01 | P2 | RBAC | CONFIRMED — and it invalidates part of the security agent's report
The live `viewer` role holds **1** permission (`overview.view`); the code's
canonical seed says **12**. Every other role matches the constant exactly.
- Evidence (live audit DB, image mesflow-app:71.0.0.310):
    SELECT role_code,count(*) FROM rbac_role_permissions GROUP BY 1;
      admin | 36   manager | 34   operator | 8   supervisor | 19   viewer | 1
  vs SEED_ROLE_PERMISSIONS in app/mesflow/db/repositories/rbac.py:82:
      {'admin': 36, 'manager': 34, 'operator': 8, 'supervisor': 19, 'viewer': 12}
  Migration 0025_rbac_permissions.py:55 seeds viewer with 11 codes; only
  overview.view survives live.
- Why it can never self-heal: RBACRepository.seed() (rbac.py:196-238) seeds a
  role's grant set ONE ROLE AT A TIME and only when that role has ZERO rows —
  "any role with at least one grant already recorded, however it originally got
  there, is left completely alone" (its own docstring). The rationale is sound
  (a naive re-seed would resurrect grants an admin deliberately removed), but the
  consequence is that ANY partial grant set is frozen permanently, and no drift
  detector exists.
- Root cause of the initial partial state NOT pinned. Needs follow-up.
- Impact: fail-SAFE in direction (viewer is more restricted than intended), but
  (a) the permission matrix an admin sees is not what the code declares, and
  (b) any permission added to SEED_ROLE_PERMISSIONS for an existing role will
  never be applied on an installation that already has one grant for that role.
- **This is why SEC-08 did not reproduce** — see the correction below.
- Fix: a startup/CI drift check comparing rbac_role_permissions against
  SEED_ROLE_PERMISSIONS and reporting (not silently repairing) the difference.

## CORRECTION to the security agent's SEC-08 (RBAC widening)
The agent predicted, from a static evaluation of _permission_for_request(),
that a `viewer` could GET /api/production-orders/<id>/router.xlsx and
/router-labels (declared @roles_required('admin','manager')). Tested live with a
real viewer session on 71.0.0.310:
    viewer GET /api/production-orders/277/router-labels -> 403
    viewer GET /api/production-orders/277/router.xlsx   -> 403
    viewer GET /api/users (control, genuinely admin-only) -> 403
It does NOT reproduce, because `viewer` does not actually hold `po.view` in the
seeded RBAC (RBAC-DRIFT-01). The *mechanism* the agent describes is real and the
carve-out list is genuinely incomplete — but the exploit depends on a grant that
is not present, so this is a LATENT design weakness, not a live hole. It becomes
live the moment anyone grants viewer `po.view` through Users & Roles.
Downgraded from P1 CONFIRMED to P2 HIGH-RISK SUSPECT.
The one part that DOES reproduce: `viewer GET /api/templates/import-history` -> 200.

## Verified live by me, from the security agent's report (not just accepted)
- SEC-01 CONFIRMED: anonymous POST /api/kiosk-web/scan with a GUESSED employee
  number ("WF|EMP|NV002", never scanned) returns that employee's badge qr and
  name -> workforce enumeration + credential harvest.
- SEC-02 CONFIRMED end-to-end (the most serious): with no cookie and no token,
  POST /api/kiosk-web/start created work_session id=216 for an arbitrary
  employee+operation, then POST /api/kiosk-web/finish/216 {"good_qty":99999}
  closed it; operations.done_qty went to 99999. Reachability on the live host
  confirmed with a HARMLESS probe only (POST /api/kiosk-web/scan {} -> 400
  SCN-001); I did NOT attempt any write against mesflow.net.
- SEC-10 CONFIRMED end-to-end: an ordinary `admin` reset a super_admin's
  password and logged in as them.
    GET /api/system-health/services  as admin -> 403 ; after escalating -> 200
    GET /api/system-health/audit     as admin -> 403 ; after escalating -> 200
  FIXED in commit 6a13511 with a regression test.
- SEC-06 partially confirmed: GET /api/wallboard/employee-productivity is public
  and unauthenticated on the live host (HTTP 200, no cookie) — but it currently
  returns `employees: []` (zero rows) there, so no PII is being exposed right
  now. The exposure is real the moment that window contains completed sessions.
- OPS-12 CONFIRMED but LATENT: MESFLOW_ENV in {Production, PRODUCTION, prod,
  prodtest} boots with secret_key='dev-only' and cookie_secure=False. Every real
  deployment path uses exact lowercase 'production' (compose.yml:49,
  .env.example:3) and the live host reports environment='production', so this is
  a typo-triggered hazard, not a live hole.
