# UI Template Migration — Batch B (MONITOR pages)

VERSION BEFORE: 71.0.0.18
VERSION AFTER: 71.0.0.19

Migrates Overview, Dashboard, Production Trace, and Kiosk Management onto
the same outer visual contract as the Golden Foundation (71.0.0.17) and
Batch A (71.0.0.18), reusing the approved shared primitives exactly as-is
— no new competing page shell, header, filter bar, or panel was
introduced:

- `.page-shell` / `.page-header` (plain, title + description, actions
  where the page has them)
- `MFUI.filterBar()` for Overview, Dashboard, and Production Trace
  (Kiosk Management also uses it for its search/status row)
- `.content-panel` / `.content-panel-head` / `.content-panel-body` for
  each page's static-header data regions
- existing KPI/stat rows (`#ovKpis`, `.daily-kpis`) kept as-is — already
  correctly positioned, satisfying "StatsRow optional" without forcing
  Production Order's plain-text variant onto monitor content
- monitor-specific visualization (repair plan, operation progress bars,
  session timeline, shift feed, production-trace timeline/tabs, kiosk
  device cards) is completely untouched in logic/data — only its outer
  wrapper was normalized

Per the task's explicit "do not force list-page structure onto monitor
pages" instruction, two dynamically-redrawn regions (`#ovRepairPlan`,
`#kmDetail`) were deliberately kept as plain `.panel` rather than
converted to `.content-panel` — their entire content, including an
ad-hoc header, is written by page JS on every redraw via a single
`innerHTML=` call. Measurement confirmed `.panel` and `.content-panel`
share identical outer box geometry (border/radius/background/edges), so
the visual contract holds either way, while avoiding a rewrite of
page-specific render logic that the task explicitly prohibits touching.

---

## OVERVIEW

**BEFORE STRUCTURE**
```
<section class="panel overview-command">
  <div class="overview-intro"><h2>Đang sản xuất</h2><p>…</p></div>
  <div class="overview-filters">…6 filter fields + primary reload button…</div>
</section>
<section class="overview-summary" id="ovKpis"></section>
<section class="panel repair-plan" id="ovRepairPlan"></section>
<section id="ovPos" class="overview-po-list">…</section>
```
Bespoke side-by-side "hero" grid (title left, filters right) with its own
`.overview-command`/`.overview-filters`/`.overview-reload` styling,
independent of the Golden shell/header/filterBar contract.

**AFTER STRUCTURE**
```
<div class="page-shell">
  <div class="page-header"><div><h2>Đang sản xuất</h2><p>…</p></div></div>
  {MFUI.filterBar(...)}  <!-- search, PO, hàng sửa, tình trạng, sắp xếp + "Làm mới" -->
  <section class="overview-summary" id="ovKpis"></section>
  <section class="panel repair-plan" id="ovRepairPlan"></section>
  <section id="ovPos" class="overview-po-list">…</section>
</div>
```
Title/description now stacked plainly above a canonical bordered filter
row, matching the Golden pages. `#ovKpis`, `#ovRepairPlan`, `#ovPos` kept
unchanged in class/ID/JS.

**LEGACY CSS REMOVED**: `.overview-command`, `.overview-intro` (bare and
`.overview-command`-scoped forms), `.overview-filters` (+ label/input/
select rules), `.overview-search`, `.overview-reload`,
`.overview-reload-icon`, `.overview-live`, `.overview-hero` (+ its
`.pc-actions`-scoped rules), `.overview-sections`, `.overview-orders`,
`.overview-operations` (its `.pc-op-table`/`.pc-op-row`-scoped rules),
and every dead media-query fragment referencing those selectors (five
`@media` blocks partially or fully pruned), plus the two now-dead entries
(`.overview-filters .btn,…` / `.overview-hero .pc-actions .btn,…`) in the
shared toolbar-control-height unification rule (both the desktop and
`@media(max-width:520px)` copies).

