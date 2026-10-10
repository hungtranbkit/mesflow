# PROJECT_CONTEXT.md

Living handoff for the MESFlow app repo (`hungtranbkit/mesflow`). Read after
`AGENTS.md` / `PROJECT.yaml`. Code, tests, git and the running stacks win over
anything stale here; fix this file when they disagree.

> Note: the long-lived UI refactor line `refactor/ui-consolidation-20260928`
> has its OWN `PROJECT_CONTEXT.md` (P0–P3 handoff). This file was created on
> main by the kiosk hotfix below. When main is next merged into that line,
> keep both sections (add/add conflict — concatenate, don't pick one).

## Issue #40 — instant FAQ live on TEST (2026-10-10 12:28 ICT)

This supersedes the old topic-selection support design recorded below.

- PR #44 merged as `88b32a0` from tested source `8e04f31`, independent worktree
  `mesflow-issue40`. Resolved the main handoff conflict without dropping the
  report assistant notes. Full push CI `38026075761` and PR CI `38026078032`
  both passed: **1,997 Python/PostgreSQL + 598 browser passed, 31 skipped**.
  Focused suite: 43 Python + 8 Playwright; independent review findings resolved.
- Familiar questions render immediately in the browser, with no gateway call.
  Fourteen reviewed public topics cover Vietnamese/accent-free questions,
  active workers, multi-operation sessions, employee Excel, progress checks,
  quantities and missing plans. Explicit compound clauses preserve both intents.
  Kiosk facts were checked against actual code: new OP starts on scan, existing
  OP QR selects a session; setup sessions skip quantities.
- Complex public questions show relevant FAQ first and an explicit AI opt-in
  preview. Only public topic IDs + fixed intent + consent leave the browser;
  server reconstructs that public question and retrieves approved excerpts.
  Raw text, identifiers, page context, history, sessions and business data never
  reach the gateway. Generated text requires validated JSON, source citations,
  safe vocabulary and actual approved provider; invalid output stays FAQ.
- Shared `/support/assistant.js` exposes `MESFlowSupport.match/faq/deeper/topics`
  for #39; the same helper is embedded in the landing so FAQ survives outages.
  `/support/knowledge#id` exposes the public evidence. Legacy `{topics:[id]}`
  remains compatible and returns immediate `mode=faq`, with `topic_ids` intact.
  The .385/bf15a04 widget assets were exercised in an anonymous harness against
  the real support endpoint: 791ms end-to-end, correct FAQ and omitted cookies.
  This is NOT an authenticated app test or a claim .385 is still deployed.
- Nine-second wall deadline, nonblocking input, obsolete-response cancellation,
  two bounded workers, in-flight dedupe, five-minute cache, six AI requests per
  minute/IP, 20 upstream attempts/hour and 30s failure cooldown. Route check is
  cached five minutes; actual provider validated on every completion. No mock,
  Claude, paid/auto route or new gateway configuration. Internal-only metrics
  contain aggregate counts and rolling p50/p95, no prompts or identifiers.

### Observed live latency and limits

- BEFORE on TEST: known FAQ uncached **18,304ms / 16,363ms**, cached **802ms**.
- AFTER on https://mesflow.net/: **90 browser measurements** (six questions,
  five repetitions, three viewports), submit → next painted frame after page
  load: p50 **14.4ms**, p95 **15.1ms**, max **15.2ms**. First-question samples
  (n=18): p50 14.3ms / p95 14.9ms; repeats (n=72): 14.4ms / 15.1ms. These are
  local FAQ timings, not AI or initial page-load timings. Zero `/support/chat`
  or business `/api/*` requests during FAQ questions.
- AI caveat: one real extended diagnostic produced valid contextual Gemini
  prose in **17,768ms**. Subsequent diagnostics were slow, unavailable or rejected
  by output validation. Do NOT describe the AI path as reliably fast or fully
  live-validated for successful generation: public browser opt-in timed out at
  **9000.8ms server / 9852.3ms client**, then two requests returned cooldown FAQ
  in 368.7/384.6ms client time. FAQ was already visible in 12–20ms. No real AI
  cache hit was observed; cached-AI logic is covered by isolated tests only.
- Internal metrics immediately after smoke/E2E: FAQ 5 (known-topic 2, timeout 1,
  unavailable 2), upstream attempts 1. Browser-local FAQ samples deliberately do
  not increment server counters. Gateway #62 / PR #63 owns the separate
  `mesflow-fast` route; its reported DeepSeek hold and Gemini fallback explain
  the current latency. Keep #40 open for that successful real-AI follow-up.
- Public E2E at 1366/390/320 passed: no overflow/page errors, fully visible opt-in,
  privacy/unknown/pricing refusal, input remains enabled, source/helper/report
  routes 200. Anonymous `/app` → 302 `/login`; `/api/auth/me` → 401. No login,
  logout, real report query/download or business-data action was performed.

### Exact rollout and rollback

- Verified target: TEST `vps-78ae7aec`, `148.113.207.13`, ready role
  `PRODUCTION_TEST`. Support image **`mesflow-public-support:issue40-8e04f31`**,
  image ID `sha256:0c7f3fe0baf002a3a68f2e8528598a6b476db6076f491cf47dd80eb7cf83ee3d`.
  Only support compose under `/opt/mesflow/public-support` was recreated.
  No published port; existing root-owned secret env was preserved.
- Patched only exact `/support/chat`, `/support/assistant.js` and
  `/support/knowledge` nginx locations. Other routes, including reports/app,
  remained byte-for-byte unchanged. Drift checked before replacement; config
  written in place and nginx validated/reloaded without recreation. Synchronized
  BOTH host and current-container welcome.html. HTML SHA256:
  `8c3a94096f1a49dbfa43e50525f3f3d42fe3a4a79deb1f3f4aec8da28d19d194`.
  Nginx SHA256: `7691be53aef78d4c6123e4bab735d706f6f96cd13984eb6dc256da71543bcdea`.
- Concurrent sessions changed app/report versions BEFORE this rollout. Snapshot
  and postcheck confirmed this rollout preserved app `.383` / `4fb2882`, image
  `sha256:680d8db3…`, started `2026-10-10T05:02:49.770611972Z`, and report assistant
  `7e39f2c`, image `sha256:59e7b486…`, started `2026-10-10T05:18:47.377338807Z`.
  Do not restore .385 or overwrite the current integration app from this branch.
- Rollback: `/opt/mesflow-gateway/rollback/issue40-20261010T052810Z/` contains
  nginx.conf, both prior welcome copies and the prior support-image env. Restore
  support `.env` and start ONLY support compose; restore both HTML copies and
  nginx config IN PLACE, validate/reload. Never recreate app/report/DB. Coordinate
  future helper-dependent #39 UI before removing the helper routes in rollback.
- Shared widget handoff: #43 comments describe the new contract and the raw-static
  root constraint. Do not deploy an unrendered Jinja `{% include %}` as nginx's
  static welcome.html. #45 owns private precomputed snapshots and #62 owns the
  dedicated gateway route; neither belongs in this public KB endpoint.
- Evidence on HP: `/tmp/mesflow-issue40-evidence/`: `before.json`,
  `live-measurements.json`, `live-ai.json`, `legacy-widget.json`, screenshots,
  CI logs/JUnit, immutable archive+hashes, deployment script/log and live-state.
  Contract/build/rollback details: `services/public-support/README.md`.

## Secure natural-language report assistant — 2026-10-10 (live TEST)

- Separate `services/report-assistant` service, root chatbot link → `/reports`.
  No MES app replacement, DB credentials, migrations or business writes.
- Anonymous exports are fixed, clearly marked DEMO samples only. Authenticated
  preview/download revalidates current MES session and RBAC using existing APIs.
  Five report types: employee productivity, PO progress, Operation output,
  planned versus actual, exceptions. Filters: explicit dates, numeric PO,
  Operation and employee IDs; missing fields require confirmation in the UI.
- AI Gateway sees only public report-type/period enums, never raw questions,
  entity IDs, report data or sessions. Validated classification only, no SQL.
  Real non-queued/non-Claude route and provider checked; labeled rules fallback.
- Sources are fixed authorized GET endpoints; exceptions use session detail,
  NOT the existing auto-mutating `/api/session-exceptions` endpoint. Report
  notes distinguish session-start/end date semantics and current PO totals.
- Excel/CSV export exact preview, source/filter metadata, formula-safe cells,
  browser SHA-256 checks; PDF via browser Print only. Snapshots bound to user,
  expire in 5min, max 3 downloads; role/permission checked again. Audited grants
  fail closed if audit cannot be written. Date/row/size/time/rate limits apply.
  This is a single-workshop backend, not a newly introduced tenant model.
- Focused security/projection/export tests and mocked mobile/browser tests added.
  Full limits, API semantics, deploy/rollback instructions: see
  `services/report-assistant/README.md`.
