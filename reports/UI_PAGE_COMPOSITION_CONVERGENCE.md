# MESFlow Page Composition Convergence

VERSION BEFORE: 71.0.0.23
VERSION AFTER: 71.0.0.24

This pass does not declare success on edges/geometry/control-height alone.
Every fix below was verified by actually looking at a real deployed
screenshot and answering the five acceptance questions (floating
single-action row / oversized empty region / orphan KPI card / canonical
tabs / excessive nested panels), plus a `getBoundingClientRect()`-backed
functional check. Screenshots referenced below live in
`reports/screenshots/composition-convergence/` (`current-*` = before this
pass, `mid-*` = live-preview during implementation, `final-*` = real
deployed 71.0.0.24, both viewports).

---

## 1. PRODUCTION ORDER

**BEFORE ISSUE**: Three separate horizontal bands stacked above the
table — an actions-only row (`+ Tạo PO từ Template` / `Nhập Excel` /
`Xuất Excel`, floating right with a wide empty left side), a StatsRow
row, and the FilterBar row. Excessive vertical fragmentation before any
real content.

**STRUCTURAL ROOT CAUSE**: The prior normalization pass (content
hierarchy) correctly dropped the redundant page-title text from
`.page-header`, but left `.page-header` holding *only* the actions div —
a full-width flex row with nothing on the left reads exactly as a
"floating action row." The StatsRow (`#poSummary`) was a fully separate
sibling instead of sharing that row.

**CHANGE**: Moved `#poSummary.stats-row` into `.page-header` as the left
child, actions as the right child — one row: `[stats.......] [+ Tạo PO
từ Template][Nhập Excel][Xuất Excel]`. Added `.page-header>.stats-row,
.page-header>.daily-kpis{flex:1;min-width:0;margin:0}` so the stats/KPI
side takes the remaining width and actions stay pinned right.

**AFTER RESULT**: One combined row, then FilterBar, then "Danh sách
Production Order" ContentPanel + table. See `final-production-orders-
1920x1080.png` / `-1366x768.png`.

**FUNCTIONAL TEST**: create-button wiring (`#addPO`), import/export
(`#importExcel`/`#exportExcel`), search (`#poSearch`), open PO — all
pass (`po-stats-actions-one-row`, `po-create-wiring`, `po-import-export`,
`po-search-works`, `po-open-navigates`).

---

## 2. EXCEPTION CENTER

**BEFORE ISSUE**: Screenshots read as "too many strong horizontal
layers" — Topbar, a full-bleed dark status banner, tabs, filter, list —
and the dark banner visually dominated the page.

