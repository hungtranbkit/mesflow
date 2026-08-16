# UI Template Migration — Batch A (List/Data-Heavy Pages)

Date: 2026-08-16
Project: `~/workspace/mesflow/mesflow`
Branch: `main`
Golden foundation used as source of truth: **71.0.0.17**
(`docs/architecture/UI_TEMPLATE_STANDARD.md`, `reports/UI_TEMPLATE_FOUNDATION.md`)

Pages migrated: **Employees, Equipment, Users, Working Calendar.** No other
page was touched. No backend, API, business logic, permission, or database
behavior was changed.

## Approach

Same primitives as the Golden pages, reused as-is (no new competing shell/
header/filter/panel was created):

- `.page-shell` (the shared `display:grid;gap:16px` layout parent)
- `.page-header` (title/description left, actions right — plain, no border)
- `MFUI.filterBar()` where the page has filters (Employees, Equipment, Users)
  — omitted for Working Calendar, which has no filter row (correctly "if
  applicable")
- the existing KPI card rows (`.employee-summary`/`.catalog-summary`/
  `.system-user-summary`) kept exactly as they already were (Pass 2 of this
  session already positioned them correctly, right after the header) —
  StatsRow is "optional" per the contract and these already satisfy it
  visually; no reason to force them into PO's plain-text `.stats-row` variant
  and lose the established KPI-card treatment used elsewhere in the app
- `.content-panel`/`.content-panel-head`/`.content-panel-body` wrapping each
  page's actual table, with a head title following the same "X theo bộ lọc"
  phrasing Session Management already established, distinct from both the
  Topbar and the PageHeader text (no repeated titles)

## Employees

**BEFORE STRUCTURE:**
```
<div class="panel">
  <div class="panel-head">title+desc+"+ Thêm nhân viên"</div>
  <div class="employee-summary">…KPI cards…</div>
  <div class="employee-tools">…bespoke 4-col grid: search/dept/status/reload…</div>
  <div id="employeeList">…result-count + table…</div>
</div>
```

**AFTER STRUCTURE:**
```
<div class="page-shell">
  <div class="page-header">title+desc+"+ Thêm nhân viên"</div>
  <div class="employee-summary">…KPI cards (unchanged)…</div>
  MFUI.filterBar(search + dept + status, actions: "Làm mới")
  <section class="content-panel">
    <div class="content-panel-head"><h3>Nhân viên theo bộ lọc</h3></div>
    <div class="content-panel-body" id="employeeList">…result-count + table (unchanged)…</div>
  </section>
</div>
```

**LEGACY CSS REMOVED:** `.employee-tools{…}` (grid layout), `.employee-tools
input,select{…}`; trimmed `.employee-tools` out of the shared
media-query/control-height selector lists it used to share with live classes.

**VISUAL NOTES:** Identical header/filter/panel geometry to Production
Orders (measured, see below). KPI cards unchanged (were already correctly
positioned from an earlier pass this session).

**FUNCTIONAL SMOKE:** search input filters the table live (`"Nguyen"` →
`employee-result-count` updated to `0 / 52`, cleared back to `52 / 52`);
"Sửa" opens the edit modal (`.modal-backdrop` present), closed without
saving. No console errors.

## Equipment

**BEFORE STRUCTURE:**
```
<section class="panel equipment-panel">
  <div class="panel-head">title+desc+"+ Thêm thiết bị"</div>
  <div class="catalog-summary">…KPI cards…</div>
  <div class="catalog-toolbar">…bespoke 4-col grid…</div>
  <div id="equipmentList">…</div>
</section>
```

**AFTER STRUCTURE:** same shape as Employees —
`.page-shell` → `.page-header` → `.catalog-summary` (unchanged) →
`MFUI.filterBar()` → `.content-panel` (head: "Thiết bị theo bộ lọc") →
`.content-panel-body#equipmentList`.

**LEGACY CSS REMOVED:** `.catalog-toolbar{…}` (grid layout) and its
900px/520px responsive overrides; `.equipment-panel .panel-head{…}` (the
wrapper section class is gone). `.catalog-toolbar` was combined with
`.qr-toolbar` in several shared rules (QR Print's toolbar, **still live,
not migrated in this task**) — only the `.catalog-toolbar` half of each was
removed, `.qr-toolbar` kept verbatim everywhere.

**VISUAL NOTES:** Identical geometry to Production Orders. Equipment
currently has 0 real records in this environment, so the empty state
("Không có thiết bị phù hợp") is what's visible in the screenshot — still
compact, sits correctly inside `.content-panel-body`.

**FUNCTIONAL SMOKE:** status filter interacts, "Làm mới" reload click
completes without error. No console errors.

## Users

**BEFORE STRUCTURE:**
```
<section class="panel system-user-panel">
  <div class="panel-head">title+desc+3 actions (Vai trò & phân quyền / Đổi mật khẩu / + Tạo người dùng)</div>
  <div class="system-user-summary">…KPI cards…</div>
  <div class="system-user-tools">…bespoke 3-col grid…</div>
  <div id="userList"></div>
</section>
```

**AFTER STRUCTURE:** `.page-shell` → `.page-header` (all 3 actions kept,
now in `.page-header-actions`) → `.system-user-summary` (unchanged) →
`MFUI.filterBar()` (search + role + status, no extra action needed) →
`.content-panel` (head: "Tài khoản theo bộ lọc") →
`.content-panel-body#userList`.

**LEGACY CSS REMOVED:** `.system-user-tools{…}` (grid layout) and its
label/input/select rules; `.system-user-panel .panel-head/.panel-actions{…}`
(520px); trimmed `.system-user-tools` out of shared selector lists.

**VISUAL NOTES:** Identical geometry to Production Orders. Three
page-header actions wrap/align the same way PO's three actions do.

**FUNCTIONAL SMOKE:** search input filters the account list (`"admin"` → 1
row shown, matching the only account in this environment); no destructive
action taken — permissions/roles were not modified, only read/filtered.

## Working Calendar

**BEFORE STRUCTURE:**
```
<div class="panel">
  <div class="panel-head">title+desc+"+ Thêm ca"</div>
  <div id="shiftList">…table…</div>
</div>
<div id="shiftEditor">…modal, unchanged…</div>
```

**AFTER STRUCTURE:** `.page-shell` → `.page-header` → `.content-panel`
(head: "Ca đang áp dụng") → `.content-panel-body#shiftList`. No FilterBar
(this page has none — correctly omitted per "FilterBar if applicable").
The shift editor modal markup is untouched.

**LEGACY CSS REMOVED:** none specific to this page (it only ever used the
generic `.panel`/`.panel-head`, which stay in use elsewhere and are not
page-specific dead code).

**VISUAL NOTES:** Identical header/panel geometry to Production Orders.
Simplest of the four migrations — no filter row, no stats row.

**FUNCTIONAL SMOKE:** "+ Thêm ca" opens the shift editor
(`#shiftEditor` loses `.hidden`); closed via "Đóng" without saving
(`#shiftEditor` regains `.hidden`). No console errors.

## EDGE ALIGNMENT

`getBoundingClientRect()` against the live deployed build, all four pages
vs. Production Orders (the Golden reference):

**1920×1080** (all values in px):

| Page | PageHeader L/R | FilterBar L/R | ContentPanel L/R |
|---|---|---|---|
| Production Orders (reference) | 272/1896 | 272/1896 | 272/1896 |
| Employees | 272/1896 | 272/1896 | 272/1896 |
| Equipment | 272/1896 | 272/1896 | 272/1896 |
| Users | 272/1896 | 272/1896 | 272/1896 |
| Working Calendar | 272/1896 | n/a (no filter row) | 272/1896 |

**1366×768:**

| Page | PageHeader L/R | FilterBar L/R | ContentPanel L/R |
|---|---|---|---|
| Production Orders (reference) | 248/1346 | 248/1346 | 248/1346 |
| Employees | 248/1346 | 248/1346 | 248/1346 |
| Equipment | 248/1346 | 248/1346 | 248/1346 |
| Users | 248/1346 | 248/1346 | 248/1346 |
| Working Calendar | 248/1346 | n/a | 248/1346 |

**Every measured edge matches Production Orders exactly — 0px difference**
at both viewports (well inside the ≤2px tolerance). PageHeader height is
46px on all five pages at both viewports. FilterBar height is 83px on all
four pages that have one (single-row wrapping at both viewports for these
field counts — no awkward multi-row collapse).

## CONTROL HEIGHT

Input/select height inside every `.ui-filter-bar`: **36px** on Employees,
Equipment, and Users, at both viewports — identical to Production Orders,
no documented exception needed for this batch.

## OVERFLOW

**0px horizontal overflow** on all four pages at both viewports (measured
via `document.documentElement.scrollWidth - clientWidth`), and confirmed
again via the full 16-page × 2-viewport Playwright audit (32/32 captures,
0 overflowing).

## PAGE ERRORS / CONSOLE ERRORS

**0** across all four pages, both viewports, and across the targeted
functional smoke checks below (`page.on('console')`/`page.on('pageerror')`
listeners active throughout).

## FUNCTIONAL SMOKE (consolidated)

| Check | Result |
|---|---|
| Employees: search filters table | PASS (`52/52` → `0/52` → `52/52`) |
| Employees: edit modal opens/closes | PASS |
| Equipment: filter interaction + reload | PASS |
| Users: search filters account list | PASS (no permission changes made) |
| Working Calendar: editor opens/closes | PASS |
| Full 16-page × 2-viewport audit | 32/32, 0 overflow, 0 errors |
| 12-check general smoke pass | 12/12 |

## TESTS

| Check | Result |
|---|---|
| `node --check app.js` | OK |
| CSS brace balance | balanced |
| `git diff --check` | clean |
| `tests/test_v71_ui_foundation.py`, `tests/test_web_ui.py` | 7 passed, 0 failed |

## LOCAL BUILD

```
build-release.sh --bump
IMAGE RELEASE PASS
Version: 71.0.0.18
Digest: sha256:a28ad25b2a3aedb959eaf5dc0eed4f83bc5fb95b459117dc6fd9203886674d25
Schema: 0037_v72_audit_operations_separation
```
(71.0.0.9 through .17 were already frozen releases from earlier this session.)

## LOCAL DEPLOY

Deployed via Deploy Agent's official `/api/release-manager/deploy-local`.
Job progression: `deploying` → `"CUTOVER: stopping application only;
gateway and PostgreSQL remain running"` → `verifying` → `success —
"Deployment verified: 71.0.0.18"`.

## LOCAL HEALTH

```json
{"status":"healthy","version":"71.0.0.18","schema_version":"72.0.0.0",
 "database_backend":"postgresql","postgres_version":"17.10"}
```
`mesflow-postgres` uptime unaffected (27h, never restarted).

## Files changed

- `app/mesflow/web/static/app.js` — `renderEmployees`, `renderEquipment`,
  `renderUsers`, `renderWorkingCalendar` rebuilt on `.page-shell`/
  `.page-header`/`MFUI.filterBar()`/`.content-panel`. No change to any
  `load*`/`draw*` data-fetching or filtering logic, or to any modal/edit
  flow — only the top-level container markup these functions render into.
- `app/mesflow/web/static/ui.css` — removed confirmed-dead
  `.employee-tools`, `.catalog-toolbar`, `.system-user-tools`,
  `.equipment-panel`, `.system-user-panel` layout rules (verified zero
  remaining references in any `.js` file before deletion); trimmed the
  same dead class names out of shared multi-selector rules while keeping
  every still-live class in those same rules (`.qr-toolbar`,
  `.template-old-toolbar`, `.panel-toolbar`, `.toolbar`, `.ui-toolbar`,
  `.ui-filter-bar`) untouched. Result-count styling
  (`.employee-result-count`, `.equipment-result-count`, `.system-user-count`)
  and all table/badge/modal CSS for these four pages kept as-is — none of
  it was page-shell-related.
- `reports/UI_TEMPLATE_MIGRATION_BATCH_A.md` — this report.

## Not migrated in this task

All other pages (Overview, Dashboard, Templates, Session Management,
Session Exception Center, Production Trace, Business Audit, Production
Schedule, Kiosk Management, System Logs, QR Print) — unchanged, per the
explicit stop condition. Session Management and Session Exception Center
were already migrated in the prior Golden Foundation task.

**PRODUCTION TEST TOUCHED: NO**
**PRODUCTION TOUCHED: NO**