- **Live on TEST 2026-10-10:** root support links to `/reports`. Anonymous
  reports are DEMO only; authenticated users can preview/export all five types
  through the existing authorized APIs. Native PDF is NOT deployed: the current
  button is explicitly browser Print/Save PDF, not a downloadable server PDF.
- PR #35 merged as `233ca3f` after BOTH full CI runs 38023284317 and
  38023287805 passed: 1,979 Python/PostgreSQL tests (27 skipped), 594 browser
  tests (4 skipped). Schema guard PR #38 merged as `987c249` after 37 focused
  tests on the merged-main tree. Its full PR follow-up run 38024166013 then
  passed (1,981 Python/PostgreSQL, 594 browser); the duplicate push run was still
  active at handoff. Mobile table readability PR #41 merged as `3f1e85f`, source
  `21524bf`, after all 4 report Playwright tests passed (1366/390/320px and
  expired session). Columns scroll in a named keyboard-focusable region;
  print sizing stays flexible. Full follow-up CI is separate from these results.
- Live browser checks on the final image: anonymous DEMO and authenticated
  Operation output at 1366×844 and 390×844; real Gateway intent responses and
  explicitly cached responses; the final authenticated desktop intent used
  labeled rules fallback, while mobile returned a fresh real Gateway result.
  Confirmed filters, API-equivalent rows, valid
  Excel/CSV, browser SHA-256 checks, no page errors/overflow, and login CTA back
  to authenticated `/app`. Other four types compared against their original
  authorized GET sources, including Part planned quantity and exact date/ID
  filters. The selected live exception sample was empty; nonempty exceptions
  are covered by the projection tests. Anonymous live preview and downloads
  of authenticated snapshots return 401; malformed report types and tenant
  overrides return 400. Non-admin denial/revocation and cross-user ownership
  are tested with isolated API fixtures, not fabricated production accounts.
- Audit verification matches the actual downloaded hashes to
  `REPORT_DOWNLOAD_GRANTED` records. No rows/raw prompts/secrets in the audit.
  Root regression checks at 1366/390/320px returned 200, protected `/app` 302
  to login and `/api/auth/me` 401; all root chat rechecks used verified cached
  Gemini. An initial transient support request fell back to FAQ; the subsequent
  browser run passed. Earlier uncached Gemini evidence is in the root handoff below.
- Deployment: isolated `mesflow-report-assistant:21524bf`, digest
  `sha256:3a7faa5ef37e043bde64d2e820fa24f587f07a2e95899680eddc7f1d4c05f88c`,
  compose `/opt/mesflow/report-assistant/compose.yml`, no host port, network
  `mesflow-edge`. Same dedicated server-only key env as support; audit directory
  `/opt/mesflow/report-audit` is 0700/65534 and has daily logrotate. Actual nginx
  config `/opt/mesflow-gateway/nginx/nginx.conf` SHA-256
  `71a57ef3b6986d3196c23ca8ec4838ff628619e231861c19e39609d1c4a624d7`.
  Both static landing copies were synchronized. MES app STILL runs e66587f /
  71.0.0.381, original digest/start time; support image/start time also unchanged.
- Rollback: `/opt/mesflow-gateway/rollback/report-assistant-20261010T0410Z/`
  contains pre-report nginx and BOTH welcome copies. Restore config in place,
  restore both HTML files, validate/reload nginx, then stop only report compose.
  Keep audit files. For a report-image-only rollback use `039af2b` (same backend,
  before the CSS accessibility fix). Restarting reports expires its snapshots.
- Evidence on HP: `/tmp/mesflow-root-evidence-20261010/`, including
  `live-report-browser.json`, `live-report-api.json`, `live-report-audit.json`,
  root browser JSON, CI logs, final runtime inspection and private screenshots.
  Never commit authenticated evidence/session files or gateway credentials.
- P0 Report Engine belongs to Dell PR #34 (XlsxWriter/WeasyPrint), still separate
  from the isolated assistant. Review findings posted there: one-sided dates
  bypass the 366-day cap, and synchronous PDF rendering needs bounded resource
  admission. Integration with the running refactor line also conflicts in
  employee-productivity.js: preserve the P3 report layout and add the PDF button
  there, never replace TEST with plain main. No backend/PDF deployment or native
  host package installation was performed here. Coordinate deployment ownership
  on PR #34 before changing the MES app. Issues #39 (chat inside `/app`) and #40
  (faster/useful public answers) are separate active work, not part of this report
  rollout; public support behavior was not changed by the report service.

## Public root support + real AI Gateway — 2026-10-10 (implementation)

- `/` renders the public landing with login CTA (`/login?noauto=1`) and
  compact “Hỏi MESFlow” dialog. `/app` remains protected; `/login` still
  redirects valid sessions to `/app`. Auth/session/RBAC code is unchanged.
- Grounding: approved public facts embedded in `welcome.html#support-facts`,
  sourced from landing workflow/features/FAQ, isolated demo, and verified
  380/381 Excel and active-worker behavior below. Browser matches questions
  to topic IDs. ONLY those IDs cross the public support endpoint; raw visitor
  questions/history/cookies/customer data never go to the gateway. Unsupported,
  pricing/contact/private questions get curated fallback without an AI call.
- `services/public-support/server.py` is a standalone Flask service with no
  MES imports, DB, session secret, tools or business API access. It loads the
  same approved facts from the HTML. AI selects allowed fact IDs; arbitrary
  model prose is rejected, so it cannot add unverified pricing/contact claims.
- Gateway verified: HP-local `127.0.0.1:8788` and the old repoport prefix are
  mock-only. User approved the REAL `https://ai-gateway.mesflow.net/v1` on m910.
  Authenticated models/config confirm `facebook-chat` is non-queued and uses
  only grok-web/gemini-web/deepseek-web. The service checks those candidates
  before each uncached call and rejects mock/Claude or unknown actual providers.
  A real non-streaming probe returned HTTP 200, Gemini, `{"topic_ids":["excel"]}`
  in 15.2s. Dedicated client key name `mesflow-public-support-test-20261010`,
  key ID `3e5491064a61`; the secret stays outside source/browser in a 0600 env file.
- Request controls: 300 characters locally, 256-byte server body, strict JSON
  schema (1–2 approved topic IDs), origin check, 6 requests/minute per gateway
  client IP, 20 upstream attempts/hour globally, 2 in flight, 20s completion
  timeout + 4s model check, 26s browser timeout, 60s failure cooldown, 5min cache.
  One gunicorn worker preserves these process-local budgets; restart resets them.
  UI labels fresh AI, cached AI, and FAQ fallback separately. No conversations
  are stored. The existing Cloudflare analytics beacon is separate.
- TEST rollout is static HTML + separate support container only: do not replace
  the live MES application image. `scripts/prepare-public-root-nginx.py` adds
  exact `/` and `/support/chat` locations in HTTPS; HTTP root redirects HTTPS.
  Support forwards neither Authorization nor Cookie, strips Set-Cookie, and
  overwrites client-IP. No public support container port. Other proxy blocks
  remain byte-for-byte intact. Existing nginx compose has a future read-only
  showcase bind; synchronize BOTH host HTML and current container HTML.
- Verification: focused Python suite 46 passed; browser coverage exercises
  1366/390/320px, keyboard, reset, text-only rendering, fake gateway/outage and
  payload privacy. These mocked browser checks are NOT proof of live AI.
- **Live verified 2026-10-10 11:19 ICT:** https://mesflow.net/ returns 200 at
  the root URL. Public browser checks at 1366×768, 390×844 and 320×568 passed
  without overflow, page errors or business API requests. First Excel response
  was `mode=gateway`, actual provider `gemini-web`; the next two were explicitly
  `gateway_cached`. This is real public E2E evidence, not a mocked response.
- Anonymous `/app` remains 302 → `/login`; `/api/auth/me` remains 401; manual
  login form works. An existing authenticated mobile session opened the root,
  followed the login CTA to `/app?page=overview`, and retained API authentication
  with no page errors. Do not logout the verification account: that can revoke
  other sessions. No authentication implementation was changed.
- Merged PR #32 (`374ecfa`, source `df7f048`) after full CI run 38022215529:
  1,944 Python/PostgreSQL passed (27 skipped), 590 browser passed (4 skipped).
  The original 20-minute gate timed out; job limit is now 40 minutes and
  Playwright artifacts use their own directory so they do not erase JUnit files.
- Actual nginx found a runtime-only alias problem during first live check:
  exact `/` plus a file alias appended `index.html` and returned 500. The original
  gateway config was restored while correcting it. PR #36 (`1d88af2`, source
  `7dfa87e`) replaces that alias with an INTERNAL rewrite to the already working
  exact `/welcome` static location; the browser URL remains `/`. Corrected route
  was first exercised by a separate loopback nginx process in the real container
  (response hash equals welcome.html), then 46 focused tests, merge, reload, and
  the public browser checks above. Full follow-up CI also runs on PR #36.