**MONITOR-SPECIFIC ELEMENTS PRESERVED**: summary/KPI cards (`.pc-kpi`,
`.pc-kpis`, `.pc-state`, `.pc-priority`), repair-plan panel and its table,
PO progress cards, operation rows, all `drawSummary()`/`drawPlan()`/
`drawPos()` JS untouched. `.pc-kpi`/`.pc-kpis` bare rules and their
responsive tweaks kept exactly (confirmed still live — shared with
`pages/po-control.js`).

**FUNCTIONAL SMOKE**: quick-nav "Làm mới" button present and clickable —
PASS.

---

## DASHBOARD

**BEFORE STRUCTURE**
```
<section class="daily-command panel">
  <div class="daily-command-copy"><h2>Báo cáo ca sản xuất</h2><p>…</p></div>
  <div class="daily-command-actions">…date picker, shift picker, "Danh sách Operation", "Làm mới dữ liệu"…</div>
</section>
<section class="daily-kpis" id="dailyKpis"></section>
<section class="panel op-time-panel daily-section">…</section>
<section class="panel session-timeline-panel daily-section">…</section>
<section class="panel daily-feed-panel daily-section">…</section>
<section class="panel daily-section">…</section>
```

**AFTER STRUCTURE**
```
<div class="page-shell">
  <div class="page-header"><div><h2>Báo cáo ca sản xuất</h2><p>…</p></div></div>
  {MFUI.filterBar({content: date+shift picker, actions: "Danh sách Operation" + "Làm mới dữ liệu"})}
  <section class="daily-kpis" id="dailyKpis"></section>
  <section class="content-panel op-time-panel daily-section">…</section>
  <section class="content-panel session-timeline-panel daily-section">…</section>
  <section class="content-panel daily-feed-panel daily-section">…</section>
  <section class="content-panel daily-section">…</section>
</div>
```
All four `.panel.daily-section` blocks converted to
`.content-panel`/`.content-panel-head`(h3)/`.content-panel-body`; chart
IDs (`#opTimeProgress`, `#sessionTimeline`, `#dailyFeed`,
`#dailyAttention`) and all chart-rendering JS untouched.

**LEGACY CSS REMOVED**: `.daily-command`, `.daily-command-copy`,
`.daily-command-actions` — all three definition layers found in the file
(an older `display:flex` layer, a `display:grid` layer with gold-styled
shift picker, and the final active `display:grid` layer with the current
teal styling), plus every scoped/dead selector inside their surrounding
media queries (`max-width:1100px`, `max-width:650px`, `max-width:760px`,
`max-width:1450px`, `max-width:900px`). Bare, still-live sibling
selectors in the same rules (`.daily-date-picker`, `.shift-picker*`,
`.daily-kpis`, `.daily-kpi`, `.daily-list-button`, `.daily-refresh`,
`.daily-section`, `.employee-timeline-actions`) were preserved verbatim.

**LIVE CSS PRESERVED (explicit)**: `.daily-date-picker`, `.shift-picker`
and all its state/night/current variants, `.daily-kpis`/`.daily-kpi`
(bare, both legacy and current cascade layers), `.daily-section`,
`.daily-live`, `.employee-timeline-actions`, `.control-clear-state` — all
chart/timeline-specific rules for `#opTimeProgress`/`#sessionTimeline`/
`#dailyFeed`/`#dailyAttention` untouched (not scoped to any dead class).

**MONITOR-SPECIFIC ELEMENTS PRESERVED**: KPI cards, operation-progress
bars, employee session timeline + sort control, shift feed, "Operation
cần chú ý" list — no chart logic or data changed.

**Bug fixed during this migration**: the shift-picker markup passed to
`MFUI.filterBar({content:'…'})` contained a nested
`${currentCtx.active?'is-current':''}` ternary; using single quotes for
the outer `content` string broke on the inner `'is-current'` literal
(`node --check` → `SyntaxError: Unexpected identifier 'is'`). Fixed by
converting that `content:` argument to a backtick template literal.

**FUNCTIONAL SMOKE**: shift filter present, "Làm mới dữ liệu" present and
clickable (triggers a data refresh) — PASS.

---

## PRODUCTION TRACE

