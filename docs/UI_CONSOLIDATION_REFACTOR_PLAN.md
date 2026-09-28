# MESFlow UI Consolidation Refactor Plan

Status: PLAN ONLY - DO NOT DEPLOY
Branch: refactor/ui-consolidation-20260928
Worktree: /home/dell/workspace/.worktrees/mesflow-ui-consolidation-20260928
Base: main@8aa78a6
Production-test canonical: https://mesflow.net - this branch must not deploy there until explicit UAT approval.

## 1. Objective

- Reduce the current 25 sidebar destinations to about 11 canonical workflow screens.
- Preserve all existing business features, permissions, deep links, exports, kiosk modes and auditability.
- Replace duplicated screens with canonical screens plus tabs/subviews.
- Keep legacy URLs as compatibility aliases until all callers and tests have migrated.
- Avoid another large-bang UI regression: each consolidation phase must be independently testable and reversible.

## 2. Non-goals

- No production database redesign as part of the UI consolidation.
- No removal of business APIs just because a screen is merged.
- No production or production-test deployment from this branch before final UAT approval.
- No deletion of legacy routes until aliases, deep-link tests and permission tests are green.
- No rewrite of Overview logic, session accounting or productivity formulas unless required by a documented UI contract.

## 3. Target canonical information architecture

1. Tổng quan - tabs Realtime and Theo ngày.
2. Kế hoạch sản xuất - Production Order plus Gantt and Material Flow.
3. Template - canonical process and part and operation templates.
4. Điều hành phiên - Tất cả phiên plus Bất thường.
5. Chất lượng - Rework and QC.
6. Năng suất - Nhân viên plus Operation KPI.
7. Trạm kiosk - Trạm plus Sự kiện.
8. Danh mục - Nhân viên plus QR plus Thiết bị.
9. Truy vết and Nhật ký - Production Trace plus Business Audit plus Application Log.
10. Quản trị - Người dùng and quyền plus Lịch and ca làm.
11. Hệ thống - Super Admin console with system tabs.

- Hướng dẫn moves to the global header as a help action, not a primary sidebar destination.
- Notifications moves to the global header inbox, not a primary sidebar destination.
- Daily-dashboard-kiosk remains a presentation mode, not a normal sidebar screen.
- Worker kiosk and productivity wallboard remain standalone runtime surfaces.

## 4. Canonical route and compatibility map

| Legacy or current page | Canonical destination | Migration rule |
| --- | --- | --- |
| dashboard | overview?tab=daily | Preserve old URL as alias |
| session-management | operations-sessions?tab=all | Canonical session screen |
| session-exceptions | operations-sessions?tab=exceptions | Preserve context and Back behavior |
| sessions | operations-sessions?tab=all | Legacy alias only |
| rework-queue | quality?tab=rework | Canonical quality screen |
| qc | quality?tab=qc | Legacy alias |
| employee-productivity | productivity?tab=employees | Canonical productivity screen |
| kpi-employees | productivity?tab=employees | Legacy alias |
| kpi-operations | productivity?tab=operations | Legacy alias |
| kiosk-management | kiosk-admin?tab=stations | Canonical kiosk admin screen |
| kiosk-events | kiosk-admin?tab=events | Legacy alias |
| production-trace | trace-logs?tab=trace | Canonical trace and logs screen |
| business-audit | trace-logs?tab=business | Preserve permissions |
| system-logs | trace-logs?tab=application | Preserve permissions |
| monitoring | system?tab=overview | Super Admin or legacy alias as appropriate |
| production-orders | planning?tab=orders | Canonical planning screen |
| production-schedule | planning?tab=schedule | Gantt and Material Flow subview |
| employees | master-data?tab=employees | Canonical master data screen |
| qr-print | master-data?tab=qr | Keep print workflows intact |
| equipment | master-data?tab=equipment | Canonical master data screen |
| users | admin?tab=users | Preserve role deep links |
| working-calendar | admin?tab=calendar | Preserve shift editing |
| tutorials | Global help action | Alias remains during transition |