- TEST only: `vps-78ae7aec`, `148.113.207.13`, ready role `PRODUCTION_TEST`.
  Support image `mesflow-public-support:c034ae4`, digest
  `sha256:10b3b030a922b480fbc94128546cc2675e6d611fb0e18acdbb9e60b7792bb4a6`;
  isolated compose `/opt/mesflow/public-support/compose.yml`, key env
  `/opt/mesflow/public-support.env` (root 0600). No published support port.
  The MES app STILL has version 71.0.0.381, image `sha256:d4786d47…`, and start
  time `2026-09-30T10:06:11.689145751Z`: it was not restarted or replaced.
- Root rollback: `/opt/mesflow-gateway/rollback/root-support-20261010T0335Z/`.
  Restore nginx.conf IN PLACE and both welcome HTML copies, validate/reload;
  stop only the support compose if retiring it. Never recreate the MES app.
- HP evidence: `/tmp/mesflow-root-evidence-20261010/` contains CI logs, immutable
  image archive, corrected nginx config, deployment scripts, live browser JSON
  and screenshots. Authenticated evidence and temporary session/key files are
  private; never commit them. See the report assistant handoff for its separate
  rollout; a healthy support endpoint does not imply reporting is deployed.

## Public landing live on TEST — 2026-10-10 09:00 ICT

- **Live:** https://mesflow.net/welcome and https://mesflow.net/demo, both HTTPS
  200 (previously `/welcome` was 404). Source: PR #30 + PR #31 landing refresh
  `1c8111418d534fcf9e5adcb4bbddf445160d76f5`, with `c3675f6` removing the
  unverified Facebook contact link. Only the internal demo CTA is retained;
  no phone/email/Zalo contact was invented.
- Target verified over HP → SSH: `ubuntu@148.113.207.13`, hostname
  `vps-78ae7aec`; `/api/system/ready` reports `PRODUCTION_TEST`. No connection
  to `ssh-prod.mesflow.net`, DNS change, business-data write or migration.
- Static rollout only: `/opt/mesflow/public-showcase/{welcome.html,demo_showcase.html}`.
  The existing **container** `mesflow-nginx` serves exact `location = /welcome`
  and `location = /demo`, restricted to Host `mesflow.net`, from
  `/usr/share/nginx/html/mesflow-showcase/`. GET/HEAD only; no directory route.
  Nginx config: `/opt/mesflow-gateway/nginx/nginx.conf`. Existing `/`, `/app`,
  `/api`, kiosk and deploy-agent proxy blocks are unchanged.
- Backup: `/opt/mesflow-gateway/rollback/public-showcase-20261010T0159Z/`
  contains `nginx.conf` and `compose.yml` before this change. Updated the bound
  nginx.conf **in place** (preserve inode), ran `docker compose config --quiet`
  and `docker exec mesflow-nginx nginx -t`, then `nginx -s reload`; all passed.
  No container was recreated. HTML was copied into the current container;
  `/opt/mesflow-gateway/compose.yml` now declares a read-only bind mount from
  `/opt/mesflow/public-showcase` to that same container path for future recreates.
  Keep host HTML synchronized when refreshing the landing; application deploys
  alone do not update this static override.
- Backend unchanged: app container start time `2026-09-30T10:06:11Z`, version
  `71.0.0.381`, commit `e66587f`, image `sha256:d4786d47…`, migration `0054`.
- Verification: `pytest -q tests/test_showcase_public_routes.py`: **6 passed**.
  Local and LIVE Chromium at **1366×768** and **390×844**: landing → demo CTA,
  all four demo tabs, simulated scan completion and browser-only reset passed;
  no JavaScript/console errors, no horizontal document overflow, **zero `/api/*`
  requests**. The pages contain only fixed sample data. Public Cloudflare
  injects its existing analytics beacon (`static.cloudflareinsights.com` and
  POST `/cdn-cgi/rum`); this is not MESFlow API traffic, so do not claim zero
  network requests. Origin HTML hashes equal repository files; public HTML
  differs only by the edge-injected analytics script.
- `/` and `/app` remain anonymous `302 → /login` (same as before), not a public
  business dashboard. No authenticated app or real kiosk workflow was exercised.
- SHA256: welcome `7572574ca59176366694e41d4ccc399eabc637389683656660b8d23540f5f442`;
  demo `96c2a865c703040a7247804d54218e9c1ec85a2e6d50845c174655612f168425`.
- HP evidence: `/tmp/mesflow-public-evidence-20261010/` contains local/live
  screenshots, browser request/error reports, config before/after and the
  deployment script. GitHub PR #31 is the source of truth for CI/merge status.

Rollback (on **TEST VPS only**, no app restart or migration):
```sh
sudo sh -c 'cat /opt/mesflow-gateway/rollback/public-showcase-20261010T0159Z/nginx.conf > /opt/mesflow-gateway/nginx/nginx.conf'
sudo cp -p /opt/mesflow-gateway/rollback/public-showcase-20261010T0159Z/compose.yml /opt/mesflow-gateway/compose.yml
sudo docker exec mesflow-nginx nginx -t && sudo docker exec mesflow-nginx nginx -s reload
```
This removes both static overrides; the still-old backend will return 404 for
showcase routes again. The inert HTML copies can remain for recovery.

## Environments (as of 2026-09-29)

- DEV = https://dev.mesflow.net → cloudflared `kiosk-local-test` →
  `127.0.0.1:8310` → container `mesflow-dev-app` (compose project
  `mesflow-dev`, `/home/dell/workspace/mesflow-dev/compose.dev.yml`, image
  pinned in `/home/dell/workspace/mesflow-dev/.env` `MESFLOW_IMAGE`).
  DEV currently runs the UI refactor line, so DEV images are built from an
  integration of `refactor/ui-consolidation-20260928` + main (see Current
  state). Never deploy a plain main image to DEV; it would wipe UI P0–P3.
- TEST = "production test" = https://mesflow.net = VPS `vps-78ae7aec`
  (148.113.207.13, `/opt/mesflow`, compose project `mesflow`, container
  `mesflow-app` on 127.0.0.1:8080, SERVER_ROLE=PRODUCTION_TEST, DB =
  Patroni `mesflow-patroni-test` reached as `postgres`; the old
  `mesflow-postgres` container is exited and unused). Deploy ONLY with
  `REMOTE_TEST_TARGET_FILE=<main checkout>/scripts/remote-test-target.env
  REMOTE_TEST_SSH_CONFIG=~/.ssh/config scripts/deploy-remote-test.sh <ver>`
  (bundle transfer; local image must be tagged `mesflow-app:<ver>`). Real
  PROD (`mesflow-prod`, ssh-prod.mesflow.net) and the local
  `mesflow-prodtest-*` pair are different targets and are not touched by it.
- Version bump on main: `scripts/bump-version.sh <X.Y.Z.W>` then
  `scripts/check-version-sync.sh`. Main hotfixes land as a fix commit + a
  `chore(release): bump …` commit.

## Current state (2026-09-30, after the Tổng quan active-only hotfix)

- main = 71.0.0.381 (Tổng quan active-only, handoff below).
- Refactor line = `e66587f`: merge of main `28070b9` into `6b7c545`. The only
  conflict was a PROJECT_CONTEXT insertion; the overview code is identical
  to main.
- DEV runs `mesflow-app:dev-381-e66587f` (`.env` pinned; previous
  `mesflow-app:dev-380-133cb22`, kept for rollback). `/api/system/ready`
  → 71.0.0.381, commit e66587f, DEV.
- TEST (mesflow.net) runs 71.0.0.381 since 2026-09-30 17:05 ICT: image
  `mesflow-app:71.0.0.381` = the SAME image as DEV `dev-381-e66587f` (ID
  `sha256:d4786d47…`, retagged, not rebuilt). It was deployed with
  `scripts/deploy-remote-test.sh 71.0.0.381` → DEPLOY PASS.
  `/api/system/ready` → 71.0.0.381, commit e66587f, PRODUCTION_TEST,
  migration 0054 (no schema change).
  - Rollback: `mesflow-app:71.0.0.380` (`sha256:22f12e07…`, commit
    133cb22) is still on the VPS.
  - DB backup before the deploy: VPS
    `~/backups/mesflow-pre-381-20260930T100410Z.dump` (4.9 MB, 69 tables).
  - Verified read-only on https://mesflow.net, P3 + legacy, 1366 + 390:
    - 363 Operation rows; DOM == live API active lists, 0 mismatches;
    - 13 Operations with finished-today workers in the API show no block
      and no names;
    - 0 active at 17:05, so 0 blocks;
    - no JS errors.
  - No TEST data was created: TEST has only 26 real employees and no test
    accounts. "Active worker shown" is proven live on DEV with the identical
    image.