**BEFORE STRUCTURE**
```
<div class="trace-toolbar panel"><label>Production Order<select id="ptPo">…</select></label><button id="ptReload">Làm mới</button></div>
<section id="ptSummary" class="trace-summary">…</section>
<nav class="trace-filters">…8 category tabs…</nav>
<main id="ptTimeline" class="production-trace"></main>
<button id="ptMore" hidden>Tải thêm sự kiện</button>
```
No in-content page-header at all — only the Topbar title "Production
Trace".

**AFTER STRUCTURE**
```
<div class="page-shell">
  <div class="page-header"><div><h2>Dòng thời gian sản xuất</h2><p>…</p></div></div>
  {MFUI.filterBar({content: PO select, actions: "Làm mới"})}
  <section id="ptSummary" class="trace-summary">…</section>
  <nav class="trace-filters">…8 category tabs, unchanged…</nav>
  <section class="content-panel"><div class="content-panel-body">
    <main id="ptTimeline" class="production-trace"></main>
    <button id="ptMore" hidden>Tải thêm sự kiện</button>
  </div></section>
</div>
```
A distinct in-content title ("Dòng thời gian sản xuất") was added,
deliberately different from the Topbar's "Production Trace" — following
the same convention already used for Production Orders and Session
Management, and avoiding the "duplicate title" defect from the very
first (rejected) Golden Foundation attempt. `#ptTimeline`/`#ptMore`
wrapped in `.content-panel` with no static head, to avoid redundancy with
the tabs immediately above.

**LEGACY CSS REMOVED**: `.trace-toolbar` (bare + `label` rule) and its
`max-width:900px` media-query fragment; `.trace-summary`/`.trace-current`
rules in that same media query preserved unchanged.

**MONITOR-SPECIFIC ELEMENTS PRESERVED**: `.trace-summary`,
`.trace-filters`/`.pt-filter`, `.production-trace`, `.trace-day`,
`.trace-event*`, `.trace-diff`, `.trace-qty`, `.trace-mini` — all
timeline-visualization CSS and drill-down/detail JS untouched.

**FUNCTIONAL SMOKE**: 8 category tabs present, tab switch toggles
`.active` correctly, PO filter select present — PASS.

---

## KIOSK MANAGEMENT

**BEFORE STRUCTURE**
```
<div class="panel">
  <div class="panel-head"><div><h2>Thiết bị kiosk</h2><p>…</p></div><button id="kmReload">Làm mới</button></div>
  <div id="kmSummary" class="daily-kpis"></div>
  <div class="toolbar"><input id="kmSearch">…<select id="kmState">…</select></div>
  <div id="kmList">Đang tải...</div>
</div>
<div class="panel" id="kmDetail"><div class="empty">Chọn một kiosk…</div></div>
```

**AFTER STRUCTURE**
```
<div class="page-shell">
  <div class="page-header"><div><h2>Thiết bị kiosk</h2><p>…</p></div><div class="page-header-actions"><button id="kmReload">Làm mới</button></div></div>
  <div id="kmSummary" class="daily-kpis"></div>
  {MFUI.filterBar({content: search + state filter})}
  <section class="content-panel"><div class="content-panel-head"><h3>Kiosk theo bộ lọc</h3></div><div class="content-panel-body" id="kmList">Đang tải...</div></section>
  <div class="panel" id="kmDetail"><div class="empty">Chọn một kiosk…</div></div>
</div>
```
`#kmDetail` deliberately kept as `.panel` (not `.content-panel`) —
`box.innerHTML=…` fully replaces its content on every `show(device)` call
including its own "Action timeline · {device}" header; converting the
wrapper class would leave dynamically-injected content flush against the
border with no padding. Measured identical to `.content-panel`'s outer
box geometry.

**LEGACY CSS REMOVED**: none — Kiosk Management only ever used the
generic, still-shared `.toolbar`/`.panel`/`.panel-head`/`.daily-kpis`
classes, all of which remain live elsewhere (still used inside `#kmDetail`
and by other pages) and were not touched.

**MONITOR-SPECIFIC ELEMENTS PRESERVED**: device summary KPIs, kiosk card
grid (`.kiosk-card`, online/offline/has-error states, firmware/IP/Wi-Fi/
sync metadata), action-timeline detail panel, event-resolve buttons — no
OTA/destructive action was exercised.