Rule: canonical navigation changes first. Business logic moves only after route and permission contracts are stable.

## 5. Git and isolation strategy

- This branch is the long-lived UI integration branch.
- Every implementation phase uses a short-lived child branch based on this branch, for example ui-refactor/p01-shell or ui-refactor/p04-productivity.
- Child branches merge only into refactor/ui-consolidation-20260928, never directly into main.
- main may continue receiving production hotfixes independently.
- Sync main into the refactor branch only at controlled checkpoints, one sync commit at a time, followed by the full UI contract suite.
- Never resolve a conflict by blindly choosing ours or theirs for Overview, session or navigation files. Compare route, markup and CSS contracts explicitly.
- No deploy scripts are run from this refactor worktree until final UAT approval.
- Final promotion to main happens once, after the complete compatibility and regression matrix passes.

## 6. Phase plan

### P0 - Baseline and guardrails
- Freeze inventory: 25 sidebar screens, 9 hidden SPA pages, 4 standalone surfaces.
- Record canonical route IDs, permissions and deep-link query parameters.
- Add automated route inventory test so screen count changes are intentional.
- Add compatibility redirect helper and tab URL contract.
- Add shared PageShell, Tabs and Empty/Error/Loading contracts without changing visible behavior.
- Baseline critical screens at 1366x768, 1920x1080 and mobile widths.
DoD: zero visible behavior change; baseline tests pass.

### P1 - Navigation shell
- Replace sidebar definition with canonical 11-screen IA behind a feature flag local to the refactor branch.
- Add canonical tab routing via ?tab=.
- Preserve browser Back, refresh and deep links.
- Move Help and Notifications to global header actions.
- Keep all legacy page IDs addressable through aliases.
DoD: every old page ID lands on an equivalent canonical screen and permissions remain unchanged.

### P2 - System console consolidation
- Merge system-overview, system-errors, system-logs-it, system-services, system-diagnostics and system-audit into one System screen.
- Lazy-load each tab to avoid heavy initial requests.
- Keep Super Admin visibility and API authorization unchanged.
DoD: six old URLs deep-link to correct tabs; restart and diagnostics actions still work.

### P3 - Productivity consolidation
- Make productivity the canonical screen.
- Tabs: Nhân viên and Operation.
- Merge kpi-employees and kpi-operations views into the same shell.
- Preserve current employee filters, filtered KPI recalculation, Excel export and NV xác nhận column.
- Keep employee detail drill-down and wallboard links.
DoD: productivity calculations and exported rows exactly match active filters.

### P4 - Master data consolidation
- Combine Employees, QR Print and Equipment into Master Data tabs.
- Keep employee CRUD, badge and QR flows intact.
- QR bulk print becomes a tab/action, not a top-level screen.
DoD: no loss of CRUD, import/export or print capability.

### P5 - Quality consolidation
- Combine Rework Queue and QC into one Quality screen.
- Tabs: Rework and QC.
- Preserve defect quantities, rework resolution, exclusion semantics and trace links.
DoD: all existing rework and QC actions remain auditable.

### P6 - Kiosk administration consolidation
- Combine Kiosk Management and Kiosk Events.
- Tabs: Stations, Events and Health if needed.
- Do not modify worker kiosk runtime pages in this phase.
DoD: station registration, health and event history remain available.

### P7 - Trace and logs consolidation
- Combine Production Trace, Business Audit and Application Logs.
- Tabs preserve permission boundaries; unauthorized tabs are not rendered.
- Cross-links from PO, session, employee and exception views open the correct trace context.
DoD: trace context survives refresh and Back.

### P8 - Session operations consolidation
- Highest-risk operational phase.
- Combine Session Management, Session Exceptions and legacy Sessions.
- Tabs: All Sessions and Exceptions; detail remains the shared in-place drawer.
- Preserve session filters, exception reason and correction flows, return context and multi-session behavior.
- Legacy session URLs become aliases only after E2E coverage is green.
DoD: no change to session accounting, close/reopen behavior, quantity edits or audit records.

