# MESFlow UI Quality Audit — TEST (mesflow.net, v71.0.0.253) — 2026-09-09

Independent QA/UI reviewer pass against the real deployed TEST instance. **Audit
only — BUSINESS LOGIC CHANGED: NO, nothing deployed.** Severity uses this
skill's taxonomy (P0 Broken / P1 UX / P2 Consistency / P3 Polish).

Method: 101 live Playwright screenshots + per-element DOM measurement + axe
(WCAG2A/AA) + keyboard tab-order, `https://mesflow.net` as `admin`, 4 viewports
(1920/1366/768/390). Evidence: `scratchpad/ui-audit/evidence/`. Full narrative
companion: `reports/UI_AUDIT_MESFLOW_NET_20260909.md`.

```
PAGES AUDITED: 24 authenticated SPA routes + 2 public kiosk pages (login,
  overview, dashboard A/B/C, production-orders, templates, session-management,
  session-exceptions, rework-queue, production-trace, business-audit,
  production-schedule, kiosk-management, employee-productivity, system-logs,
  employees, qr-print, equipment, users, working-calendar, tutorials, parts,
  operations, esp-ota, /kiosk, /kiosk/employee-productivity)
NOT AUDITED (needs interactive 2nd pass): all modals/drawers, PO/Part/Operation
  detail drill-ins, OP SETUP section, /print/setup/<id>, kiosk state screens
  past "ready". These are click/modal-only; the URL sweep can't reach them.
SHARED COMPONENTS AUDITED: app shell + sidebar (app.html), MFUI primitives
  (core/ui.js: filterBar, statusBadge, content-panel, drawer/modal), the
  `.cards` KPI-strip class, `--text-secondary` token, global checkbox style,
  dashboard-tabs / ec-tabs / sl-tabs.

P0 (Broken):
- system-logs.js:11,13,34,36 — the KPI strip `<div class="cards">` (5 stat
  cards on the Action-Log tab, 4 on Error-Trace) overflows the viewport by
  6,000–7,600px at ALL FOUR viewports. First card ("Request 24h") stretches to
  fill the full width; "Lỗi 24h"/"Chậm 24h"/… are pushed off the right edge and
  clipped (body does not scroll → unreachable). Visibly broken on desktop-1920.
  Root cause is the shared `.cards` class not constraining to a grid — SYSTEMIC.
- app.js:128 — `if(id==='esp-ota')return renderEspOta()` dispatches to a
  function defined NOWHERE → `ReferenceError: renderEspOta is not defined`;
  `#content` renders blank and the shell shows the wrong fallback title
  "Dashboard". Unlinked route (URL-only), but a real broken screen + the sweep's
  ONLY JS error. (`esp-ota-*.png`)

P1 (UX):
- Template editor: 104 per-Operation `<select>` with no accessible name +
  26 unlabeled `<input>` (axe critical: select-name n=104, label n=26). The
  dropdowns that pick equipment / unit / source-OP on each Operation row are
  unusable to keyboard/screen-reader users. Contrast this with the CORRECT
  pattern the codebase already uses elsewhere — `MFUI.filterBar` wraps every
  control as `<label><span>…</span><select>…` (system-logs.js:11) — the template
  editor rows just don't follow it. (`templates-desktop-1366.png`)
- Template editor is unusable-responsive at 390px: 182 form controls clipped by
  an `overflow:hidden` ancestor because the 2-column editor grid never reflows.
  (`templates-mobile-390.png`)
- overview: aria-prohibited-attr n=188 (axe serious) on the repair-plan rows,
  plus an empty orphan grey KPI cell (bottom-right of the KPI block) at every
  viewport — the "oversized empty region" composition anti-pattern.
  (`overview-desktop-1366.png`)

P2 (Consistency):
- Colour-contrast below WCAG AA on ALL 20 content pages, 185 nodes, ONE root
  cause: the `--text-secondary` muted-grey token (used pervasively, e.g.
  ui.css:258,262,263,264,265,297) is too light on the light ground. Worst
  pages: production-schedule (80), dashboard·people (34), users (12). SYSTEMIC —
  one token change fixes ~all.
- Checkboxes render 16×16px (below the 24×24 touch-target minimum): 27 on
  templates, 26 on qr-print, scattered elsewhere. SYSTEMIC (global checkbox
  style).
- production-schedule + tutorials: scrollable-region-focusable (axe serious) —
  the horizontally-scrollable Gantt / tutorial region isn't keyboard-reachable
  (needs tabindex=0 + role/aria-label).

