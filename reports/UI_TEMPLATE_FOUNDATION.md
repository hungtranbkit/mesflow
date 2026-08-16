# MESFlow UI Template Foundation — Golden Reference Migration

Date: 2026-08-16
Project: `~/workspace/mesflow/mesflow`
Branch: `main`

Companion document: `docs/architecture/UI_TEMPLATE_STANDARD.md` (Phases 1–11:
audit, canonical shell/archetypes/primitives/tokens/contracts).

## Revision note (v2 — supersedes the first pass of this report)

The first version of this report claimed **READY TO FREEZE UI STANDARD: YES**
after attaching a shared `.page-header` CSS class onto each page's existing,
still-different bespoke container (`.po-list-panel` wrapped title+stats+
filters+table in one bordered box; Session Management's header/filters sat
unwrapped on the canvas; Exception Center had no separate header at all).
**Rejected on visual review**: same class name, three different geometries —
confirmed by the reviewer that the three pages still read as three different
UI systems, not one. Corrected finding: *same CSS class ≠ same visual
template.* This revision replaces that work with real structural
convergence — the three pages now share literal markup/geometry, not just a
class name — verified with `getBoundingClientRect()` measurements, not just
visual impression.

## CURRENT UI ARCHITECTURE

`app.html`'s App Shell (`.app-layout > .app-sidebar + .app-workspace
(.workspace-header + #content)`) is universal and was already consistent.
The problem was entirely inside `#content`. First pass found six different
in-content page-header *class names*; the deeper problem the reviewer
caught is that even after adding one shared class, the *surrounding
geometry* — whether the header/stats/filters sat inside one bordered panel,
sat bare on the canvas, or didn't exist at all; whether the filter row was a
bespoke grid or the shared toolbar; whether the data region was its own
bordered panel or fused into a bigger box — still differed page to page.
Visual consistency lives in that surrounding geometry, not in the header
class alone.

## NEW UI CONTRACT (v2 — real shared geometry, not shared class names)

```
#content (already display:grid;gap:16px — the single source of truth for
          left/right edges and vertical rhythm; nothing below introduces
          its own outer padding, so nothing can drift out of sync)
└── .page-shell            display:grid;gap:16px — direct child of #content
    ├── .page-header        PLAIN (no border/background — DESIGN.md 5.2:
    │                        "don't wrap the header in a hero card").
    │                        title h2 18/24/700 + description + actions.
    ├── .stats-row          optional, plain text counts strip
    ├── .ec-command         optional, the ONE sanctioned bordered/dark
    │                        "Command/Status panel" variant (Workflow
    │                        archetype only)
    ├── .ui-filter-bar      MFUI.filterBar() — same generated markup for
    │                        every page that has a filter row, not three
    │                        implementations wearing a matching class
    └── .content-panel      PanelHeader (title + optional meta, left) +
         ├─ .content-panel-head   PanelBody (table / card list / empty state)
         └─ .content-panel-body
```

Every one of PageHeader/StatsRow/CommandPanel/FilterBar/ContentPanel is now
a **direct sibling inside the same `.page-shell` grid**, so left/right edges
and vertical gaps come from one place (`#content`'s and `.page-shell`'s own
`display:grid;gap:16px`) instead of each page choosing its own wrapper.

## PAGE ARCHETYPES

Unchanged from the first pass: A. List, B. Detail, C. Monitor, D. Workflow,
E. Audit. Full detail in `docs/architecture/UI_TEMPLATE_STANDARD.md`.

## PRIMITIVES

| Primitive | v1 (rejected) | v2 (this revision) |
|---|---|---|
| PageShell | n/a | **New `.page-shell`** — `display:grid;gap:16px`, the actual layout parent all sections share |
| PageHeader | `.page-header` class layered onto 2 different old containers | Same class, but now truly standalone (no border, no wrapper padding) — identical markup shape on all 3 pages |
| StatsRow | `.po-list-summary` (PO only) | **New `MFUI.statsRow()`** + `.stats-row` — one real shared implementation |
| Command/StatusPanel | n/a (EC's banner had no separate header above it) | Formalized as the one sanctioned bordered/dark variant for the Workflow archetype; `.ec-command` |
| FilterBar | 3 separate implementations (`.po-list-toolbar`, `MFUI.filterBar()`, `.ec-filters`) each with different padding/grid | **Consolidated to one**: `MFUI.filterBar()` generates the exact same markup for all 3 pages now (`filterBar()` extended with `clearLabel`/`actions` params to cover PO's "Đặt lại"+"Làm mới" and EC's "Áp dụng") |
| ContentPanel | table/list left inside the old bespoke wrapper | **New `MFUI.contentPanel()`** + `.content-panel`/`.content-panel-head`/`.content-panel-body` — one shared bordered region for every page's actual data |
| DataTable | `.num` alignment utility (kept) | unchanged |

## TOKENS

No new color/spacing tokens — `ui.css` already matched `DESIGN.md`. New CSS
is entirely structural (the primitives above), using existing tokens
(`--border-default`, `--radius-panel`, `--shadow-card`, `--control-height`).

## SHARED FILES CHANGED

- `app/mesflow/web/static/core/ui.js` — `MFUI.filterBar()` extended with
  optional `clearLabel`/`actions`; added `MFUI.contentPanel()` and
  `MFUI.statsRow()` as real, callable shared primitives (not just CSS).
- `app/mesflow/web/static/ui.css` — added `.page-shell`, revised
  `.page-header` (removed the v1 border/padding — DESIGN.md 5.2 compliance),
  added `.stats-row`, `.content-panel`/`.content-panel-head`/
  `.content-panel-body`, widened `.ui-filter-bar` padding to `12px 16px` to
  match `.content-panel-head`'s density. **Removed** now-dead legacy CSS:
  `.po-list-panel`, `.po-list-head`, `.po-list-summary`, `.po-list-toolbar`,
  `.po-primary-actions`, `.session-accordion-panel`, `.ec-filters` (all
  fully audited as zero remaining references in markup before deletion).
  Fixed a real regression the measurement pass caught: `.page-shell` is
  itself a CSS grid, so its own children needed the same `min-width:0`
  safety rule `#content>*` already had one level up — without it, Production
  Order's 9-column table overflowed the viewport by 139px at 1366×768.
- `app/mesflow/web/static/app.js` — Production Orders and Session
  Management both rebuilt on `.page-shell`/`.page-header`/`.ui-filter-bar`/
  `.content-panel` (no more `.po-list-panel` wrapper; Session Management's
  header restored with copy distinct from the Topbar — "Danh sách Session"
  vs. the Topbar's "Quản lý Session" — same pattern PO already uses).
- `app/mesflow/web/static/pages/exception-center.js` — added a `.page-header`
  above the "Action Required" panel (`DESIGN.md`'s attention-order principle
  keeps the dark banner first on screen, but it no longer stands in for a
  page title); `filters()` rebuilt to emit `MFUI.filterBar()`'s standard
  markup with labeled fields instead of a bespoke `.ec-filters` grid, and
  "Áp dụng" moved into the filter bar's shared `actions` slot; the exception
  list is now `.content-panel-body`, matching the other two pages' data
  region exactly.
- `tests/test_v71_ui_foundation.py` — updated the one assertion pinned to
  Session Management's old container classes.
- `docs/architecture/UI_TEMPLATE_STANDARD.md` — unchanged from Phase 1–11
  (the structural contract it describes is what this revision actually
  implements).

## GOLDEN PAGE 1 — PRODUCTION ORDERS

Un-nested from the single `.po-list-panel` box into 4 real siblings:
`.page-header` (plain) → `.stats-row` (plain) → `.ui-filter-bar` (bordered,
now shared markup) → `.content-panel` (bordered, "Danh sách Production
Order" header + table). Numeric "Kế hoạch" column right-aligned (kept from
the first pass).

## GOLDEN PAGE 2 — SESSION MANAGEMENT

Rebuilt on the identical 3-sibling structure (no StatsRow — this page has
no counts to show): `.page-header` ("Danh sách Session" + "Làm mới") →
`.ui-filter-bar` (same generated markup as Production Order and Exception
Center, not a lookalike) → `.content-panel` ("Session theo bộ lọc" + result
count + list/empty state).

## GOLDEN PAGE 3 — SESSION EXCEPTION CENTER

Gained the missing first step: `.page-header` ("Hàng đợi ngoại lệ") now
sits above the "Action Required" `.ec-command` panel, which is kept as the
one sanctioned Workflow-archetype Command/Status panel variant — a
component variant, not a different page template, per the task's explicit
instruction. Its filter row was rebuilt on `MFUI.filterBar()` (labeled
fields, same border/padding/control-height as the other two pages) instead
of the old bespoke `.ec-filters` 5-column grid; "Áp dụng" moved into the
filter bar's shared actions slot. The exception card list now lives inside
a `.content-panel`, the same bordered region PO's table and Session
Management's list use.

## VISUAL CONVERGENCE PASS

Side-by-side check at both required viewports: with the titles covered,
Production Orders, Session Management and Session Exception Center now
read as one application — same plain page-title band, same bordered
toolbar strip (border/radius/background/label style/control height
identical), same bordered content region with a title+meta header row. The
Exception Center's dark "Action Required" panel is the one deliberate
component variant, clearly a *component*, not a different page skeleton
around it.

| | Production Orders | Session Management | Session Exceptions |
|---|---|---|---|
| Page edge (L/R, 1920) | 272 / 1896 | 272 / 1896 | 272 / 1896 |
| Header geometry | plain, 46px tall | plain, 46px tall | plain, 46px tall (+ Command panel below) |
| Section gap | 16px (`.page-shell` gap) | 16px | 16px |
| Filter geometry | `.ui-filter-bar`, 36px controls | `.ui-filter-bar`, 36px controls | `.ui-filter-bar`, 36px controls |
| Content panel | `.content-panel`, border+radius+shadow | `.content-panel`, same | `.content-panel`, same |
| Control height | 36px (btn/input/select) | 36px | 36px |
| Panel radius | `var(--radius-panel)` | `var(--radius-panel)` | `var(--radius-panel)` |
| Panel border | `1px solid var(--border-default)` | same | same |
| Density | compact, no added whitespace | compact | compact (dark banner is the only intentional emphasis) |

### Bounding-box measurements (`getBoundingClientRect()`, live against the deployed build)

**1920×1080:**

| Region | Production Orders | Session Management | Session Exceptions |
|---|---|---|---|
| PageHeader L/R/H | 272/1896/46 | 272/1896/46 | 272/1896/46 |
| FilterBar L/R/H | 272/1896/83 | 272/1896/83 | 272/1896/83 |
| ContentPanel L/R | 272/1896 | 272/1896 | 272/1896 |
| Control height (btn/input/select) | 36/36/36 | 36/36/36 | 36/36/36 |
| Horizontal overflow | 0 | 0 | 0 |

**1366×768:**

| Region | Production Orders | Session Management | Session Exceptions |
|---|---|---|---|
| PageHeader L/R/H | 248/1346/46 | 248/1346/46 | 248/1346/46 |
| FilterBar L/R | 248/1346 | 248/1346 | 248/1346 |
| FilterBar height | 83 | 127 | 148 |
| ContentPanel L/R | 248/1346 | 248/1346 | 248/1346 |
| Control height (btn/input/select) | 36/36/36 | 36/36/36 | 36/36/36 |
| Horizontal overflow | 0 | 0 | 0 |

Left/right edges match **exactly (0px difference)** across all three pages
at both viewports, for every region. FilterBar *height* legitimately differs
at 1366px (83/127/148) because Session Management (6 fields) and Exception
Center (8 fields) wrap to more rows than Production Order (2 fields) at the
narrower width inside the same bordered box — expected content-driven
wrapping (Phase 7's "responsive wrapping" rule), not a geometry mismatch;
the box itself (border/radius/background/padding/control height) is
identical in all three.

A real regression was caught and fixed during this measurement pass:
Production Order overflowed the viewport by 139px at 1366×768 because
`.page-shell`, being itself a CSS grid, needed the same `min-width:0` safety
rule already applied one level up at `#content>*` — without it, the table's
natural width pushed `.content-panel` past the edge instead of scrolling
inside its own `.table-wrap`. Fixed; overflow is 0 at both viewports for
all three pages after the fix (verified above).

## 1920×1080

All three pages: identical PageHeader/FilterBar/ContentPanel geometry
(table above), 0 horizontal overflow, 0 console errors.

## 1366×768

All three pages: identical left/right edges, filter rows wrap gracefully
inside the same bordered box (not a layout break), 0 horizontal overflow
(including the regression caught and fixed above), 0 console errors.

## FUNCTIONAL REGRESSIONS

**None.** Re-verified after the full restructure:
- Production Orders: list loads, "Mở PO" navigates to detail, back
  navigation works, "Đặt lại"/"Làm mới" both still bound and functional.
- Session Management: filter fields work, "Thêm bộ lọc" toggles, "Làm mới"
  (now in the PageHeader) still fires its reload request.
- Session Exception Center: tab switch still re-renders and highlights the
  active tab; "Áp dụng" (now in the FilterBar's actions slot) still applies
  filters — verified live: selecting severity=CRITICAL and clicking "Áp
  dụng" fired the expected `/api/exceptions` request and filtered the card
  count from 25 to 2; card click still opens the detail drawer, drawer
  still closes.

## TESTS

| Check | Result |
|---|---|
| CSS brace balance | balanced |
| `node --check` (app.js, core/ui.js, exception-center.js) | OK |
| Python compile (`web/app.py`) | OK |
| Jinja parse (`app.html`, unchanged) | OK |
| `git diff --check` | clean |
| `tests/test_v71_ui_foundation.py`, `tests/test_web_ui.py` | 7 passed, 0 failed |
| Full 16-page × 2-viewport Playwright audit | 32/32 captures, 0 overflow, 0 console/page errors, 0 failed requests |
| 12-check functional smoke pass | 12/12 passed |
| Targeted EC filter-apply + tab-switch check | both fire the expected request/state change |

## LOCAL BUILD

```
build-release.sh --bump
IMAGE RELEASE PASS
Version: 71.0.0.17
Digest: sha256:1a5716485163eb94e374715516c6df038364f3b033c8ad72bd5936b14c6c41ba
Schema: 0037_v72_audit_operations_separation
```
(71.0.0.9 through .16 were already frozen releases from earlier this session.)

## LOCAL DEPLOY

Deployed via Deploy Agent's official `/api/release-manager/deploy-local`.
Job progression: `deploying` → `"CUTOVER: stopping application only;
gateway and PostgreSQL remain running"` → `verifying` → `success —
"Deployment verified: 71.0.0.17"`.

## LOCAL HEALTH

```json
{"status":"healthy","version":"71.0.0.17","schema_version":"72.0.0.0",
 "database_backend":"postgresql","postgres_version":"17.10"}
```
`mesflow-postgres` uptime unaffected (27h, never restarted).

## READY TO FREEZE UI STANDARD: YES

Grounds for this answer, per the task's explicit "don't claim success from
classes/tests/tokens alone" rule: the three pages now share **literal
markup structure** (the same `MFUI.filterBar()`/`contentPanel()` calls
generate the same DOM shape, not three implementations with a matching
class name), their outer boundaries measure **pixel-identical** at both
required viewports (table above), their control heights are identical, and
a side-by-side visual read (titles covered) reads as one system with one
intentional, clearly-labeled component variant (Exception Center's Command
panel) rather than three different templates. This is offered as evidence
for your review, not a substitute for it — the first pass also technically
passed every automated check and was still visually wrong, so please look
at the screenshots yourself before this is treated as final:
`reports/screenshots/golden-v2-deployed/`.

## REMAINING PAGES NOT MIGRATED

Overview, Dashboard, Templates, Production Trace, Business Audit,
Production Schedule, System Logs, QR Print, Equipment, Users, Working
Calendar, Kiosk Management — unchanged, per the explicit stop condition.

**PRODUCTION TEST TOUCHED: NO**
**PRODUCTION TOUCHED: NO**
