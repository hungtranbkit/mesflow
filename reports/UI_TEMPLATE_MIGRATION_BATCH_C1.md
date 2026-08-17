# UI Template Migration — Batch C1

VERSION BEFORE: 71.0.0.19
VERSION AFTER: 71.0.0.20

Migrates Business Audit, System Logs, QR Print, and Production Schedule onto
the same outer visual contract as the Golden Foundation (71.0.0.17) / Batch A
(71.0.0.18) / Batch B (71.0.0.19), reusing the approved shared primitives
exactly as-is — no new competing page shell, header, filter bar, or panel
was introduced: `.page-shell`, `.page-header`, `MFUI.filterBar()`,
`.content-panel`/`.content-panel-head`/`.content-panel-body`. Each page's
specialized interior (audit cards, log tables with monospace JSON detail,
QR catalogue/print sheet, Gantt/Material Flow) is untouched in logic/data —
only the outer wrapper, header, and filter/toolbar row were normalized.

Templates was explicitly NOT migrated in this task, per instruction.

---

## BUSINESS AUDIT (AUDIT archetype)

**BEFORE**: `<section class="panel"><div class="panel-head">…</div><div class="ba-categories">`
category chips`</div><div class="toolbar ba-toolbar" style="…">` inline-styled
flex row of bare date/actor inputs + `<details class="ba-advanced">` +
"Lọc" button `</div><div id="baList">…</div></section>`

**AFTER**: `.page-shell > .page-header (plain title/description) >
.ba-categories (unchanged category-chip nav) > MFUI.filterBar({content:
Từ ngày/Đến ngày/Người thực hiện labeled fields + <details class="ba-advanced">,
actions: "Lọc"}) > .content-panel (head: "Nhật ký theo bộ lọc" + live
result-count <p>, body: #baList)`.

Standardized per the task's density requirement: header, filters, result
count, and list container are now canonical; `.ba-card` rows themselves
were NOT touched (already compact — 14px/16px padding, 12–14px type) and
detail-action alignment (`.ba-card-actions`) is unchanged. Added a live
result-count line (`#baCount`, "N bản ghi phù hợp") in the content-panel
head, updated on every `load()`.

## SYSTEM LOGS (AUDIT archetype)

**BEFORE**: `<div class="panel system-log-tabs"><div class="toolbar wrap">`
3 tab buttons`</div></div><div id="slView">` — each tab (`loadActions`/
`loadErrors`/`loadRetention`) redrew its own `<div class="panel"><div
class="toolbar wrap">`bare filter controls`</div></div><div id="…Stats"
class="cards"></div><div class="panel"><div id="…Rows">…</div></div>`.

**AFTER**: `.page-shell > .page-header (distinct in-content title "Theo dõi
vận hành hệ thống", separate from the Topbar's "Nhật ký ứng dụng") >
.system-log-tabs (tab nav, unchanged) > #slView`, where each tab now draws
`MFUI.filterBar({…}) > #…Stats.cards (unchanged KPI strip) > .content-panel
(head: "Action Log theo bộ lọc" / "Error Trace theo bộ lọc" / "Lịch sử
retention", body: the existing table)`. The log viewer itself — table rows,
inline expand-detail rows (`.sl-inline-detail`/`.sl-inline-box`), monospace
`<pre class="json">` request/response/traceback blocks — was not touched;
`.content-panel-body:has(>.table-wrap){padding:0}` (already-existing shared
rule) makes the table sit flush inside the new panel exactly as it did
inside the old bare `<div class="panel">`.

Added a small new shared utility, `.ui-filter-check` (single-line inline
checkbox+label matching the FilterBar's 36px control baseline instead of
the standard stacked label/control grid) — needed for "Chỉ lỗi", not a
new toolbar/filter component.

## QR PRINT (UTILITY archetype)

**BEFORE**: `<section class="panel qr-print-center"><div class="panel-head">`
title + `<div class="panel-actions">`Chọn tất cả/Bỏ chọn/In tem`</div></div>
<div class="qr-toolbar">` 4 filter fields + "Làm mới" `</div><div
class="qr-selection-summary">…</div><div id="qrList">…</div></section>
<div class="qr-print-sheet" id="qrPrintSheet"></div>`.