**STRUCTURAL ROOT CAUSE**: Investigated with an actual measurement
before touching anything (per this task's own warning not to trust a
scaled-down screenshot's visual impression over real DOM data):
`.ec-command`'s real rendered height is **56px** — a compact strip, not
an oversized hero. Its visual dominance came entirely from full-bleed
navy color contrast against a light page, which is an intentional,
task-sanctioned choice ("It may remain visually stronger than normal
content because this is an exception workflow"). The genuine structural
problem was elsewhere: its tabs (`.ec-tabs button`) used their own
underline styling, textually similar to but not literally the same
component as Production Trace's tabs — a real "same-shape-different-
component" violation of one tab language.

**CHANGE**: Left `.ec-command`'s size/color/padding untouched (already
compact, confirmed by measurement). Retargeted its tab buttons onto the
one canonical navigation-tab component introduced this pass
(`.mf-tabs`/`.mf-tab`, see §J below) instead of page-specific button
styling.

**AFTER RESULT**: Banner remains a compact 56px strip with the exception
counts front-and-right; tabs are now pixel-identical in styling to
Production Trace/System Logs/Guidance's tabs. See `final-session-
exceptions-1920x1080.png` / `-1366x768.png`.

**FUNCTIONAL TEST**: tabs (`ec-tabs-canonical` — 5 `.mf-tab` buttons
found, `ec-tab-switch`), filters+Apply (`ec-filter-apply`), view
exception → drawer opens (`ec-view-exception`) — all pass.

---

## 3. PRODUCTION TRACE

**BEFORE ISSUE**: A huge full-width navy `.trace-summary` block (the
same treatment used for *real* PO data) rendered even when no PO was
selected, containing only a small white "Chọn một Production Order…"
box floating inside vast dark empty space. Below it, a `ContentPanel`
containing only the (supposedly hidden) "Tải thêm sự kiện" button
rendered as an empty white panel with a stray button in it.

**STRUCTURAL ROOT CAUSE (two separate bugs)**: (1) `#ptSummary` was
unconditionally given `class="trace-summary"` in the initial markup —
the same dark styling meant for a *populated* summary was applied to the
placeholder text too. (2) **A real, previously-undiscovered app-wide CSS
bug**: `.btn,button.primary,.primary{display:inline-flex}` (the
canonical button rule) unconditionally overrides the browser's built-in
`[hidden]{display:none}` for any element carrying both a `.btn`-family
class and the `hidden` attribute — author CSS always wins over the User
Agent stylesheet regardless of selector specificity. Verified live:
`#ptMore` had `hasAttribute('hidden') === true` yet
`getComputedStyle(...).display === 'inline-flex'`. This affected `#ptMore`
here and `#seModalSecondary` in `session-exceptions.js` (found by a
full-app grep for `class="btn...hidden` patterns).

**CHANGE**: (1) `#ptSummary` starts with no class (plain `MFUI.emptyState()`
markup); `.trace-summary` is only added by `load()` once real PO data
populates it, and removed again if the user clears the PO selector. The
tab bar (`.trace-filters`) and the timeline `ContentPanel`
(`#ptTimelinePanel`, newly wrapping `#ptTimeline`+`#ptMore`) both start
`hidden` and are only revealed once a PO is actually selected. (2) Added
`.btn[hidden],button.primary[hidden],.primary[hidden]{display:none}`
to `ui.css`, restoring correct `[hidden]` semantics app-wide.

**AFTER RESULT**: No PO selected → one compact `MFUI.emptyState()` box
("Chưa chọn Production Order" / "Chọn một Production Order để xem lịch
sử."), tabs and timeline panel both absent — no oversized dark region,
no stray button. PO selected → the navy summary, canonical tabs, and
timeline panel all appear together, exactly as before functionally. See
`final-production-trace-1920x1080.png` (empty state) — the giant navy
block is gone.

**FUNCTIONAL TEST**: PO selection loads real data
(`trace-po-selection-loads`), tabs are canonical (`trace-tabs-canonical`
— 8 `.mf-tab` buttons), tab switch (`trace-tab-switch`), refresh
(`trace-refresh`), event rendering, and — the regression this bug class
could easily reintroduce — **reverting to "no PO" correctly restores the
compact empty state** (`trace-reverts-to-empty-state`) — all pass.

---

## 4. BUSINESS AUDIT

**BEFORE ISSUE**: Category navigation rendered as a row of fully-rounded
pill buttons (`.ba-chip`) sitting *above* the FilterBar, visually
unrelated to any other tab/filter language in the app.

**STRUCTURAL ROOT CAUSE / CLASSIFICATION**: Determined semantically, not
just visually: clicking a chip does not switch to a different view or
component — it narrows `baState.category` and re-runs the *same* list
query (`load()`), exactly like the date/actor fields next to it. These
are **filter chips**, not navigation tabs (the task's own dichotomy in
§F). Styling them as `.mf-tab` underline tabs would have been the wrong
fix — it would have implied "this switches to a different page," which
is false.

**CHANGE**: Moved `.ba-categories` inside `MFUI.filterBar()`'s `content`
slot (now a real filter-row control, `flex-basis:100%` so the chips
occupy their own line above the date/actor fields within the same
bordered FilterBar box) instead of being a free-floating row above it.
Documented the semantic distinction directly in `ui.css`: *"Filter chips
(audit category), not navigation tabs — they narrow which records the
same list below shows, they don't switch to a different view, so they
deliberately look like chips, not `.mf-tab`."* Left the pill visual
treatment unchanged (chips are explicitly allowed to look different from
tabs, per §J, precisely because they are filters).

**AFTER RESULT**: One canonical FilterBar box containing category chips
+ date/actor fields + advanced-filter disclosure + "Lọc", instead of two
separate rows. "Chi tiết thay đổi"/"Xem Session" already use `.btn.mini`
(fixed in the prior normalization pass) — confirmed still correct. See
`final-business-audit-1920x1080.png` / `-1366x768.png`.

**FUNCTIONAL TEST**: category selection (`ba-category-selection`),
filters + advanced filters toggle (`ba-filters-apply`,
`ba-advanced-filters-toggle`), detail opens (`ba-detail-opens`) — all
pass.

---

## 5. PRODUCTION SCHEDULE

**BEFORE ISSUE (task's stated concern)**: "excessive nested framing."

**STRUCTURAL ROOT CAUSE — investigated, not assumed**: Measured the
actual box model live before changing anything: `.panel#schedulePanel`
top = 88px, `.ui-filter-bar` top = 121px — a 33px gap, matching exactly
`.panel`'s 16px padding + the sticky toolbar's 16px top padding. This is
normal spacing, not an unexplained gap or wasted region. The outer
composition is: one `.panel.schedule-control-panel` → sticky toolbar
(FilterBar + legend) → per-PO Gantt cards (each genuinely needs its own
bordered card, since multiple POs can be shown) → Material Flow section.
That is **not** "panel inside panel inside panel for the same content" —
it is one outer container plus functionally-necessary per-PO cards, which
the task explicitly permits ("unless functionally necessary").

**CHANGE**: None to markup/CSS structure — the composition was already
correct. Retested and reconfirmed rather than left unverified.

**AFTER RESULT**: Unchanged visually; re-verified via the same five
acceptance questions: no floating single-action row (reload sits with
the PO select in one FilterBar), no oversized empty region, no orphan
KPI (this page has none), tabs n/a (no navigation tabs on this page —
the internal "Material Flow" label is a real distinct subsection,
correctly left alone per the task's own instruction), nesting is
functionally justified. See `final-production-schedule-1920x1080.png`.

**FUNCTIONAL TEST**: PO filter (`ps-po-filter`), refresh (`ps-refresh`),
Gantt present (`ps-gantt-present`), Material Flow present
(`ps-material-flow-present`), scroll/sticky — **sticky toolbar
re-verified pinned at exactly `top:72px`** after a 600px scroll
(`ps-sticky-toolbar-pinned`, unchanged from every prior pass this
session) — all pass. Gantt coordinates, sticky PO header, and horizontal
timeline scrolling were not touched.

---

## 6. KIOSK MANAGEMENT

**BEFORE ISSUE**: "Làm mới" rendered alone in an otherwise-empty
full-width row (same floating-action-row defect as Production Order).
The 5-metric KPI grid used a hardcoded 4-column grid, so the 5th card
("Xung đột offline") wrapped alone onto a second row — a visually
orphaned card.

**STRUCTURAL ROOT CAUSE**: `body[data-page="kiosk-management"]
#kmSummary{grid-template-columns:repeat(4,minmax(0,1fr))}` — hardcoded
4 columns for a KPI set that has always had 5 metrics
(Tổng kiosk/Online/Chờ đăng ký/Có lỗi/Xung đột offline). Same
actions-only-page-header defect as Production Order for "Làm mới".

**CHANGE**: Moved `#kmSummary` (the KPI grid) into `.page-header`
alongside the reload button (same pattern as Production Order). Changed
the desktop grid to `repeat(5,minmax(0,1fr))` with a new intermediate
`@media(max-width:1400px){repeat(3,...)}` step before the existing
900px/2-column and 520px/2-column breakpoints, so the reduction reads as
intentional at every width instead of jumping straight from 5 to a
lopsided 4+1.

**AFTER RESULT**: All 5 KPI cards render in one balanced row at 1920px,
with "Làm mới" aligned to its right — verified all 5 cards share the
same `getBoundingClientRect().top`. At 1366px it steps down to a
3+2 arrangement (still no single orphan on its own line relative to the
group it's paired with) — see `final-kiosk-management-1366x768.png`.
Then FilterBar, then "Kiosk theo bộ lọc" ContentPanel + cards, unchanged.

**FUNCTIONAL TEST**: refresh (`km-refresh`), search (`km-search`), status
filter (`km-status-filter`), device card → detail opens
(`km-device-card-detail`) — all pass; kiosk status/heartbeat rendering
untouched.

---

## 7. GUIDANCE

**BEFORE ISSUE**: `[MESFlow] [ESP Kiosk]` rendered as filled, rounded,
button-shaped controls (reusing System Logs' then-also-button-shaped
`.sl-tab`) — visually indistinguishable from an ordinary `.btn`, not
readable as tabs. A "MESFLOW LEARNING CENTER" eyebrow label added no
information beyond what the now-active "MESFlow" tab already states.
Search/category used a bespoke `.tutorial-tools` row, not the canonical
FilterBar.

**STRUCTURAL ROOT CAUSE**: `.sl-tab` (and by extension `.guide-tabs`,
which shared its CSS) was built on top of the `.btn` class — inheriting
`.btn`'s border/radius/fill — instead of the underline tab pattern
already established (independently, in nearly identical form) by
Exception Center and Production Trace.

**CHANGE**: Part of the app-wide tab-language consolidation (§J).
Dropped `.btn sl-tab` from the markup; both tab buttons now render
through the shared `.mf-tab` class. Removed the "MESFLOW LEARNING
CENTER" eyebrow+description block (kept ESP Kiosk's eyebrow+firmware/
tutorial-version badges, since those carry real information, not a
restated title). Converted the search+category-select row to
`MFUI.filterBar()`.

**AFTER RESULT**: `Hướng dẫn` (Topbar) → `[MESFlow] [ESP Kiosk]` as real
underline tabs, pixel-identical to Exception Center/Production Trace/
System Logs → canonical FilterBar (search + nhóm) → video grid. No
second pseudo-header, no left rail (already removed in the prior task).
See `final-tutorials-1920x1080.png` / `-1366x768.png`.

**FUNCTIONAL TEST**: MESFlow tab active by default
(`guide-mesflow-tab-default`), search (`guide-search`), group filter
(`guide-group-filter`), video card opens the player
(`guide-video-card-interaction`), ESP Kiosk tab switch (`guide-esp-tab`),
and — the specific regression risk of a client-side SPA tab rewrite — a
full browser **refresh + re-navigation** still renders the tab bar
correctly (`guide-refresh-state`) — all pass.

---

## FLOATING ACTION ROWS

BEFORE: 2 (Production Order's action-only header row, Kiosk Management's
"Làm mới"-only header row).
AFTER: 0 — both merged into a combined stats/KPI + actions row.

## OVERSIZED EMPTY REGIONS

BEFORE: 1 (Production Trace's full-navy `.trace-summary` treatment
applied to the "no PO selected" placeholder, plus an empty
`ContentPanel` containing only a stray, incorrectly-visible-despite-
`hidden` "Tải thêm sự kiện" button).
AFTER: 0 — replaced with `MFUI.emptyState()`; the timeline panel and
tab bar are hidden entirely until a PO is selected; the underlying
`[hidden]` CSS bug is fixed app-wide.

## ORPHAN KPI ROWS

BEFORE: 1 (Kiosk Management's 5th KPI card alone on its own row at
1920px).
AFTER: 0 — 5-column grid at desktop width, intentional 3-column and
2-column reductions below it.

## TAB VISUAL IMPLEMENTATIONS

BEFORE: 3 distinct implementations for 4 navigation-tab surfaces —
underline (`.ec-tabs`/`.trace-filters`, two near-identical but separate
definitions), filled-pill (`.sl-tab`, shared by System Logs and
Guidance).
AFTER: 1 — every navigation-tab surface (Exception Center, Production
Trace, System Logs, Guidance) renders through the same `.mf-tabs`/
`.mf-tab` CSS. Business Audit's category chips were deliberately *not*
folded into this component — they are filter chips, not navigation, and
now live inside the FilterBar with that distinction documented in code.

## UNNECESSARY NESTED PANELS

BEFORE: 0 confirmed (Production Schedule's nesting was investigated and
found to be functionally necessary, not excessive — see §5).
AFTER: 0 (unchanged; the investigation itself is the deliverable here,
not a code change).

---

## LEGACY CSS / DEAD CODE REMOVED

Confirmed 0-referenced before deletion in every case: `.ec-tabs button`/
`.ec-tabs button.active`, `.trace-filters button`/`.trace-filters
button.active` (superseded by `.mf-tab`), `.system-log-tabs`/
`.guide-tabs`'s old `.toolbar`/`.sl-tab` filled-pill rules (both the
desktop and 520px-media copies), the `.trace-filters .btn,input,select`
entries in the shared control-height-unification list (dead once
`.pt-filter` buttons stopped carrying `.btn`), `.tutorial-hero h2`/
`.tutorial-hero p`/`.tutorial-tools` (+ its two media-query fragments,
dead once Guidance's search moved into `MFUI.filterBar()`).

## REAL BUG FOUND AND FIXED (not in the original task list)

`[hidden]` was silently broken for every `.btn`/`button.primary`/
`.primary` element app-wide, because the canonical button rule sets
`display:inline-flex` unconditionally, and author CSS always overrides
the User Agent stylesheet's `[hidden]{display:none}` regardless of
specificity. Found live while investigating Production Trace's oversized
empty region (`#ptMore` had `hidden` yet was visible). A second instance
(`#seModalSecondary` in `session-exceptions.js`) was found by grepping
the whole frontend for the same pattern. Fixed with one defensive rule
(`.btn[hidden],button.primary[hidden],.primary[hidden]{display:none}`)
rather than patching each call site — protects every future page that
uses `hidden` on a button, not just the two found today.

---

## VISUAL VERIFICATION (real deployed screenshots, both viewports)

Captured and **visually inspected** — not auto-passed on DOM measurements
alone — for all 7 pages at 1920×1080 and 1366×768 against the real
deployed 71.0.0.24 build (`reports/screenshots/composition-convergence/
final-*.png`). For every page, answered explicitly:

| Page | Floating action row? | Oversized empty region? | Orphan KPI card? | Tabs canonical? | Excessive nested panels? |
|---|---|---|---|---|---|
| Production Order | No | No | No | n/a | No |
| Exception Center | No | No | No | Yes | No |
| Production Trace | No | No | No | Yes | No |
| Business Audit | No | No | No | n/a (filter chips, documented) | No |
| Production Schedule | No | No | No | n/a | No (investigated, functional) |
| Kiosk Management | No | No | No | n/a | No |
| Guidance | No | No | No | Yes | No |

All "No"/"Yes" answers are the desired outcome — no page triggered the
"first five YES = not complete" rule.

## FUNCTIONAL REGRESSION

39/39 targeted composition/behavior checks (listed inline above, per
page) + full 16-page × 2-viewport Playwright audit (32 captures) + the
general 12-check regression suite + `pytest` — **all run twice**, once
against the live-preview container during implementation and once
against the real deployed 71.0.0.24 build. 0 page errors, 0 console
errors, 0 unintended horizontal overflow at either viewport, on every
page.

## LOCAL BUILD

`scripts/build-release.sh --bump` → `IMAGE RELEASE PASS`, version
71.0.0.24, schema `0037_v72_audit_operations_separation`, package
`artifacts/releases/71.0.0.24/MESFlow_71.0.0.24.deploy.zip`.

## LOCAL DEPLOY

Deploy Agent `POST /agent/api/release-manager/deploy-local
{"version":"71.0.0.24"}` → job `success`. Steps: backup → stage → install
→ restart ("MES Docker stack started; PostgreSQL data preserved") →
health ("Version 71.0.0.24 and health verified") → rollback skipped (not
required). `from_version: 71.0.0.23`.

## LOCAL HEALTH

`GET /api/system/health` → `{"ok": true, "status": "healthy", "version":
"71.0.0.24", "postgres_version": "17.10", "schema_version": "72.0.0.0"}`.

POSTGRES RESTARTED: NO
PRODUCTION TEST TOUCHED: NO
PRODUCTION TOUCHED: NO

---

Per the explicit stop condition, the UI contract is **not** marked
FROZEN in this task — this report only documents the composition
convergence pass.
