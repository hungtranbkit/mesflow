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
- dev.mesflow.net was still on version 71.0.0.370 before this P0/P1 deployment.
- P0/P1 must deploy only to DEV using compose.local-test.yml and .env.local-test.
- mesflow.net / production-test must remain untouched.
- After DEV deploy, update this section with DEV health/version and live canonical asset verification.

### Next phases after P0/P1
P2 System console consolidation, then P3 Productivity, P0 Master Data, P5 Quality, P6 Kiosk Admin, P7 Trace/Logs, P10 Planning, P11 Admin, P8 Sessions, P9 Overview, P12 cleanup.
