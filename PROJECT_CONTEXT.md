# PROJECT_CONTEXT.md

## MESFlow UI consolidation - current handoff

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