**AFTER**: `.page-shell > .page-header (title/description +
.page-header-actions: Chọn tất cả/Bỏ chọn/In tem) > MFUI.filterBar({…4
fields…, actions:"Làm mới"}) > .qr-selection-summary (unchanged) >
.content-panel (body: #qrList) </div><div class="qr-print-sheet"
id="qrPrintSheet"></div>` — the print sheet stays a direct sibling of
`.page-shell` (not nested inside it), exactly matching its original DOM
position, since the print stylesheet's `body *{visibility:hidden!important}`
+ `.qr-print-sheet{position:absolute;inset:0}` technique depends on it
being addressable independent of normal document flow. Configuration
(loại QR/PO/tìm nhanh/kích thước, select-all/clear/print actions) is now
visually separated from the preview/output (QR card grid) by the canonical
page-header/filter-bar/content-panel boundaries.

## PRODUCTION SCHEDULE (MONITOR/PLANNING archetype — highest risk)

**BEFORE**: `<section class="panel schedule-control-panel" id="schedulePanel">
<div class="schedule-sticky-toolbar" id="scheduleStickyToolbar"><div
class="panel-head"><div><h2>Gantt + Material Flow</h2>…</div><div
class="schedule-actions"><label>Production Order</label><select
id="schedulePoFilter">…</select><button id="scheduleReload">…</button>
</div></div><div class="schedule-legend">…</div></div><div
id="scheduleBody">…</div></section>` — no outer `.page-shell`/`.page-header`
at all; the in-content title lived inside the sticky toolbar itself.

**AFTER**: `.page-shell > .page-header (distinct title "Gantt + Material
Flow", separate from the Topbar's "Tiến trình sản xuất") > .panel
.schedule-control-panel#schedulePanel` (kept as the SAME specialized
wrapper class it always was — `.panel` and `.content-panel` share
identical border/radius/background/shadow tokens, confirmed by measurement
in Batch B, so the outer box geometry is canonical either way) `>
.schedule-sticky-toolbar#scheduleStickyToolbar (still position:sticky,
top:var(--schedule-workspace-offset), unchanged) > MFUI.filterBar({content:
PO select, actions:"↻ Cập nhật"}) + .schedule-legend (unchanged) >
#scheduleBody (Gantt rows + Material Flow section, completely untouched)`.

