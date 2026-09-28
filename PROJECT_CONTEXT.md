# PROJECT_CONTEXT.md

## MESFlow UI consolidation - current handoff

Date: 2026-09-28
Long-lived integration branch: refactor/ui-consolidation-20260928
Current child task branch: ui-refactor/p0-p1-nav-shell-20260928
Production-test mesflow.net must not be deployed from this refactor line without explicit approval.

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
P2 System console consolidation, then P3 Productivity, P0 Master Data, P5 Quality, P6 Kiosk Admin, P7 Trace/Logs, P10 Planning, P11 Admin, P8 Sessions, P9 Overview, P12 cleanup.

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