### P9 - Overview and daily dashboard consolidation
- Highest-risk visual phase; do late.
- One Overview screen with Realtime and Theo ngày tabs.
- Realtime preserves mini dashboard, worker rows, active/finished dots, aligned compact grid and OP double-click detail.
- Theo ngày preserves date filter, employee productivity summary and daily metrics.
- Do not reuse old overview-v2 entrypoints.
DoD: screenshot/layout contracts pass at 1366x768 and 1920x1080; mobile remains usable.

### P10 - Planning consolidation
- Combine Production Orders and Gantt/Material Flow as Planning tabs.
- Production Order remains the default tab.
- PO detail keeps a stable deep link and Back behavior.
- Material flow may reuse existing API and rendering code without moving backend logic.
DoD: PO create/edit/detail, progress and Gantt all survive refresh/deep link.

### P11 - Admin consolidation
- Combine Users/Roles and Working Calendar.
- Tabs: Users and Roles, Calendar and Shifts.
- Preserve Super Admin safeguards and role permission deep links.
DoD: permission changes and calendar editing remain fully audited.

### P12 - Legacy retirement and cleanup
- Remove hidden pages only after zero production references remain.
- Delete duplicate renderers, CSS and obsolete tests.
- Keep compatibility aliases for one release cycle if cheap.
- Produce final route map and operator/admin release notes.
DoD: no dead menu entries, no duplicate canonical renderer, no stale page entrypoint.

## 7. Required regression matrix

Every phase must pass the following before merge into the long-lived refactor branch:

- Navigation: direct URL, refresh, Back, Forward, sidebar click and tab switching.
- Permissions: Admin, Super Admin and restricted roles see exactly the same allowed capabilities as before.
- Desktop layout: 1366x768 and 1920x1080.
- Mobile layout: 390x844 and 430x932.
- Loading, empty and error states for every merged tab.
- Deep links: PO detail, Session detail, exception context, role permissions and employee detail.
- Overview contracts: mini dashboard, aligned compact grid, worker green and gray dots, OP double-click detail.
- Session contracts: multi-open sessions, end-of-day boundaries, quantity correction and exception audit.
- Productivity contracts: filter-recalculated KPI, Excel export, NV xác nhận and wallboard.
- Print contracts: QR print and setup print.
- Kiosk contracts: worker scan runtime must be unchanged by admin navigation refactor.
- System contracts: diagnostics and service actions remain Super Admin only.

A phase that cannot pass its existing tests must not be hidden behind a new tab and called complete.

## 8. Test layers

Layer 1 - source and contract tests: route IDs, alias map, tab map, permission map, no duplicate canonical IDs.
Layer 2 - unit tests: tab state, filter state, summary calculation and URL serialization.
Layer 3 - API integration: merged pages must still call the same APIs with the same parameters.
Layer 4 - browser E2E: desktop and mobile flows, Back and refresh, modal and drawer behavior.
Layer 5 - screenshot or geometry contracts: especially Overview, session tables, productivity and planning.
Layer 6 - UAT checklist with realistic test data before any deploy candidate is built.

## 9. Feature flag and rollout strategy

- During development, old and new navigation may coexist behind a refactor-only flag.
- The flag is enabled only in the refactor worktree or a dedicated isolated preview environment.
- Do not point mesflow.net at this branch.
- Before final promotion, run one dedicated preview stack with a copied or test database, never the active production-test database if schema behavior would change.
- Final release is promoted only after explicit user approval.
- First release keeps aliases and rollback paths.
- A later cleanup release may delete dead legacy renderers after telemetry and logs show no use.

## 10. Merge order and dependency graph

P0 baseline -> P1 navigation shell.
P1 -> P2 System, P3 Productivity, P4 Master Data, P5 Quality, P6 Kiosk, P7 Trace and Logs can proceed mostly independently.
P1 + P7 -> P8 Session because session return-context depends on navigation and trace links.
P1 + stable shared tabs -> P9 Overview because Overview is visually fragile and should be changed late.
P1 -> P10 Planning.
P1 -> P11 Admin.
P2-P11 green -> P12 legacy cleanup.