P3 (Polish):
- employee-productivity @390: wallboard action row overflows +38px.
  (`employee-productivity-mobile-390.png`)
- business-audit @390: filter chips overflow +10px.
- overview @390: 6 repair-plan PO buttons clipped by `panel repair-plan`.

SHARED FIXES (systemic — fix once, not per page):
- `.cards` KPI-strip class → constrain to a grid (e.g.
  `grid-template-columns:repeat(auto-fit,minmax(160px,1fr))`), fixes P0 #1.
- `--text-secondary` token → darken to reach 4.5:1, fixes ~185 contrast nodes.
- global checkbox rule → min 24×24 hit area, fixes the P2 touch-target set.

PAGE-SPECIFIC FIXES:
- app.js:128 → define `renderEspOta()` or drop the dispatch + add an error
  boundary so unknown `?page=` shows a message, not a silent blank + wrong title.
- template editor operation-row markup → wrap each `<select>`/`<input>` in the
  existing `<label><span>` MFUI pattern; let the editor grid go 1-column <640px.
- overview repair-plan rows → remove prohibited aria attrs; fill/collapse the
  empty KPI cell.
- production-schedule/tutorials scroll regions → tabindex=0 + aria-label.

ALIGNMENT: Good across the board. Skip-nav link ("Bỏ qua điều hướng") is the
  first focusable element; tab order is logical (nav → content). No misaligned
  toolbars found in the swept pages.
SPACING: Consistent; pages use the `--ui-space-*` scale. Only anomaly is the
  overview empty KPI cell (P1) and the templates mobile grid (P1).
TYPOGRAPHY: Consistent title/section/metadata hierarchy. No stray sizes found.
BUTTONS: Consistent height/variant. Primary actions clearly distinguished.
FORMS: The one real defect — template editor controls have no labels (P1) and
  clip on mobile (P1). Filter bars elsewhere use the correct labelled pattern.
TABLES: Overflow correctly contained in `.table-wrap` scroll regions on the
  list pages; no page-level table overflow. system-logs' problem is the KPI
  strip above the table, not the table.
CARDS: Consistent border/radius. Exception: system-logs `.cards` KPI strip
  loses its width (P0); overview has one empty card cell (P1).
TABS: dashboard (3), session-exceptions (5), system-logs (3), tutorials
  (nested), production-trace (8) — all stable, no wrap, no layout shift on
  select. Active state consistent.
DRAWERS/MODALS: NOT AUDITED (interactive-only) — flagged as a coverage gap.
RESPONSIVE: 22/24 pages reflow cleanly (sidebar→hamburger, KPI grids re-column,
  filters stack). No body horizontal scroll at any viewport. The two exceptions
  are the template editor (P1) and the minor P3 mobile overflows.

1920x1080: clean on 23/24; system-logs KPI overflow visible.
1366x768: clean on 23/24; system-logs KPI overflow visible.
  (768 tablet + 390 mobile also swept — see responsive section.)

PAGE ERRORS: 1 — esp-ota `ReferenceError: renderEspOta is not defined`. All
  other 100 loads clean.
CONSOLE ERRORS: 1 (the same esp-ota ReferenceError, seen at all 4 viewports).
OVERFLOW: system-logs `.cards` at all viewports (P0); template editor mobile
  (P1); 2 minor mobile cases (P3). NO page-wide body horizontal scroll anywhere.

BUSINESS LOGIC CHANGED: NO
```

## Go / No-Go

**GO for continued TEST use and a controlled release, with two must-fix items
before a broad or accessibility-sensitive audience:** the P0 `system-logs` KPI
overflow (one visibly-broken admin page, one shared `.cards` rule) and the P1
template-editor unlabeled controls (blocks keyboard/screen-reader use of a core
authoring screen). Everything else is scheduled debt, not a blocker. The
unaudited modal/detail/OP-SETUP surfaces are a stated coverage gap — a Go here
covers the 26 surfaces actually tested.

## Notes for the record
- The brief's two specific worries are SATISFIED: REWORK ("Chờ sửa") is a
  distinct KPI from NG and Phế (NG shown red) on overview/dashboard/rework-queue;
  Templates master-detail auto-selects the first item (never opens blank).
  production-trace / kiosk-management show empty-state prompts, not blank panes.
- Three shared fixes (`.cards`, `--text-secondary`, checkbox size) are each a
  single safe CSS change with wide payoff — available to batch on a branch on
  request. Per Build Once, a CSS edit here is not live until committed →
  version-bumped → `scripts/build-release.sh` → Deploy Local; none of that done.