- 381 verification on DEV:
  - Merged tree: static suite 1246 passed / 2 failed (baseline
    `autologin_guard` ×2); Overview e2e 11/11.
  - Public https://dev.mesflow.net Tổng quan, P3 + legacy, 1366 + 390:
    225 rows, DOM == API active lists, no finished/placeholder text, no
    JS errors (DEV had no active sessions at the time).
  - Live sequence at 16:21 ICT via the real kiosk scan path: DEV-001 +
    NV002 started on op 4 (6126-…-01-OP01) → Overview listed both (NV 2).
    Finished NV002 (session #16, 0 qty) → only "Tho Dev" (NV 1). Finished
    DEV-001 (#15, 0 qty) → no Hôm nay block. The API still returned both in
    `today_worker_list`, so the data is preserved. DEV sessions #15/#16 are
    CLOSED, 0 qty, note "DEV verify: Tổng quan active-only hotfix 381".
- The PO header "Hôm nay" strip (day counts, no names) is intentionally
  unchanged.

- main = 71.0.0.380: kiosk hotfixes 377/378, the 379 detail export, and
  380 (`2252e57` feature, `255b61f` bump), which REPLACES 379's export
  menu with one-file Excel + print. Handoff below.
- Refactor line `refactor/ui-consolidation-20260928` = `133cb22`: merge of
  main `685de6d` (all fixes through 380) into P3 `57a71d8`. It no longer
  lacks any main fix.
- DEV runs `mesflow-app:dev-380-133cb22` (built from the integration worktree;
  `.env` pinned, previous `mesflow-app:dev-kioskfix-37b1f79`, kept for
  rollback). `/api/system/ready` → 71.0.0.380, commit 133cb22, DEV.
- TEST (mesflow.net) runs 71.0.0.380 since 2026-09-29 ~10:05 ICT: image
  `mesflow-app:71.0.0.380` = the SAME image as DEV's
  `mesflow-app:dev-380-133cb22` (ID `sha256:22f12e07…`, retagged, not
  rebuilt). `/api/system/ready` → 71.0.0.380, commit 133cb22,
  PRODUCTION_TEST, migration 0054 (no schema change; migrate step was a
  no-op). The script wrote `/opt/mesflow/deploy-state.json`.
  - Rollback: previous image `mesflow-app:71.0.0.376`
    (`sha256:170dd929…`, commit unknown) is still on the VPS. Set it in
    `/opt/mesflow/.env` MESFLOW_IMAGE, then
    `sudo docker compose --env-file .env up -d --no-deps mesflow`.
  - DB backup before the deploy: VPS
    `~/backups/mesflow-pre-380-20260929T030338Z.dump` (pg_dump -Fc, 4.6 MB).
  - Verified on https://mesflow.net (Playwright, P3 and legacy mode,
    1366×768 + 390×844):
    - P3 "Năng suất" with tabs Nhân viên/Operation;
    - exactly one "Xuất Excel" and one "In", no menu;
    - one workbook: Tổng hợp + 18 employee sheets, 156 session rows, each
      sheet's rows = its "Phiên hoàn tất";
    - print dialog shows "In toàn bộ"/"In theo nhân viên";
    - print-all: 18 sections, 18 page breaks, print() called;
    - print-one: 1 employee;
    - `/kiosk` 200; no JS errors.

## Recent handoff — Tổng quan: active-only workers (2026-09-30, 71.0.0.381)

**Ask.** Tổng quan must show only the employees with an active session
on each Operation. When someone finishes they disappear on the next
refresh; others on the same Operation stay; an Operation with nobody
active has no "Hôm nay" block (no finished/empty placeholder). This is a
display change only.

**Change.**
- New `app/mesflow/web/static/core/overview-active.js` (UMD, pure).
  `MFOverviewActive.activeWorkers(row)` builds the list from
  `row.active_worker_list` (OPEN sessions only, server-side):
  - it drops any entry that is not OPEN, has `ended_at`/`closed_at`, or
    has `session_count` <= 0 (defensive);
  - one entry per employee (duplicates folded, earliest start, session
    counts summed);
  - the API row is never mutated.
  `hasActiveWork(row)` = list not empty. It is loaded in `app.html` before
  `pages/overview.js`.
- `pages/overview.js`:
  - `todayMetrics(x)` returns '' when there is no active worker.
  - Otherwise the block lists only active workers (`.ov-worker.is-active`,
    "Đang làm HH:mm"). The NV metric = active count ("Nhân viên đang làm
    Operation này").
  - Day metrics (phiên, span, Đạt/Lỗi/Sửa được, Làm, ĐM, So ĐM, pace) are
    unchanged.
  - `today_worker_list` (closed-today history) is no longer drawn on
    Tổng quan.
  - The PO-level "Hôm nay" strip (counts only, no names) is unchanged.
  - The 60 s timer and the "Làm mới" load path are untouched.
- Backend untouched. `active_workers_by_operation()` is already
  `ws.status='OPEN'` + reportable, SETUP folded onto its parent OP, and
  multi-OPEN folded. AUTO_CLOSED sessions are CLOSED, so they leave on the
  next refresh. `today_worker_list`/`today` are still returned for
  Operation detail, Dashboard theo ngày and reports.

**Tests.**
- New `tests/test_overview_active_only.py` (7): the projection under Node
  covers:
  - 2 workers → 1 finishes → the other remains;
  - last finishes → no block;
  - CLOSED/AUTO_SHIFT_END/ended/zero-session entries excluded;
  - multi-session fold, no mutation;
  - page/backend contracts.
- New `tests/e2e/overview-active-only.spec.js`: refresh sequence at
  1366×768 and 390×844, plus one employee active on 2 OPs and AUTO_CLOSED.
  It FAILS on the pre-fix build (`dev-380-133cb22`: NV 3 ≠ 2) and passes
  on the fix.
- Updated the 2026-09-26/28 pins that required finished workers /
  placeholder: `test_overview_active_workers_unit.py`,
  `test_overview_today_activity_unit.py`,
  `test_overview_today_minidash_unit.py`,
  `e2e/overview-today-activity.spec.js`, `e2e/overview-today-minidash.spec.js`.
- e2e, isolated (throwaway `postgres:17-alpine` + test-mode preview with
  auto-login on 127.0.0.1:8319, both removed): 11/11 passed —
  overview-active-only ×2, overview-active-workers ×3,
  overview-today-activity ×3, overview-today-minidash ×3.
- Static suite (`mesflow-aw0926-tests`): 1220 passed / 2 failed / 18
  skipped vs main `3d185d8` 1218 / 2 / 13. The same 2 baseline-only
  `autologin_guard` failures; +5 skips are the Node tests, which pass on
  the host.

**Release.** `8a98290` fix, `1ed9abd` bump 71.0.0.381, plus this handoff.
DEV deploy / refactor-line integration: see Current state.

## Recent handoff — Năng suất: one-file Excel + "In" (2026-09-29, 71.0.0.380)

Supersedes the 379 "Chi tiết từng nhân viên" menu (`80c6ca0`/`c0b988e`, kept
in history). The user changed the requirement: one Excel button, one file,
plus printing.

**Behavior.**
- Screen buttons: exactly "Xuất Excel" and "In" (+ the existing "Làm mới").
  There is no dropdown and no `mode` parameter any more.
- "Xuất Excel" → `GET /api/reports/employee-productivity/export.xlsx`
  (`from,to,search,department,team,employee_id,sort,dir`) → ONE workbook:
  - sheet 1 "Tổng hợp": the summary, written by the same
    `_write_summary_sheet()` as before. Verified cell/format/style-identical
    to main's pre-hotfix summary export in 5 filter cases; only the sheet
    title changed ("Năng suất nhân viên" → "Tổng hợp").
  - one sheet per employee in the filtered list, in summary order, one row
    per session. Columns: STT, Mã NV, Tên NV, Ngày, PO, Part, Mã OP,
    Operation, Bắt đầu, Kết thúc, Thời gian thực tế, Sản lượng đạt, Lỗi,
    Định mức (giây/SP), Thời gian định mức, % năng suất, Trạng thái / ghi chú,
    NV xác nhận (signature, blank), Mã phiên. Header row 4, freeze A5,
    auto-filter, date/`[h]:mm:ss`/`0.0%` formats, widths, A4 landscape.
  - `employee_id` given → Tổng hợp + that employee's sheet only.
  - sheet names (`employee_sheet_names`): "<Mã NV> <Tên>", `[]:*?/\`
    replaced, <=31 chars, leading/trailing `'` stripped, never
    "Tổng hợp"/"History", case-insensitive dedupe with " (2)", " (3)"…
- "In" → dialog "In toàn bộ" / "In theo nhân viên" (choices = the rows the
  table currently lists). It opens `GET /api/reports/employee-productivity/
  print?<same filters>[&employee_id]&autoprint=1` in a NEW tab
  (`window.open`), so the app never navigates away. The template is
  `templates/employee_productivity_print.html`:
  - A4 landscape, `thead` repeats per page, screen-only toolbar (Đóng / In).
  - Filter/date context and "In lúc … bởi …".
  - The summary, then each employee's section with a page break before it
    (no page break for a single employee), plus signature lines.
- Filters: this screen has date range, search and department. There are no
  PO/Part/Operation filters on it. `team`/`employee_id` pass through.
  Excel and print both go through `web/productivity_export.py`
  (`parse_filters` → `load_export_data`).
- Access: both routes are `@login_required` (same as before; anonymous 401).
  `employee_id` outside the current filters → 404; a non-numeric one → 400.
- Formula: unchanged. Session % = `_SESSION_COMPLETION_PERCENT_SQL`
  (expected ÷ actual). The employee % on "Tổng hợp" = AVG of the non-empty
  session % on their sheet. Scope = `_productivity_scope()` (shared).
- Queries: 2 per export/print (`employee_productivity` +
  `employee_productivity_sessions`), grouped in memory. No N+1.

**Files.** `web/productivity_export.py` (new), `web/productivity_excel.py`
(one-file builder, sheet names; the old summary-only and 379 builders
removed), `web/analytics.py` (export + print routes),
`templates/employee_productivity_print.html` (new),
`static/pages/employee-productivity.js` (buttons + print dialog),
`static/ui.css` (`.ep-print-options`),
`tests/test_employee_productivity_detail_export.py` (rewritten),
`tests/test_employee_productivity_excel_export.py` (reads "Tổng hợp").
379's `_productivity_scope` / `employee_productivity_sessions` are reused
unchanged.

**Tests.**
- Productivity tests: 30 passed. They cover:
  - one/multiple employees, the same OP twice, and filters deciding sheets;
  - detail mapping/formats and AVG reconciliation;
  - summary semantics and exactly-2-queries;
  - long/invalid/duplicate/reserved sheet names;
  - Flask test client: export sheets, print all (2 page-breaks), print
    one, 404 outside filters, 400 bad id, 401 anonymous;
  - frontend contract.
- Static suite (`mesflow-aw0926-tests`, `--ignore=tests/integration
  --ignore=tests/e2e`, `-m "not postgres and not integration and not
  slow"`): hotfix 1218 passed / 2 failed / 13 skipped vs main `ea0c3cc`
  1210 / 2 / 13. The same 2 baseline-only failures (`autologin_guard` ×2),
  no new ones.
- Browser (preview container on the DEV DB, Playwright image,
  `--network host`) at 1366×768 and 390×844:
  - labels exactly "Xuất Excel"/"In", no menu;
  - one download with sheets `Tổng hợp`, `NV001 Huỳnh Thị Mơ`,
    `DEV-001 Tho Dev` (3 and 7 session rows, freeze A5, auto-filter);
  - print dialog lists the 2 filtered employees;
  - print-all tab: `window.print()` called, 2 employee sections,
    2 page-breaks, PDF render = 3 A4 pages;
  - print-one tab: only employee 28, title "BÁO CÁO NĂNG SUẤT · DEV-001 ·
    Tho Dev";
  - app tab URL unchanged, 0 px body overflow, no JS errors.

**P3 integration + DEV.**
- Child branch `ui-refactor/merge-main-380-20260929` merged main `685de6d`
  into refactor `57a71d8` → `133cb22`; the integration branch was
  fast-forwarded and both were pushed.
- Conflicts:
  - `pages/employee-productivity.js`: kept the P3 layout. The action row
    is Làm mới · In · Xuất Excel (the single `.primary`). Export/print code
    comes from main.
  - `PROJECT_CONTEXT.md` add/add: concatenated, main first, then P0–P3.
  - Tests: `test_ui_productivity_consolidation` checks the shared
    `reportQuery()`; the frontend test accepts the P3 `.primary` export
    button.
- Merged-tree static suite: 1244 passed / 2 failed / 51 skipped (the same 2
  `autologin_guard` baseline failures). The P3 base `57a71d8` was 1204 / 3;
  its third failure is fixed by main.
- Browser on a merge preview AND on public https://dev.mesflow.net after
  deploy, P3 mode (`ui_refactor=1`) and legacy mode, 1366×768 + 390×844:
  - "Xuất Excel"/"In" labels, no menu;
  - one workbook `Tổng hợp` + `NV001 Huỳnh Thị Mơ` (3 rows) +
    `DEV-001 Tho Dev` (7 rows);
  - print-all → `window.print()` called, 2 sections, 2 page-breaks;
  - print-one → only employee 28;
  - app URL unchanged, 0 px overflow, no JS errors.
- Anonymous print → 401. `/kiosk` 200 with the 377/378 kiosk code present.

## (Superseded) Excel năng suất: "Chi tiết từng nhân viên" menu (71.0.0.379)

Replaced by 380 above. It added `ReportRepository._productivity_scope()` and
`employee_productivity_sessions()` (one query, one row per session), which
380 still uses. The export menu and `mode=detail` it added are gone. Its
live-DB check (NV001 3 sessions / DEV-001 7, % 267.79 = summary) still
holds for the shared query.

## Recent handoff — kiosk pass 2: start refusals were masked (2026-09-29)

**Live DEV root cause (reproduced ~06:00 ICT on the pass-1 build d144edd).**
Pass 1 was live and correct: demo employee scan 200 → OP scan 200 →
`/start {"employee_id":28,"operation_id":4}`. DEV refused it:
`409 {"error_code":"SES-409","message":"Ngoài ca làm việc. …","action":"Quét
lại thẻ nhân viên…"}`. DEV shifts: DAY 08:00–17:00, NIGHT 18:00–00:00, Mon–Sat;
starts allowed 30 min early (`MESFLOW_SHIFT_START_EARLY_TOLERANCE_MINUTES`).
The refusal was correct, but the backend labelled it a session conflict with
"re-scan the badge" advice, and `kiosk.js` `workerError()` turned every 409
into "Công đoạn này hiện không thể bắt đầu". To the user it looked exactly
like the old SCN-003 bug. The user's own tab (WEB-621f8a6f, already on 377)
was sitting on that error.

**Fix.**
- `app/mesflow/web/kiosk.py`: `OutsideShiftError(ConflictError)` →
  `SHF-409` / `reason=OUTSIDE_SHIFT`, message lists the configured shift
  hours. `_conflict_reason()` gives every 409 a `reason` + specific code:
  PO-001 PO_NOT_STARTED, OP-409 OPERATION_CLOSED/REWORK_BENCH/NOT_READY,
  DEP-409 DEPENDENCY, QTY-409 INPUT_QTY, SES-409 SESSION_OPEN /
  SESSION_CONFLICT (fallback). The "đang mở Operation này" check must stay
  BEFORE the QTY substring test (its text contains "sản lượng"). `/start`
  "employee inactive or missing" → 400 `EMP-001` / `EMPLOYEE_INACTIVE`
  (Vietnamese). HTTP statuses unchanged; `reason` is a new field.
- `app/mesflow/web/static/kiosk.js`: with `reason` on a 4xx (not 401/403),
  the screen shows the server message/action; `kiosk_status.last_error`
  becomes `<CODE> <REASON>: <message>`. No `reason` (old server) → old
  generic text.
- Contract change: the out-of-shift code went SES-409 → SHF-409, and a
  PO-not-started START refusal went SES-409 → PO-001 (same code the scan
  path already used). ESP / kiosk v2 endpoints are untouched.

**Tests.**
- New `tests/test_kiosk_refusal_reasons.py`; e2e D6–D8 in
  `tests/e2e/kiosk-demo-employee-then-op.spec.js`. e2e 19/19 on the fix;
  D6/D7 fail on pass-1 main, D8 (old-server compat) passes on both.
- `test_a_programming_bug_becomes_500_and_is_logged` now pins clock + shifts.
  It used to measure the shift gate (409 out of hours, ShiftConfigDegraded
  without a DB), which kept main CI red and hid the integration step.
- Local static suite: 1200 passed, 2 failed (`autologin_guard` ×2 fail only
  in the local container env; they pass in GitHub CI).
- GitHub CI on 5473c8a: first run at 06:20 ICT had 7 `test_kiosk_scan_to_board`
  + 1 `test_p0_scan_auth` failures, all 409 OUTSIDE_SHIFT. Integration tests
  hit the REAL shift gate with no calendar pinning, so they are
  time-of-day dependent (pre-existing; they were hidden while the unit step
  failed). Re-run at 07:34 ICT: all of those pass; 616 passed, 1 failed:
  `test_rework_overview_rollup` (`progress_percent` None). That one also
  fails on pre-hotfix code (throwaway probe branch on 8aa78a6, CI run
  36504419675, now deleted), so it is pre-existing and unrelated.

**Live DEV verification (image 37b1f79).**
- 06:15 ICT (outside shift): `/start` → `409 SHF-409 OUTSIDE_SHIFT "Ngoài ca
  làm việc. Không thể bắt đầu phiên mới (giờ ca: Ca ngày 08:00–17:00 · Ca tối
  18:00–00:00)."`, shown on screen as that exact message.
- 07:31–07:33 ICT (inside the early window): demo employee → demo OP →
  `/start` **201** → screen "started", at 1366×768 and 390×844. Each test
  session was closed through the kiosk (re-scan badge → 0/0 → confirm):
  DEV work_sessions #8, #9, #10 for DEV-001 / op 4, all CLOSED with 0 qty.
- mesflow.net / production not touched (still 71.0.0.376).

**Open items.**
- Integration tests that call `/start` need a pinned shift (e.g. an
  all-day fixture shift) or CI goes red outside 07:30–17:00 / 17:30–00:00
  Mon–Sat. Adding a shift changes shift attribution, so do it with care.
- `test_rework_overview_rollup` progress_percent None: pre-existing, not
  investigated.
- A kiosk tab with the demo panel open never auto-reloads to a new version
  (`isIdleForReload` requires the panel closed). Demo users can stay on old
  JS after a deploy until they close the panel or refresh.

## Recent handoff — kiosk demo scan P0 hotfix (2026-09-29, pass 1)

**Bug.** On `/kiosk` with the "Mô phỏng quét QR" panel open: demo employee →
demo OP (server rejects, e.g. SES-409 "Ngoài ca làm việc") → demo OP again →
SCN-003 "Hãy quét thẻ nhân viên trước / Quét thẻ nhân viên trước, sau đó mới
quét Operation." Reproduced live on DEV with Playwright.

**Root cause** (`app/mesflow/web/static/kiosk.js`, `scan()`): while the panel
is open, result screens `error`/`started` stay pinned (scheduleReset skips
them; `error` never auto-returns). A scan on a terminal screen did
`reset(); setTimeout(() => scan(qr), 50)` — `reset()` wiped `employee` /
`openSessions`, the re-scan ran in `ready`, so an OP QR always hit SCN-003.
The re-scan also POSTed `/scan` twice and left a `ready` gap the next click
could fall into.

**Fix.** `scan(qr, {source})`; demo panel buttons and
`MESFlowKioskDemo.scanEmployee/scanOperation` pass `{source:'demo'}`. On a
terminal screen a demo scan reuses the result it already fetched:
employee → reset + handle as `ready`; Operation with an identified employee →
continue the operation branch with the same employee/open sessions;
Operation with nobody → SCN-003 as before. Dispatch uses a local `flow`
(seeded from `state`). Real scanner input, camera, and
`MESFlowKioskDemo.scan(qr)` keep `source='scanner'` → old reset+rescan path,
intentionally unchanged (at a standalone station an OP scanned after a
result screen may belong to the next worker, so they must badge first).
No backend/API/schema change.

**Tests.**
- New `tests/e2e/kiosk-demo-employee-then-op.spec.js` (D1–D5, mocked API).
  Run against a tiny Jinja+static server + `mesflow-test-playwright` image
  on `--network host`: fixed code 16/16 (with existing
  `kiosk-multi-session` + `kiosk-result-auto-return` specs); unfixed main
  fails D1, D2, D3; D4/D5 (unchanged behaviour) pass on both.
- New `tests/test_kiosk_demo_scan_keeps_employee_context.py` (source contract).
- `tests/test_web_kiosk_v6564.py` token updated `state === 'operation'` →
  `flow === 'operation'` (same intent).
- Full static suite in `mesflow-aw0926-tests` (`--ignore=tests/integration
  --ignore=tests/e2e`): 1183 passed, 13 skipped, 3 failed = known baseline
  (autologin_guard ×2, kiosk_errors_are_logged). `tests/integration` not run
  (needs live Postgres).

**Release / deploy.**
- Branch `hotfix/kiosk-demo-scan-20260929`: `a290681` fix, `987d01b` bump to
  71.0.0.377, plus this handoff commit; fast-forwarded into `main`.
- DEV only: image `mesflow-app:dev-kioskfix-d144edd` built from a local,
  unpushed integration merge `d144edd` = refactor `57a71d8` (P3) + hotfix.
  `.env` pinned to it (previous: `mesflow-app:ui-p3-c78f040`).
  `/api/system/ready` → 71.0.0.377, commit d144edd, DEV, migration 0054.
- Live DEV browser check (1366×768 and 390×844): demo NV→OP→OP now retries
  `/start` with the same employee (`[[28,4],[28,4]]`, 3 `/scan` calls, no
  SCN-003); reset → demo OP → SCN-003 with no `/start`; real-scanner hook
  after error still SCN-003. The remaining SES-409 is the genuine backend
  out-of-shift rule (checked ~05:30 ICT), not this bug.

**Open items / next actions.**
- The UI refactor line does not yet contain this fix. Merge `main` into
  `refactor/ui-consolidation-20260928` (VERSION goes to 377; resolve the
  PROJECT_CONTEXT.md add/add conflict by concatenating). Until then, any DEV
  redeploy from the refactor line alone REGRESSES the kiosk bug.
- Pre-existing UX gap (not changed): kiosk `workerError()` maps every 409 to
  "Công đoạn này hiện không thể bắt đầu", hiding backend reasons like
  "Ngoài ca làm việc".
- mesflow.net / production were not touched; promote 377 only with explicit
  approval.

---

<!-- Merged from the UI refactor line (add/add conflict resolved by concatenation, 2026-09-29). -->

## UI refactor line (refactor/ui-consolidation-20260928) — P0–P3 handoff

Last updated: 2026-09-29 (P3 Productivity)
Long-lived integration branch: refactor/ui-consolidation-20260928 (NOT merged to main; main = 8aa78a6)
Latest child task branch: ui-refactor/p3-productivity-20260929 (merged by fast-forward into integration @ c78f040 + handoff commit)
Workflow (P0-P3): child branch + own worktree -> fast-forward integration -> push both over HTTPS -> build DEV image from the integration worktree -> deploy dev.mesflow.net only. Never main, never TEST/production.
Production-test mesflow.net must not be deployed from this refactor line without explicit approval.

**GOLDEN REFERENCE:** the canonical Năng suất screen (`productivity`, P3) is the golden visual reference for every P4+ migration. Compose its primitives (DESIGN.md §5.11, screenshots in docs/ui-golden/productivity/) instead of building per-page UI.

### P0/P1 scope implemented
- Added machine-readable UI inventory at docs/ui-inventory.json.
- Baseline inventory is locked to 25 sidebar destinations, 9 hidden/legacy SPA page IDs, 4 standalone surfaces, and 4 viewport baselines: 1366x768, 1920x1080, 390x844, 430x932.
- Added metadata-driven canonical navigation in app/mesflow/web/static/core/canonical-nav.js.
- Canonical navigation has exactly 11 screens:
  overview, planning, templates, operations-sessions, quality, productivity, kiosk-admin, master-data, trace-logs, admin, system.
- Canonical tabs map to existing legacy renderers; no business renderer is duplicated in P0/P1.
- Legacy page aliases are preserved. Deep-link query parameters are preserved.
- Refactor navigation is opt-in only with ui_refactor=1 and persists client-side; ui_refactor=0 disables it.
- Without the refactor flag, legacy navigation behavior remains the default.
- Permission filtering continues to use existing legacy PAGE_PERMISSION/canOpenPage behavior.
- Overview canonical mapping continues to the existing overview renderer; overview-v2 is not introduced.
- Added tests:
  tests/test_ui_inventory_contract.py
  tests/test_ui_canonical_nav.py
  tests/test_ui_canonical_nav_browser.py

### Files changed
- app/mesflow/web/static/core/canonical-nav.js
- app/mesflow/web/static/app.js
- app/mesfow/web/static/ui.css
- app/mesflow/web/templates/app.html
- docs/ui-inventory.jso
- tests/test_ui_inventory_contract.py
- tests/test_ui_canonical_nav.py
- tests/test_ui_canonical_nav_browser.py

### Verification on child worktree
- Focused P0/P1 suite: 32 passed, 1 skipped.
- Broader navigation/overview/session regression suite: 80 passed, 1 skipped.
- Browser test skip reason: playwright.sync_api is not installed in the current local Python test environment.
- Overview today mini-dashboard unit tests: 15 passed.
- node --check passes for canonical-nav.js and app.js.
- git diff --check passes.

### Deployment state
- P0/P1 child implementation commit: ee72d5e.
- Long-lived integration branch refactor/ui-consolidation-20260928 is based on ee72d5e plus this handoff update.
- Both child and integration branches were pushed before DEV deployment.
- DEV stack is the existing Docker Compose project mesflow-dev under /home/dell/workspace/mesflow-dev using compose.dev.yml.
- Built DEV-only image mesflow-app:ui-p0p1-ee72d5e from the integration worktree.
- DEV app container is healthy on that image.
- https://dev.mesflow.net/api/system/ready reports version 71.0.0.376, server_role DEV, status ready, migration 0054_multi_open_session_per_employee.
- Live dev canonical-nav.js exposes exactly 11 canonical screens.
- Live resolver check: page=session-exceptions + ui_refactor=1 resolves to operations-sessions / exceptions / session-exceptions.
- Live overview mapping remains overview->realtime and dashboard->daily.
- Live URL serialization preserves unrelated query parameters while adding page/screen/tab canonical state.
- Live app.js contains MFCanonicalNav integration.
- Browser gateway is disabled on Terminal MCP, and local playwright.sync_api is not installed, so screenshot/browser verification was unavailable. Source/browser contract tests are present; 80 passed and 1 browser test skipped for that dependency.
- mesflow.net / production-test was not deployed or modified by this P0/P1 task.

### Next phases after P0/P1
P2 System console consolidation (done), P3 Productivity (done), then P4 Master Data, P5 Quality, P6 Kiosk Admin, P7 Trace/Logs, P10 Planning, P11 Admin, P8 Sessions, P9 Overview, P12 cleanup.

## P2 System Console consolidation — 2026-09-28
- Implementation commit: 4187267. Integration pre-deploy handoff commit: 374b236.
- Child branch: ui-refactor/p2-system-console-20260928 from refactor/ui-consolidation-20260928@9f1c4fc.
- Canonical System screen is explicitly marked `kind:'console'` and `lazy:true` in canonical-nav.js.
- The System canonical screen has exactly six tabs: overview, errors, logs, services, diagnostics, audit.
- Legacy routes remain the renderer/API source of truth; inactive tabs do not trigger their renderer/API until opened.
- Six legacy URLs still deep-link to the correct canonical System tab in refactor mode.
- Super Admin visibility remains gated through existing PAGE_PERMISSION / SUPER_ADMIN_PAGES / isSuperAdmin checks; backend system-health authorization is unchanged.
- Existing System renderers remain intact in pages/system-console.js: renderSystemOverview, renderSystemErrors, renderSystemLogsIT, renderSystemServices, renderSystemDiagnostics, renderSystemAudit.
- Restart and diagnostics POST actions are preserved unchanged.
- Canonical nav now exposes System console state via body/tab-strip data attributes and `canonical-console-tabs` class for shared console UI handling.
- New regression file: tests/test_ui_system_console_consolidation.py.
- Focused P2/canonical contract suite: 44 passed.
- Broader P2/navigation/Overview/session regression suite: 92 passed, 1 skipped because local playwright.sync_api is unavailable.
- System Console / Super Admin / system-health unit suite: 31 passed.
- Final integration verification suite after fast-forward: 75 passed.
- node --check passes for canonical-nav.js and app.js; git diff --check passes.
- P2 must merge only into refactor/ui-consolidation-20260928, never main, and deploy only to dev.mesflow.net.

### P2 DEV deployment verification
- Integration branch was fast-forwarded to child HEAD 374b236 before deploy.
- DEV image built from integration worktree: mesflow-app:ui-p2-374b236.
- Existing mesflow-dev Compose project was updated in place; app container is now canonical name mesflow-dev-app, image mesflow-app:ui-p2-374b236, health healthy, service label app.
- https://dev.mesflow.net/api/system/ready reports 71.0.0.376 / DEV / ready / migration 0054_multi_open_session_per_employee.
- https://mesflow.net/api/system/ready remains 71.0.0.376 / PRODUCTION_TEST / ready / migration 0054_multi_open_session_per_employee; production-test was not deployed.
- Live canonical-nav.js reports System kind=console, lazy=true and exactly six tabs: overview, errors, logs, services, diagnostics, audit.
- All six legacy System page IDs resolve live to screen=system and their matching canonical tab.
- Live canonical nav contains canonicalConsole state hook.
- Live system-console.js still contains restart and diagnostics action endpoints.
- Browser screenshot verification remains unavailable because Terminal MCP browser gateway is disabled; source/live-asset contracts and test suites are green.
- Browser screenshot verification is unavailable because Terminal MCP browser gateway is disabled (BROWSER_GATEWAY_DISABLED); source/live asset contracts were verified instead.

## P3 Productivity consolidation + golden visual reference — 2026-09-29
- Implementation commit: c78f040 on ui-refactor/p3-productivity-20260929 (branched from origin/main 8aa78a6, fast-forwarded onto integration 3eb6a00 first, since integration sat directly on main's tip). Integration fast-forwarded to it and both refs pushed (verified via GitHub API).
- Scope: employee-productivity + kpi-employees + kpi-operations -> one canonical screen `productivity`, tabs "Nhân viên" (page employee-productivity) and "Operation" (page kpi-operations). kpi-employees remains an alias (renders itself only for a role lacking session.view, as before).
- Routes/deep links: `?page=employee-productivity|kpi-operations|kpi-employees` and, in refactor mode, `?page=productivity[&tab=operations]` / `?screen=productivity&tab=operations` resolve to the right tab; unrelated query params are preserved.
- canonical-nav.js: productivity is `kind:'report', inlineTabs:true`; the shell's external tab strip hides for it and the page renders its own tab bar from the same SCREENS definition, so tabs exist with the refactor flag OFF too (legacy sidebar unchanged).
- kpi-operations: real renderer in app/mesflow/web/static/pages/productivity-operations.js (registerPage) replacing renderSimple; search/PO/status filters; KPIs recalculated from filtered rows (quantity-weighted: Σđạt/Σkế hoạch, Σđạt/Σ(đạt+lỗi)); status shown in Vietnamese. /api/kpi/operations has no date param, so no date filter (intentional). The dead renderSimple branch for kpi-operations was removed from app.js; inventory updated.
- Nhân viên tab (pages/employee-productivity.js): same filters, same summaryForVisibleRows KPI recalculation, same Excel export params (from/to/search/department/sort/dir) and NV xác nhận column; filters + sort now persist across tab switches within a page load (in-memory, reload = defaults). "Xóa bộ lọc" added. Wallboard panel unchanged, moved below the table. All element ids used by tutorial e2e are unchanged.
- Golden-reference primitives (core/ui.js, exported on MFUI): reportBar, screenTabs, bindScreenTabs, kpiCards, tableHead (aria-sort + real sort buttons), meter. CSS layer at the end of ui.css ("GOLDEN VISUAL REFERENCE", all `.mf-*`, scoped): .mf-report, .mf-report-bar, .mf-screen-tabs, .mf-kpis/.mf-kpi (tone = top indicator), .mf-table-panel, .mf-table (sticky header inside --table-sticky-max on desktop, right-aligned tabular numerics, hover, sticky identity column <=700px), .mf-badge, .mf-meter, .mf-count. New tokens in the single :root: --table-head-h, --table-row-hover, --table-sticky-max, --meter-track, --meter-fill, --radius-pill. Documented in DESIGN.md §5.11.
- No backend, API, permission, schema, migration or dependency change.
- Tests: new tests/test_ui_productivity_consolidation.py (19 passed, node on host). Focused host runs green: test_ui_canonical_nav (20), test_ui_inventory_contract (12), test_ui_system_console_consolidation (12), test_v71_ui_foundation (7), design-token/radius contracts. Broad static suite in the `mesflow-aw0926-tests` image (`-m "not postgres and not integration and not slow"`, e2e/integration dirs ignored, dummy DATABASE_URL + MESFLOW_ENV=test + MESFLOW_SECRET_KEY): 1204 passed, 3 failed, 51 skipped; the same 3 fail on the untouched baseline (test_autologin_guard_unit x2, test_kiosk_errors_are_logged_and_classified) -> no new failures. Local host python lacks flask/openpyxl; run such tests in that image.
- DEV deploy: image mesflow-app:ui-p3-c78f040 built from the integration worktree; mesflow-dev Compose project updated; /home/dell/workspace/mesflow-dev/.env MESFLOW_IMAGE changed from the stale mesflow-app:71.0.0.370 to mesflow-app:ui-p3-c78f040 (P2 had deployed via a command-line override, so a plain `up -d` would have regressed DEV). https://dev.mesflow.net/api/system/ready -> commit c78f040, 71.0.0.376, DEV, ready, migration 0054. mesflow.net (PRODUCTION_TEST) untouched: still 71.0.0.376 / commit unknown.
- Browser verification on public https://dev.mesflow.net (Playwright in the mesflow-aw0926-playwright image, --network host) at 1920x1080, 1366x768, 390x844, refactor mode plus legacy mode at 1366: title "Năng suất", 2 inline tabs with correct active tab, shell strip hidden, 4 KPIs, sticky header, numeric cells right-aligned, 0px body horizontal overflow, no console/page errors. Filters kept across Nhân viên -> Operation -> Nhân viên; the Excel request carried from/to/search/sort/dir. Filtered export downloaded from DEV: 200 xlsx, header ends in "NV xác nhận", search=Mơ -> 1 row. Screenshots: docs/ui-golden/productivity/*.png.
- Known risks / notes: static assets use `?v=<version>` and the version was not bumped (same as P2), so browsers with a cached 71.0.0.376 ui.css/app.js may show stale UI for up to max-age=14400s (hard-reload fixes it). A dirty sibling worktree /home/dell/workspace/.worktrees/mesflow-ui-dev-default-20260929 (branch ui-refactor/dev-default-canonical-20260929, uncommitted app.py server_role change) belongs to another task and was not touched. No Operation-tab Excel export exists (none existed before); candidate for a later phase.
- Next: P4 Master Data (Employees + QR Print + Equipment) using the P3 primitives; then P5 Quality, P6 Kiosk, P7 Trace/Logs, P10 Planning, P11 Admin, P8 Sessions, P9 Overview, P12 cleanup.


## Public showcase landing + isolated demo (2026-10-05)
- CI follow-up 2026-10-06: the rework overview regression now explicitly sets the Part planned quantity to 100 before asserting 92%/98% progress. The production query intentionally returns progress_percent=null when no operation/part planned quantity is configured; the old test depended on that missing denominator while testing an unrelated rework rollup concern. Commit 0586302f contains the test correction.

- Branch: `feat/showcase-landing-demo` (customer-facing showcase work; keep separate from production rollout until merged/deployed).
- Public routes added: `/welcome` and `/demo`.
- `/welcome` is a marketing/product landing with a direct “Dùng thử demo” CTA and clear MESFlow workflow/value explanation.
- `/demo` is intentionally client-only: fixed sample data, no `/api/*` calls, no database/session/admin token, no write actions. It demonstrates Overview → Kiosk flow → Exceptions → Productivity and provides a browser-only Reset Demo.
- Safety contract is guarded by `tests/test_showcase_public_routes.py`; production `/app`, auth, kiosk and data APIs are unchanged.
- Deployment state: code/PR only until the host is explicitly updated. Do not claim the routes are live until the public host is verified after merge/deploy.
- CI follow-up 2 (2026-10-06, run 37399700729): after the Python stage went
  green, the Playwright stage showed 3 hard failures + 1 flaky. None were
  caused by the showcase routes. main has the same latent failures, but main's
  CI stops at the Python stage, so it never reaches Playwright. Fixes (branch
  `fix/pr30-ci-e2e` pushed into `feat/showcase-landing-demo`):
  - `daily-dashboard-kiosk.spec.js:243`: stale copy. 8f8eab3 renamed
    "Tỉ lệ NG cao" → "Tỉ lệ lỗi cao" in daily-dashboard-kiosk.js; the test now
    expects the shipped label.
  - `part-block-primitive.spec.js:206` "lệch tâm 44px": REAL UI regression from
    ea094c5 (.322). The Template editor OP row gained a 6th grid cell
    ("Dự kiến / 1 sản phẩm"), but the header/grid have 5 columns, so the delete
    button wrapped onto the flow-config line. Fix: `oldOperationRow` in
    `static/app.js` wraps the cycle input + metric in `.op-cycle-cell` (one cell
    under the "Thời gian / SP" header); CSS in `ui.css` next to the
    `.template-old-op-row .time-metric` rules. Keep the row at 5 cells.
  - `production-progressive-disclosure.spec.js:46` @390 (5.1 viewports): stale
    fixture. `tests/e2e/helpers/hp3-fixtures.js` `scaleOverview` lacked the
    `progress_planned_qty/progress_actual_good_qty/progress_missing_operation_count/progress_basis`
    fields `/api/dashboard/overview` has returned since a8977ef, so every PO
    rendered the taller "Chưa có định mức sản lượng" state. The fixture now
    mirrors analytics.py `progress_rollup` (sum of done / sum of plan). The
    5-viewport threshold is unchanged.
  - `network-resilience.spec.js:79` (flaky): test race, not a product bug.
    `/app` lands on Tổng quan, whose first GET may still be in flight when the
    test goes offline; `openPage` then shares it via the MFNet in-flight GET
    dedupe and correctly renders the real data. The test now waits for
    `#ovPos .overview-loading` to clear before `setOffline(true)`.
  - Verification on dell (isolated stack `docker compose -p mesflow-t-pr30 -f
    compose.test.yml`): the 4 specs, `--retries=0`: 58/58 passed;
    network-resilience `--repeat-each=8`: 72/72 passed. Python stage (`tests`
    service): 386/874/45/617 passed, "All suites passed". Full Playwright:
    585 passed / 4 skipped / 1 failed; the 1 was the ESP tutorial test, from a
    missing local fixture. After `scripts/test/generate-esp-tutorial-fixture.sh`,
    `mesflow.spec.js` passed 7/7.
  - Local repro gotchas (not CI issues): run the `tests` service BEFORE
    Playwright (`admin-list-card-consistency.spec.js:82` clicks the first real
    PO and times out on an empty DB), and generate the ESP fixture BEFORE the
    first `up`. Otherwise Docker creates `runtime/tutorials` empty and
    root-owned, and the generator fails with `mkdir: Permission denied`.
    `scripts/test/docker-test.sh` already does both.

## 71.0.0.382 release candidate: public showcase on the live UI line (2026-10-06)
- main 8337843 = squash of PR #30 (showcase `/welcome` + client-only `/demo`, plus the
  CI fixes from a1760dd; tree identical to a1760dd).
- mesflow.net (TEST) and DEV both ran 71.0.0.381 = commit e66587f, the UI refactor line
  merged with main. Deploying plain main there would wipe UI P0–P3, so the release is
  built on the refactor line instead:
  - branch `release/71.0.0.382-showcase`;
  - `8355f32` = merge of main 8337843 into refactor 8fa6145. Only conflict: this file
    (add/add, concatenated). app.js/ui.css merged automatically; `.op-cycle-cell` is
    present;
  - `dd5870c` = `scripts/bump-version.sh 71.0.0.382` (VERSION_VERIFY PASS).
- Local image `mesflow-app:dev-382-dd5870c` (sha256:b7d463cc…, VERSION 71.0.0.382,
  MESFLOW_BUILD_COMMIT dd5870c). No migration change (head stays 0054).
- Verified on dell, isolated `-p mesflow-t-rel382` stack:
  - Python stage: 386/902/45/617 passed. `docs/` was mounted read-only: `Dockerfile.test`
    does not COPY `docs/`, and refactor-line tests read `docs/ui-inventory.json`. This
    gap already existed on the refactor line; it is why that line's CI is red;
  - Playwright: 586 passed / 4 skipped / 0 failed;
  - showcase browser check @1366 + @390: `/welcome` 200 (4 demo links), `/demo` 200,
    exactly 1 request (`GET /demo`) after clicking every visible button, 0 `/api/*`,
    0 non-GET, no horizontal overflow.
- DEPLOY STATUS: NOT DEPLOYED. The agent's permission policy blocked changing the shared
  DEV pin (`mesflow-dev/.env` MESFLOW_IMAGE) and recreating the container, and TEST was
  not attempted. On 2026-10-06 https://mesflow.net/welcome returns 404 (still 381).
  Next steps for the operator:
  1. DEV: set `MESFLOW_IMAGE=mesflow-app:dev-382-dd5870c` in
     `/home/dell/workspace/mesflow-dev/.env`, run
     `docker compose -f compose.dev.yml up -d app`, then check
     `curl https://dev.mesflow.net/api/system/ready` → 71.0.0.382 / dd5870c.
  2. TEST: on the VPS, take a backup first:
     `sudo docker exec mesflow-patroni-test pg_dump -U postgres -Fc mesflow > ~/backups/mesflow-pre-382-<ts>.dump`.
     Then `docker tag mesflow-app:dev-382-dd5870c mesflow-app:71.0.0.382` and
     `REMOTE_TEST_TARGET_FILE=<main checkout>/scripts/remote-test-target.env REMOTE_TEST_SSH_CONFIG=~/.ssh/config scripts/deploy-remote-test.sh 71.0.0.382`.
     Rollback image: `mesflow-app:71.0.0.381` (d4786d47) is still on the VPS.
  3. Verify https://mesflow.net/welcome and /demo (200, `/demo` 0 `/api/*` requests).
- mesflow-demo.mesflow.net is a different public demo (gateway + viewer, image 381). Its
  gateway owns `/demo`, so the app's `/demo` is not reachable there. It was left unchanged.
