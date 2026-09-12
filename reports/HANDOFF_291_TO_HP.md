# Handoff — MESFlow integration lane → HP (2026-09-12)

## DEPLOYED & VERIFIED: 71.0.0.291 (TEST / PRODUCTION_TEST)
- Public: https://mesflow.net  → version 71.0.0.291, commit 965463b2fd25, server_role PRODUCTION_TEST, status ready, healthy, pg 17.10
- Running image digest: sha256:cdc70a405958126a79540c69fa489b3aeb06797e7543e99865e60b3d77f38cef
- migration_head: 0050_user_session_epoch (UNCHANGED from 290 — both hotfixes are UI-only, no new migration)
- Branch: integration/daily-dashboard-test @ 965463b (pushed to origin)

## What shipped in 291 (two DONE hotfixes merged on 290/b35f27b)
1. hp3 Gantt mobile — ad6d03a — REQ-UI-023. Mobile filter = tool (fixed sheet, not sticky content); toolbar 49px, PO header 77.3px; scroll 320/375/390. Merge commit ead8c7c.
2. hp4 sidebar — f88baff (+6385c50) — REQ-UI-021. Left nav rail to one dark palette + one status scale; --nav-* tokens, scoped selectors. Merge commit 269f442.
- Merged clean (no conflicts) despite both touching app.js/ui.css/both REQ docs. No REQ-ID collision (023 vs 021). JS syntax OK, CSS braces balanced.
- Live static bundle confirmed carrying both: ui.css --schedule-toolbar-height ×10, --nav-surface ×25.

## Gate (on the exact merged tree, --retries=0 for reruns)
- pytest: 140 unit + 590 static + 44 behavioral + 502 integration = 1276 passed, +1 xfail (rework_qty two-meaning bug, Rework lane, documented).
- Playwright: 448 passed, 4 skipped, 2 flaky.
  - Flaky pair: network-resilience.spec.js:79 and session-management-dependent-filters.spec.js:110.
  - NEITHER touches Gantt/sidebar. ISOLATED RERUN --retries=0 → 12/12 PASSED (56.1s). Proven ambient (setOffline timing + a /app double-navigation race), not regressions.
- Both hotfix contract suites GREEN: sidebar-nav-surface.spec.js (9), schedule-mobile-layout.spec.js, schedule-mobile-scroll-contract.spec.js.

## DEFERRED to HP (the >10-min round I did not start on a shutting-down Dell)
- Optional: live-browser visual QA of 291 on mesflow.net at mobile viewports 320/375/390 — open Gantt (production-schedule) + toggle filter sheet + scroll; open sidebar groups. Contract E2E already covers the structure; this is eyeball confirmation only.
- Not required for release; 291 is fully gated + deployed + health-verified.

## Queue after 291 (nothing "ready" pending)
- hp3/kiosk-dense-control-room (45c09f3): NOT ready — must rebase onto 288+ (reintroduces hardcoded #101824 that hp1 removed). hp3 notified.
- fix/ui-consistency-kiosk-qr-utility-hp4 (7838982): withdrawn — needs rebase + canonical radius rewrite.
- No untouched real-production changes. Never touched real prod.

## Env notes for HP
- Deploy from a checkout that has scripts/remote-test-target.env (main checkout: /home/dell/workspace/mesflow/mesflow), OR export REMOTE_TEST_TARGET_FILE to it.
- Dell hit Docker address-pool exhaustion mid-session (release smoke). Fix: `docker network prune -f` + tear down finished lane stacks before building. Other lanes' stacks (mesflow-int, mesflow1, mesflow2-*) were left running — do not kill them.
- bump/build/deploy scripts are bash (not sh/dash): run with `bash scripts/...`.
