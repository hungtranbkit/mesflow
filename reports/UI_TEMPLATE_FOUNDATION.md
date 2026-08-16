# MESFlow UI Template Foundation — Golden Reference Migration

Date: 2026-08-16
Project: `~/workspace/mesflow/mesflow`
Branch: `main`

Companion document: `docs/architecture/UI_TEMPLATE_STANDARD.md` (Phases 1–11:
audit, canonical shell/archetypes/primitives/tokens/contracts). This report
covers Phase 12 onward: foundation implementation, the three Golden
Reference pages, testing, build/deploy, and evidence.

## CURRENT UI ARCHITECTURE

`app.html`'s App Shell (`.app-layout > .app-sidebar + .app-workspace
(.workspace-header + #content)`) is universal and was already consistent.
The problem was entirely inside `#content`: MESFlow had **six different
in-content page-header implementations** (`.panel-head`, `.po-list-head`,
`.ui-page-header`, `.overview-intro`, `.daily-command-copy`,
`.template-command`), none of which matched `DESIGN.md`'s own typography
table (Section title: 18/24, weight 650–700) — they ranged from 15px to
21px, each a different value. Repeated CSS-only polish passes earlier this
session (documented in `reports/UI_QUALITY_AUDIT_FINAL.md` and
`reports/UI_VISUAL_POLISH_PASS2.md`) fixed real defects but never touched
this structural root cause, which is why pages kept reading as
inconsistent no matter how much individual-property polish was applied.

## NEW UI CONTRACT

```
MESFlowAppShell
├── Sidebar          (unchanged, already consistent)
├── Topbar            .workspace-header — compact, title+1-line context, no actions
└── PageShell         #content
    ├── PageHeader     NEW: .page-header — title/description left, actions right
    ├── FilterBar      MFUI.filterBar() + unified toolbar-container CSS (already done pre-task)
    ├── StatsRow       optional, already consistent (ordering fixed pre-task)
    ├── ContentSection Panel / DataTable
    └── Drawer/Modal   MFUI.openDrawer/openModal (already correct)
```

Full detail in `docs/architecture/UI_TEMPLATE_STANDARD.md`.

## PAGE ARCHETYPES

A. List (Production Orders, Employees, Equipment, Users, Working Calendar)
B. Detail (PO workspace, Session Detail, Template editor)
C. Monitor (Dashboard, Production Trace, Kiosk Management)
D. Workflow (Session Exception Center)
E. Audit (Business Audit, System Logs)

## PRIMITIVES

| Primitive | Status |
|---|---|
| PageShell | Existing (`#content` + optional `MFUI.pageShell()`) — unchanged |
| **PageHeader** | **New shared `.page-header` class** — the one structural gap; added this task |
| FilterBar | Existing (`MFUI.filterBar()` + shared toolbar CSS), documented as canonical |
| StatsRow | Existing, unchanged |
| Panel | Existing, already matched `DESIGN.md` §5.3 |
| DataTable | Existing `<table>`/`.table-wrap`; added `.num` numeric-column-alignment utility |
| Drawer/Modal | Existing `MFUI.openDrawer`/`openModal`, unchanged |

## TOKENS

No new tokens needed — `ui.css`'s tokens already match `DESIGN.md` exactly.
`.page-header`'s title (18px/24px/700) is the first CSS rule to actually
implement `DESIGN.md`'s documented-but-never-wired "Section title" role.

## SHARED FILES CHANGED

- `app/mesflow/web/static/ui.css` — added `.page-header`/`.page-header-actions`
  (canonical PageHeader), `.table-wrap table th.num`/`td.num` (numeric
  column alignment utility), `.ec-command h2` explicit token-based
  typography (was an accidental browser-default size).
- `app/mesflow/web/static/app.js` — Production Orders' `.po-list-head`
  gained the `page-header` class; its "Kế hoạch" column header/cells
  gained `.num`. Session Management's page-level header was rebuilt using
  `.page-header` with copy distinct from the Topbar (was removed entirely
  in a prior commit this session after a duplicate-title report; this
  migration restores a proper in-content header, matching every other
  List-archetype page, without repeating the Topbar's exact title).
- `docs/architecture/UI_TEMPLATE_STANDARD.md` — new (Phases 1–11).
- `reports/UI_TEMPLATE_FOUNDATION.md` — this report.

Session Exception Center (the Workflow archetype) intentionally did **not**
get a `.page-header` inserted above its "Action Required" banner — see the
reasoning in `docs/architecture/UI_TEMPLATE_STANDARD.md` Phase 6 and the
`.ec-command h2` code comment: `DESIGN.md`'s own attention-priority
principle (exceptions/incidents read first) is directly served by the
banner being the first thing on screen, and the banner is not a title
duplicate — the Topbar says "Trung tâm ngoại lệ", the banner says "Action
Required" (a distinct, more urgent framing). Only its typography was moved
from an accidental default onto the token scale.

## GOLDEN PAGE 1 — PRODUCTION ORDERS

**BEFORE**: `.po-list-head` title at a bespoke 20px with no explicit
font-weight; "Kế hoạch" (quantity) column left-aligned like every text
column, against `DESIGN.md` §5.5's explicit numeric-alignment requirement.

**AFTER**: title now 18px/24px/700 via `.page-header` (shared class, same
size Session Management now also uses); "Kế hoạch" header and every row's
quantity cell right-aligned with `font-variant-numeric: tabular-nums`
(verified live: `getComputedStyle(td.num).textAlign === 'right'`).

Screenshots: `reports/screenshots/golden-pages-before/production-orders-*.png`
→ `reports/screenshots/golden-pages-after/production-orders-*.png`.

## GOLDEN PAGE 2 — SESSION MANAGEMENT

**BEFORE**: no in-content page header at all (removed in commit `7b36c74`
after a real duplicate-title defect report — the old `MFUI.pageShell()`
call repeated "Quản lý Session" a second time directly under the Topbar in
different styling). Went straight from Topbar into the filter toolbar,
inconsistent with every other List-archetype page.

**AFTER**: proper `.page-header` restored — title **"Danh sách Session"**
(deliberately distinct from the Topbar's "Quản lý Session", mirroring how
Production Orders' Topbar says "Production Order" while its in-content
header says "Quản lý lệnh sản xuất") + a one-line description + the "Làm
mới" action relocated here from the sub-panel below (Phase 7's rule:
primary/utility actions belong in PageHeader, not buried in a sub-panel
head). Verified the relocated button still works: clicking `#smReload`
fires the expected `/api/work-sessions` request.

Screenshots: `reports/screenshots/golden-pages-before/session-management-*.png`
→ `reports/screenshots/golden-pages-after/session-management-*.png`.

## GOLDEN PAGE 3 — SESSION EXCEPTION CENTER

**BEFORE/AFTER**: structurally unchanged by design (see reasoning above);
only its "Action Required" heading gained an explicit, token-based size
(20px/26px/750) in place of an accidental browser-default `h2`. Confirmed
via screenshot comparison that this is visually a refinement, not a
regression — the banner still reads first, still uses the same dark/amber
urgent treatment.

Screenshots: `reports/screenshots/golden-pages-before/session-exceptions-*.png`
→ `reports/screenshots/golden-pages-after/session-exceptions-*.png`.

## 1920x1080

All three pages verified: consistent `.page-header` typography/spacing
where present, 0 horizontal overflow, 0 console errors.

## 1366x768

All three pages verified: same consistency, filter/toolbar rows wrap
cleanly where content requires it (Session Management's search+button
group wraps to a second row inside the same bordered toolbar — expected,
not a defect), 0 horizontal overflow, 0 console errors.

## FUNCTIONAL REGRESSIONS

**None found.** Specifically re-verified after the header relocation:
- Production Orders: PO list loads, "Mở PO" navigates to detail, back
  navigation returns to the list, numeric column renders correctly.
- Session Management: filter fields work, "Thêm bộ lọc" disclosure toggles,
  the relocated "Làm mới" button still fires its reload request.
- Session Exception Center: tab switch, card click → drawer open, drawer
  close all still work.

## TESTS

| Check | Result |
|---|---|
| CSS brace balance | balanced |
| `node --check app.js` | OK |
| Python compile (`web/app.py`) | OK |
| Jinja parse (`app.html`, unchanged) | OK |
| `git diff --check` | clean |
| `tests/test_v71_ui_foundation.py`, `tests/test_web_ui.py` | 7 passed, 0 failed |
| Full 16-page × 2-viewport Playwright audit | 32/32 captures, 0 overflow, 0 console/page errors, 0 failed requests |
| 12-check functional smoke pass | 12/12 passed |

## LOCAL BUILD

```
build-release.sh --bump
IMAGE RELEASE PASS
Version: 71.0.0.16
Digest: sha256:adbdc250f363ce0c1a0f5b197ba3802d21d0058123c8ae6b223bab6bc3818d35
Schema: 0037_v72_audit_operations_separation
```
(71.0.0.9 through .15 were already frozen releases from earlier this session.)

## LOCAL DEPLOY

Deployed via Deploy Agent's official `/api/release-manager/deploy-local`
(same action the Deploy Agent UI's "Deploy Local" button performs). Job
progression: `deploying` → `"CUTOVER: stopping application only; gateway
and PostgreSQL remain running"` → `verifying` → `success — "Deployment
verified: 71.0.0.16"`.

## LOCAL HEALTH

```json
{"status":"healthy","version":"71.0.0.16","schema_version":"72.0.0.0",
 "database_backend":"postgresql","postgres_version":"17.10"}
```
`mesflow-postgres` uptime unaffected (27h, never restarted).

## READY TO FREEZE UI STANDARD: YES

The three Golden Reference pages now share one canonical PageHeader
component (Production Orders and Session Management use it identically;
Session Exception Center's variant is a documented, principled exception
tied to `DESIGN.md`'s own attention-order rule, not an unmigrated gap), one
FilterBar contract, one numeric-table-alignment convention, and pass every
static/functional/visual check at both required viewports. The standard
document (`docs/architecture/UI_TEMPLATE_STANDARD.md`) is ready to govern
the next migration batch.

## REMAINING PAGES NOT MIGRATED

Overview, Dashboard, Templates, Production Trace, Business Audit,
Production Schedule, System Logs, QR Print, Equipment, Users, Working
Calendar, Kiosk Management — all still on their pre-existing header
implementations (`.panel-head`, `.overview-intro`, `.daily-command-copy`,
`.template-command`, etc.), left untouched per the explicit stop condition.
They remain visually reasonable (verified via this session's earlier polish
passes) but do not yet use the new `.page-header` class. Per the task's stop
condition, no further pages were migrated in this task.

**PRODUCTION TEST TOUCHED: NO**
**PRODUCTION TOUCHED: NO**