Recommended order for agents: P0, P1, P2, P3, P4, P5, P6, P7, P10, P11, P8, P9, P12.

## 11. Phase task template for agents

Each phase PR or merge commit must contain:
- Scope statement: exact old pages and target canonical screen.
- Route alias changes.
- Permission impact statement.
- UI component changes.
- Tests added or updated.
- Screens or geometry checks at required viewports.
- Explicit statement of APIs not changed.
- Rollback note.
- No deploy command.

Each agent must stop if it encounters unrelated main-line production hotfix code and request a controlled sync instead of resolving it opportunistically.

## 12. Concrete work packages

### WP-00 Inventory and contracts
- Generate machine-readable list of current menu pages and hidden pages.
- Generate route-to-renderer map.
- Generate permission-to-page matrix.
- Add a test that fails when a page ID is added or removed without updating the inventory.

### WP-01 Shared navigation primitives
- Canonical PageShell.
- Canonical Tabs component.
- URL tab state and deep-link helper.
- Compatibility alias resolver.
- Unified Back and Close semantics.

### WP-02 System
- Create system canonical shell.
- Port six existing renderers as tab bodies without rewriting business logic.
- Add lazy loading and per-tab permission checks.
- Convert old system page IDs into aliases.

### WP-03 Productivity
- Create productivity shell.
- Employees tab starts from the current employee-productivity implementation.
- Operations tab absorbs kpi-operations.
- Redirect kpi-employees to Employees tab.
- Keep filters and Excel export bound to the active tab state.

### WP-04 Master Data
- Create master-data shell.
- Employees tab.
- QR tab with existing bulk print flow.
- Equipment tab.
- Preserve all create and edit drawers and QR print selections.

### WP-05 Quality
- Create quality shell.
- Rework tab.
- QC tab.
- Unify defect terminology and links without changing quantities or accounting.

### WP-06 Kiosk Admin
- Create kiosk-admin shell.
- Stations tab.
- Events tab.
- Optional Health subview if it reduces clutter.
- No changes to kiosk.html runtime.

### WP-07 Trace and Logs
- Create trace-logs shell.
- Trace tab.
- Business audit tab.
- Application log tab.
- Keep search and filters per tab; do not mix datasets.

### WP-08 Sessions
- Create operations-sessions shell.
- All Sessions tab uses current session-management as canonical implementation.
- Exceptions tab embeds current session-exceptions logic.
- Shared Session Detail drawer remains single-source.
- Preserve return context and deep-link session query.

### WP-09 Overview
- Add tab shell around existing Overview and Daily Dashboard implementations.
- Never swap overview.js to an older alternate entrypoint.
- Keep exact compact-grid class contract.
- Keep OP double-click and worker status rows.

### WP-10 Planning
- Planning shell with Orders and Schedule tabs.
- Keep Production Order detail route stable.
- Gantt and Material Flow becomes schedule tab content.

### WP-11 Admin
- Admin shell with Users and Calendar tabs.
- Roles stays a subview inside Users.
- Preserve Super Admin password and privilege safeguards.

### WP-12 Cleanup
- Delete page IDs proven unused after aliases have served one release cycle.
- Remove duplicate CSS selectors and stale page files.
- Regenerate route inventory and architecture docs.

## 13. Final promotion gates

- 0 uncommitted files in the refactor worktree.
- Full targeted test suite green.
- Full browser smoke across all 11 canonical screens.
- No 404 or permission drift for legacy deep links.
- No Overview layout regression at desktop or mobile breakage.
- No session accounting regression.
- Excel export from Productivity works with filters and NV xác nhận.
- Kiosk and wallboard standalone surfaces verified unchanged.
- Production-test deploy remains a separate explicit approval step.
- main is updated only after final UAT sign-off.