**FUNCTIONAL SMOKE**: search filter typed and cleared, kiosk card list
present, clicking a card opens the action-timeline detail panel — PASS.
No destructive OTA action triggered.

---

## EDGE ALIGNMENT

`.page-shell` left/right edges measured against Golden Production
Orders at both viewports, all four Batch B pages:

| Page | 1920×1080 (L / R) | 1366×768 (L / R) | Diff vs Golden |
|---|---|---|---|
| Overview | 272 / 1896 | 248 / 1346 | 0px |
| Dashboard | 272 / 1896 | 248 / 1346 | 0px |
| Production Trace | 272 / 1896 | 248 / 1346 | 0px |
| Kiosk Management | 272 / 1896 | 248 / 1346 | 0px |

All within the ≤2px tolerance — measured exact match (0px) in every case.

## CONTROL HEIGHTS

FilterBar controls (input/select/button) measured at 36px on all four
pages at both viewports — matches the authoritative
`var(--control-height)` unification rule and Golden Production Orders.

## PANEL GEOMETRY

`.content-panel` (and `.panel`, confirmed identical outer box geometry)
border/radius/background/edges match the Golden reference on every page;
no clipped charts, no broken timelines, no wrapped action bars, no
floating/overlapping KPI cards at either viewport.

---

## 1920x1080
32/32 captures (16 pages × 2 viewports, full-app audit) clean; Batch B's
4 pages individually re-verified: 0 overflow, 0 console errors, 0 failed
requests, 0 edge-alignment deviation.

## 1366x768
Same result — 0 overflow, 0 console errors, responsive wrapping intact
(FilterBar fields wrap, KPI cards reflow, kiosk card grid reflows) on all
four pages.

## CSS VALIDATION
- Brace balance: 2950 `{` / 2950 `}` (matched), paren balance 1291/1291
  (matched)
- Custom string/comment-aware depth scanner: final nesting depth 0
  (balanced)
- `git diff --check`: clean, no whitespace errors

## JS CHECKS
`node --check` on all touched files — `app.js`, `pages/overview.js`,
`pages/production-trace.js` — all OK.

## PYTEST
`pytest tests/test_v71_ui_foundation.py tests/test_web_ui.py` → 7 passed.

## LOCAL BUILD
`scripts/build-release.sh --bump` → `IMAGE RELEASE PASS`, version
71.0.0.19, schema `0037_v72_audit_operations_separation`, package
`artifacts/releases/71.0.0.19/MESFlow_71.0.0.19.deploy.zip`.

## LOCAL DEPLOY
Deploy Agent `POST /agent/api/release-manager/deploy-local
{"version":"71.0.0.19"}` → job `success`. Steps: backup → stage →
install → restart ("MES Docker stack started; PostgreSQL data
preserved") → health ("Version 71.0.0.19 and health verified") →
rollback skipped (not required). `from_version: 71.0.0.18`.

## LOCAL HEALTH
`GET /api/system/health` → `{"ok": true, "status": "healthy", "version":
"71.0.0.19", "postgres_version": "17.10", "schema_version":
"72.0.0.0"}`.

## PLAYWRIGHT
Full 16-page × 2-viewport audit (32 captures) against the deployed
71.0.0.19 build: 0 overflowing, 0 with errors. Batch B-specific
verification (screenshots + `getBoundingClientRect()` measurements + 7
functional-smoke checks) re-run against the same deployed build: all
pass. General 12-check regression smoke suite (login, PO nav, session
filters, exception drawer, template tools toggle, 0 console errors, 0
failed requests): 12/12 pass.

## PAGE ERRORS
None across all 32 audit captures or the 8 Batch B-specific captures.

## CONSOLE ERRORS
None across all 32 audit captures or the 8 Batch B-specific captures.

## OVERFLOW
None — 0px horizontal overflow on every Batch B page at both viewports,
and across the full 16-page/32-capture regression sweep.

POSTGRES RESTARTED: NO
PRODUCTION TEST TOUCHED: NO
PRODUCTION TOUCHED: NO