Only the toolbar's own controls were normalized (PO `<select>` + reload
`<button>` now render through FilterBar, giving them the canonical 36px
control height instead of the old custom 40–42px/9px-padding sizing); the
sticky-positioning mechanics (`--schedule-workspace-offset:72px`,
`--schedule-toolbar-height` set live by a `ResizeObserver`, the
`schedule-po-head`'s own second-level sticky position under the toolbar)
were left completely untouched, since that is schedule-specific planning
UX explicitly protected by the task ("preserve schedule/Gantt/calendar
geometry and logic… normalize only… date/filter toolbar"). Verified live
via `getBoundingClientRect()` after scrolling the page 600px: the sticky
toolbar's `top` was exactly `72px` — i.e. still pinned flush under the
72px Topbar, unchanged from before the migration.

---

## SPECIALIZED UI PRESERVED

- **Business Audit**: category-chip navigation (`.ba-categories`/`.ba-chip`),
  `.ba-card` audit-entry rows (summary, context, changes-preview,
  extra/reason/affected-sessions lines, session/detail action buttons),
  the detail drawer opened via `openAuditDrawer()`/`SessionDetailDrawer`.
- **System Logs**: 3-tab structure (Hoạt động hệ thống / Lỗi cần xử lý /
  Lịch sử lưu trữ), KPI stat strips (`systemLogStatCard()`), inline
  expand-detail rows with monospace request/response/traceback `<pre
  class="json">` blocks, error-resolve workflow (`.et-inline-*`).
  Table/log presentation was intentionally NOT converted to a generic
  DataTable style — it is the same table markup as before, just re-homed
  inside a `.content-panel-body`.
- **QR Print**: QR catalogue grid/selection state, print-sheet generation
  (`qrPrintSheet` innerHTML build + `window.print()`), the `@media print`
  stylesheet (`.qr-print-sheet`/`.qr-print-label` sizing per label format)
  — completely unchanged.
- **Production Schedule**: two-level sticky hierarchy (workspace header →
  sticky filter toolbar → sticky per-PO head), Gantt bar rendering/timeline
  ticks/dependency labels, Material Flow cards/meters, `openProductionOrder()`
  drill-down — all untouched.

## LEGACY CSS REMOVED

- **Business Audit**: `.ba-toolbar{flex-wrap:wrap}` (dead, its container
  removed). Retargeted (not deleted) `.ba-toolbar details.ba-advanced` →
  `.ba-advanced` and its two descendant rules, since `.ba-advanced` itself
  is still live inside the new FilterBar content and needed its
  border/background/padding preserved without the now-nonexistent
  `.ba-toolbar` ancestor.
- **System Logs**: `body[data-page="system-logs"] #slView>.panel{margin:0}`
  and all `#slView .toolbar.wrap` rules (desktop + 900px media, 2
  occurrences) — dead, since every subview toolbar is now `.ui-filter-bar`.
  Kept `#slView>.cards{…}` (still a direct child) and the `system-log-tabs`
  tab-bar rules (still live, different toolbar).
- **QR Print**: `.qr-toolbar` fully removed everywhere it appeared —
  2 standalone rule blocks, sub-rules inside 3 catalog/media blocks, and
  its 6 appearances as one token inside shared toolbar-selector lists
  (`.toolbar,.qr-toolbar,.template-old-toolbar,.panel-toolbar{…}` etc.,
  including both copies of the control-height-unification rule) — every
  removal individually verified so the other listed classes (`.toolbar`,
  `.template-old-toolbar`, `.panel-toolbar`, `.ui-toolbar`, `.ui-filter-bar`)
  kept their shared styling intact. `.qr-print-center` (both its
  `.panel-head` and `.panel-actions` scoped mobile rules) removed —
  fully dead, class no longer used.
- **Production Schedule**: `.schedule-actions` removed everywhere (2
  standalone declarations, 2 sub-rules in the 900px media query, 2
  sub-rules in one 520px media query, and one entirely-standalone dead
  520px media block) — confirmed 0 references left in any page/JS file.
  `.schedule-sticky-toolbar .panel-head{margin-bottom:8px}` retargeted to
  `.schedule-sticky-toolbar .ui-filter-bar{margin-bottom:8px}` (equivalent
  spacing for the new FilterBar occupying the same slot); its mobile
  (520px) `.panel-head` sub-rules were dropped outright since the shared
  global `.ui-filter-bar` responsive rule (`@media(max-width:900px)`,
  wider breakpoint, already stacks it) supersedes them.

## LIVE SPECIALIZED CSS PRESERVED

`.ba-card`/`.ba-card-head`/`.ba-action-badge`/`.ba-changes-preview`/
`.ba-extra`/`.ba-reason`/`.ba-affected` (Business Audit rows); `.cards`/
`.card` KPI strip, `.sl-inline-detail`/`.sl-inline-box`/`.sl-detail-grid`/
`.json`/`.trace` monospace panes, `.system-log-tabs`/`.sl-tab` tab bar
(System Logs); `.qr-catalog-grid`/`.qr-catalog-card`/`.qr-preview-box`/
`.qr-print-sheet`/`.qr-print-label` and its full `@media print` block,
`.qr-selection-summary`, `.qr-search-field` (QR Print); `.schedule-legend`/
`.gantt-*`/`.material-flow-*`/`.flow-*`/`.schedule-po*` and all sticky
positioning variables (`--schedule-workspace-offset`,
`--schedule-toolbar-height`) (Production Schedule) — none of these were
modified.

---

## EDGE ALIGNMENT

`.page-shell` left/right edges measured against Golden Production Orders
at both viewports, all four Batch C1 pages:

| Page | 1920×1080 (L / R) | 1366×768 (L / R) | Diff vs Golden |
|---|---|---|---|
| Business Audit | 272 / 1896 | 248 / 1346 | 0px |
| System Logs | 272 / 1896 | 248 / 1346 | 0px |
| QR Print | 272 / 1896 | 248 / 1346 | 0px |
| Production Schedule | 272 / 1896 | 248 / 1346 | 0px |

## CONTROL HEIGHTS

FilterBar controls (input/select/button) measured at 36px on all four
pages at both viewports.

## PANEL GEOMETRY

`.content-panel` and `.panel schedule-control-panel` (confirmed identical
outer box geometry — shared `--border-default`/`--radius-panel` tokens)
border/radius/background/shadow match the Golden reference on every page;
no clipped Gantt bars/timeline (the Gantt track's own internal
`overflow:auto` scroll region is unaffected, and the page itself carries
0 horizontal overflow), no broken log tables, no floating/overlapping KPI
cards at either viewport.

## 1920x1080

BEFORE/AFTER screenshots captured and visually inspected for all 4 pages.
Business Audit reads compact (chips → filter row → count → card list, no
oversized rows). System Logs' log viewer/table is clearly separated under
its own titled content-panel, distinct from the tab bar and KPI strip
above it. QR Print's configuration (title + select-all/clear/print +
filter row) sits visibly above and separate from the preview/output card
grid. Production Schedule's Gantt/Material Flow content is unchanged in
density/usability — only the toolbar row shrank to 36px controls and
gained a canonical page-header above it.

## 1366x768

Same 4 pages re-inspected: FilterBar fields wrap correctly, KPI cards
reflow, QR catalogue grid reflows to 3 columns, Gantt toolbar/legend wrap
without clipping, sticky toolbar/PO-head still pin correctly while
scrolling (`scheduleStickyToolbar` measured `top:72px` after a 600px
scroll, both before deploy — preview container — and after — real
71.0.0.20 deploy). 0 horizontal overflow on every page.

## CSS VALIDATION

Brace balance: 2913 `{` / 2913 `}` (matched), paren balance 1281/1281
(matched); custom string/comment-aware depth scanner: final nesting depth
0 (balanced); `git diff --check`: clean, no whitespace errors.

## JS CHECK

`node --check` on all touched files — `app.js`, `pages/qr-print.js`,
`pages/system-logs.js` — all OK.

## PYTEST

`pytest tests/test_v71_ui_foundation.py tests/test_web_ui.py` → 7 passed
(run twice: once against the live-preview container, once against the
real deployed 71.0.0.20 build).

## FULL UI AUDIT

Full 16-page × 2-viewport Playwright audit (32 captures), run twice
(preview container + real 71.0.0.20 deploy): 32/32 clean both times — 0
overflowing, 0 with console/request errors. General 12-check functional
regression suite (login, PO nav/back, session filters, exception
tabs/drawer, template tools toggle, 0 console errors, 0 failed requests):
12/12 pass both times.

## FUNCTIONAL SMOKE

16 targeted Batch C1 checks (4 pages × up to 4 checks each, run against
both the preview container and the real deployed build — 16/16 pass both
times):

- **Business Audit**: category chips present and switch correctly; detail
  row opens the audit drawer (`.ui-drawer`); actor+date filter narrows the
  live result count (`#baCount`).
- **System Logs**: outcome filter present; "Làm mới" refresh click works;
  tab switch to Lỗi cần xử lý and Lịch sử lưu trữ each render their own
  content; Action Log table renders inside its content-panel.
- **QR Print**: catalogue renders; checking one item updates
  `#qrSummary` ("Đã chọn 1 tem"); print wiring verified non-destructively
  — `window.print` stubbed before clicking "In tem đã chọn", confirmed the
  stub was called AND `#qrPrintSheet` was populated with
  `.qr-print-label` markup AND its `aria-hidden` flipped to `"false"`,
  without ever invoking a real print dialog.
- **Production Schedule**: PO filter present and changeable; "↻ Cập nhật"
  reload click works; sticky toolbar stays pinned at `top:72px` after
  scrolling 600px down the page.

## LOCAL BUILD

`scripts/build-release.sh --bump` → `IMAGE RELEASE PASS`, version
71.0.0.20, schema `0037_v72_audit_operations_separation`, package
`artifacts/releases/71.0.0.20/MESFlow_71.0.0.20.deploy.zip`.

## LOCAL DEPLOY

Deploy Agent `POST /agent/api/release-manager/deploy-local
{"version":"71.0.0.20"}` → job `success`. Steps: backup → stage → install
→ restart ("MES Docker stack started; PostgreSQL data preserved") →
health ("Version 71.0.0.20 and health verified") → rollback skipped (not
required). `from_version: 71.0.0.19`. (The Deploy Agent admin session had
expired since Batch B; its password was reset via the established
werkzeug/`agent.json` recovery flow, with your explicit approval, before
this deploy could authenticate.)

## LOCAL HEALTH

`GET /api/system/health` → `{"ok": true, "status": "healthy", "version":
"71.0.0.20", "postgres_version": "17.10", "schema_version": "72.0.0.0"}`.

POSTGRES RESTARTED: NO
PRODUCTION TEST TOUCHED: NO
PRODUCTION TOUCHED: NO
