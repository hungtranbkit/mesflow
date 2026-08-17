# MESFlow UI Template Standard

Status: canonical, staged migration in progress.
Source of truth for tokens/visual language: `DESIGN.md` (this document does not
redefine tokens — it defines the *structural* contract DESIGN.md's component
section implies but never fully names, and maps it onto real MESFlow code).

This document is the result of Phase 1 (audit) through Phase 11 (contracts) of
the UI Template Standard task. It does not itself change any code — Phase 12
(foundation implementation) and Phase 13 (golden reference page migration)
are covered by the accompanying commit and `reports/UI_TEMPLATE_FOUNDATION.md`.

---

## PHASE 1 — Audit of the current UI foundation

### Files inspected

- `DESIGN.md` — canonical token/visual spec, already exists and is well-formed
  (v1.1, `status: canonical`). Nothing here contradicts it; the gap is that
  page *structure* was never standardized against it, only individual
  properties (color, radius, shadow) were.
- `.impeccable/design.json` — a **stale** sidecar generated 2026-08-08 by an
  external "Impeccable" tool. Its color tokens (`command-navy: #18324a`,
  `signal-amber: #e39a22`) do not match `DESIGN.md`'s actual tokens
  (`command-800: #18364e`, `action-600: #23658b`) or the CSS actually shipped.
  No regeneration CLI for it exists anywhere in this workspace. Left
  untouched — regenerating it is out of scope for this task and inventing a
  new format for it is explicitly prohibited.
- `app/mesflow/web/templates/app.html` — the App Shell. Its own inline
  comment already states the intended architecture precisely: *"persistent
  navigation, compact context header, dense operational workspace, primary
  action in context."* That sentence is the real specification for Phase 2's
  shell/header split, already written into the codebase, just never
  formalized or consistently followed.
- `app/mesflow/web/static/ui.css` (1,259 lines) — three generations of design
  tokens layered as separate `:root` blocks (a legacy base, a "canonical
  implementation," an "Industrial Soft-3D" elevation layer), plus a later
  "V71 UX foundation" `--ui-*` token set, plus this session's own additive
  polish passes. All of them agree on the underlying color/radius values
  from `DESIGN.md` — the accumulated debt is structural duplication, not
  disagreement.
- `app/mesflow/web/static/core/ui.js` (94 lines) — `MFUI`, the one genuine
  shared-primitive module: `pageShell`, `pageHeader`, `filterBar`,
  `statusBadge`, `loadingState`/`emptyState`/`errorState`,
  `openDrawer`/`openModal`/`confirmDialog`. Real and reusable, but adopted by
  exactly one page (Session Management) before this task, and even there
  its `pageHeader` duplicated the shell's own title (fixed in a prior
  session commit, `7b36c74`).
- `app/mesflow/web/static/core/nav.js` — `AppNav`, in-app back-navigation
  (push/back/reset/persist). Orthogonal to page structure; not part of this
  standard.
- Representative pages read/screenshotted this session: Overview, Dashboard,
  Production Orders, Templates, Employees, Session Management, Session
  Exceptions (Exception Center), Production Trace, Business Audit,
  Production Schedule, Kiosk Management, System Logs, QR Print, Equipment,
  Users, Working Calendar — all 16 registered pages.

### 1. Existing reusable UI primitives

| Primitive | Real implementation today |
|---|---|
| App Shell | `app.html`: `.app-layout > .app-sidebar + .app-workspace(.workspace-header + #content)`. Universal, unavoidable, already consistent. |
| Sidebar nav | `app.js`'s sidebar builder + `.sidebar-item`/`.sidebar-group`/`.sidebar-sub-item`. Already consistent (fixed active-state visibility this session). |
| Drawer/Modal | `MFUI.openDrawer`/`openModal`/`confirmDialog` in `core/ui.js`, plus an older parallel hand-built drawer (`.drawer-backdrop`/`.drawer-panel` in `pages/session-detail.js`). Two implementations of the same concept; both real and used. |
| Status badge | `MFUI.statusBadge` (4 tones: success/warning/danger/neutral, `info` added this session) **and** a separate older `.badge`/`.status-pill`/`.workflow-badge` CSS family with its own tone classes. Two parallel systems. |
| Filter/toolbar | `MFUI.filterBar()` (used once) **and** five-plus hand-built page-specific toolbars (`.po-list-toolbar`, `.catalog-toolbar`, `.system-user-tools`, `.employee-tools`, `.ec-filters`, `.overview-filters`, generic `.toolbar`). All now share the same control-height/alignment rules (this session's polish passes), but are still five separate class names for one concept. |
| Table | Classic `<table>` inside `.table-wrap` **and** the newer `.ui-data-table` primitive (defined in `core/ui.js`'s CSS, unused by any page yet). |
| Page header (in-content) | No single implementation. See finding #4 below — this is the actual architectural problem the task description names. |

### 2. Duplicate implementations found

- **Two badge/status systems**: `MFUI.statusBadge()` vs. the classic
  `.badge`/`.pc-state`/`.workflow-badge`/`.equipment-state`/`.user-role`
  family. Both map to the same `DESIGN.md` semantics but are separate code.
- **Two drawer systems**: `MFUI.openDrawer()` vs. the hand-rolled
  `.drawer-backdrop`/`.drawer-panel` markup in `session-detail.js`.
- **Two table systems**: classic `<table>` vs. `.ui-data-table` (defined,
  never adopted).
- **Six page-header implementations**, detailed in finding #4.
- **Five-plus toolbar container class names** for the one FilterBar concept
  (already unified in *behavior* — control heights, alignment — but not in
  *markup*/class identity).

### 3. Page-specific spacing/layout rules

`.panel-head` alone is redeclared roughly 30 times across responsive
breakpoints and page-specific contexts (grepped this session). Several
pages hard-code their own header block instead: `.po-list-head`,
`.overview-command`/`.overview-intro`, `.daily-command`/`.daily-command-copy`,
`.template-command`, `.ec-command`, `.schedule-sticky-toolbar .panel-head`.
Spacing values in these are almost all already on the 4/8/12/16/20/24/32
scale from `DESIGN.md` — the debt is naming/structural duplication, not
arbitrary pixel values (a few off-scale legacy values like `13px`/`11px`
remain in older rules and are called out where found, not swept wholesale).

### 4. Inconsistent headers — the core architectural finding

`DESIGN.md` §5.2 describes exactly one page-header contract ("H1 + one line
context; no hero card unless there's a real reason"), and `app.html`'s own
inline comment describes a *two-tier* header: a **compact context header**
(the shell's `workspace-header`, universal, unavoidable, title+subtitle only,
no actions slot) plus **"primary action in context"** — meaning the
*in-content* header is where the page's real actions live. That in-content
header is the piece with no single implementation. Measured this session:

| Implementation | Title size/weight | Used by |
|---|---|---|
| `.panel-head h2` (classic) | 15px / 20px / 700 | Employees, Equipment, Kiosk Mgmt, Users, Working Calendar, Business Audit, QR Print |
| `.po-list-head h2` | 20px / — / 700 (custom) | Production Orders |
| `.ui-page-header h2` (V71/`MFUI`) | 21px / 26px / 750 | (none, until this task's golden-page migration) |
| `.overview-intro h2` / `.daily-command-copy h2` | inherited `h2` default | Overview, Dashboard |
| `.template-command h2` | inherited `h2` default | Templates |
| `.ec-command h2` (dark banner) | inherited `h2` default, white-on-navy | Session Exceptions |

None of the six exactly matches `DESIGN.md`'s typography table, which
defines **Section title: 18px / 24px / 650–700** as the role one level below
the shell's own Page title (24/30/700) — which is precisely where an
in-content page header belongs. This mismatch, not any single "broken"
page, is why switching pages reads as inconsistent even after multiple
rounds of per-page CSS polish (documented in `reports/UI_QUALITY_AUDIT_FINAL.md`,
`reports/UI_VISUAL_POLISH_PASS2.md` — real fixes, but all downstream of this
un-unified foundation).

### 5. Inconsistent toolbars/filter areas

Mostly resolved this session (shared control-height `!important` rule
covering every known toolbar container; `.ui-filter-controls` bottom-alignment
fix; real `.btn.tertiary`/`.ghost` styling). Remaining gap: five-plus
container class names instead of one, and no single documented contract for
"where do primary vs. secondary actions go inside a toolbar."

### 6. Inconsistent panels/cards

Mostly aligned already: `.panel`/`.card`/`.daily-kpi`/etc. share one
border/radius/background/shadow rule (the "Industrial Soft-3D" layer). This
session added a KPI top-accent identity strip. Remaining gap: KPI/summary
rows were positioned *before* the page header on four pages until this
session's fix (`3d2ec9c`) — now uniformly after.

### 7. Inconsistent tables

Header language unified this session (uppercase, letter-spacing, 2px
separator) across every classic `<table>`. **Not yet done**: numeric-column
right-alignment (`DESIGN.md` §5.5 requires "số phải" — no current table
marks its numeric `<td>`s with a class the CSS could target; adding this
needs a small per-table markup change, done for the golden pages in this
task, not swept across all tables).

### 8. Inconsistent forms

Input/select/button heights unified this session (the `:where()` specificity
fix + the authoritative toolbar-control-height rule). Label placement is
already consistent (`<label><span>text</span><input></label>`, grid gap 4-5px).

### 9. Inconsistent drawers/modals

`MFUI.openDrawer`/`openModal` already implement `DESIGN.md` §5.9's contract
(Escape, focus trap/restore, scrim, standard sizes) correctly. The older
hand-built drawer in `session-detail.js` implements the same behaviors
independently (verified working, not broken) but as separate code. Not
touched in this task (out of scope — no business/workflow change, and this
task's phases don't include a drawer consolidation).

---

## PHASE 2 — Official page structure

```
MESFlowAppShell                              (app.html, universal, unchanged)
├── Sidebar                                  (.app-sidebar)
├── Topbar                                   (.workspace-header: H1 + 1-line context only, no actions)
└── PageShell                                (#content, per-page innerHTML)
    ├── PageHeader                           (title + description + primary/secondary actions)
    ├── FilterBar          optional
    ├── StatsRow           optional
    ├── ContentSection                       (Panel(s) / DataTable / cards)
    └── Drawer/Modal       optional
```

The Topbar is the shell's existing `workspace-header` — already universal,
already consistent, not part of the migration. **PageHeader is the
in-content header** carrying the page's actual title, description and
action buttons, per `app.html`'s own "primary action in context" design
intent. This is the one piece that needs a single canonical implementation.

---

## PHASE 3 — Page archetypes

| Archetype | Structure | MESFlow examples |
|---|---|---|
| **A. List** | PageHeader → FilterBar → StatsRow (optional) → Panel → DataTable | Production Orders, Employees, Equipment, Users, Working Calendar |
| **B. Detail** | PageHeader+Back → Summary → Tabs (optional) → Content sections | PO detail workspace, Session Detail drawer, Template editor |
| **C. Monitor** | PageHeader → Status/KPI → Monitoring content → Timeline/Table/Viz | Dashboard, Production Trace, Kiosk Management |
| **D. Workflow** | PageHeader → Workflow status → Queue/List → Detail drawer | Session Exception Center |
| **E. Audit** | PageHeader → FilterBar → Audit summary (optional) → Audit table/timeline | Business Audit, System Logs |

Overview is a hybrid List+Monitor (a command/filter panel, then KPI stats,
then a repair-queue list, then per-PO detail cards) — used as the general
visual-language reference per the user's explicit request, not a literal
single archetype.

---

## PHASE 4 — Canonical primitives and mapping

Per the task's explicit instruction, existing good implementations are kept
and standardized, not replaced:

| Primitive | Canonical implementation | Action taken |
|---|---|---|
| PageShell | `#content` (already universal) + `MFUI.pageShell()` for pages that opt in | No change needed to the mount point. `pageShell()` header now optional (Phase 12). |
| **PageHeader** | **New: `.page-header` class**, styled once to `DESIGN.md` §Typography "Section title" (18/24/650-700) | New shared class — see Phase 12. Existing `.panel-head`/`.po-list-head`/`.ui-page-header` markup patterns keep working (backward compatible); golden pages adopt `.page-header` explicitly. |
| FilterBar | `MFUI.filterBar()` markup + the shared toolbar-container CSS rule (already covers `.toolbar`, `.catalog-toolbar`, `.po-list-toolbar`, `.ec-filters`, etc.) | Documented as the one contract; no rename of existing containers (would touch every page, out of scope). |
| StatsRow | `.daily-kpis`/`.card`/`.employee-summary` family (KPI top-accent added this session) | Already consistent after this session's reordering fix; no new class needed. |
| Panel | `.panel` / `.panel-head` / panel body | Already consistent (shared border/radius/shadow). |
| Button | `.btn` + `.primary`/`.tertiary`/`.ghost`/`.danger` | Already consistent this session (real ghost/tertiary styling added). |
| Input/Select | shared `input`/`select` rules + the toolbar-control-height unification | Already consistent this session. |
| Badge | `MFUI.statusBadge()` (4 tones + `info` added this session) | Canonical for new/migrated code; classic `.badge` family kept for backward compatibility (not migrated — out of scope). |
| DataTable | classic `<table>` in `.table-wrap`, header language now unified | Canonical for now (real page content, real data density); `.ui-data-table` stays available for genuinely new tables. Numeric-column alignment added for the golden pages' tables. |
| Drawer/Modal | `MFUI.openDrawer`/`openModal` | Canonical for new/migrated code; existing hand-built drawer in Session Detail is unchanged (functions correctly, not in scope). |

---

## PHASE 5 — Design tokens

All tokens already exist and match `DESIGN.md` byte-for-byte (verified this
session): `--surface-canvas/default/subtle`, `--text-primary/secondary`,
`--border-default/strong`, `--bg-command`, `--action-primary/hover`,
`--status-info/success/warning/danger/offline`, `--radius-control/panel/overlay`,
`--ui-space-1..6` (4/8/12/16/24/32, completed this session). No new tokens
were needed for this task; the only addition is documenting which token the
new `.page-header` class uses for its title size (a new derived value, since
`DESIGN.md`'s "Section title: 18/24" was never actually wired into CSS
anywhere — see Phase 6).

---

## PHASE 6 — Page Header contract (mandatory)

```
Production Orders                                          [+ Tạo PO]
Quản lý kế hoạch và tiến độ sản xuất
─────────────────────────────────────────────────────────────────────
```

- **Left**: `<h2>` title (18px / 24px / weight 650–700, per `DESIGN.md`
  Section title) + `<p>` one-line description (13px, `--text-secondary`).
- **Right**: primary action (`.btn.primary`) first, secondary actions
  (`.btn`) after, single row, right-aligned.
- Spacing: `padding-bottom: 16px` (`--ui-space-4`), `border-bottom: 1px solid
  var(--border-default)`, `margin-bottom: 16px` before the next block.
- Vertical alignment: `align-items: center` between the text block and the
  action group (fixed for Production Orders this session; standardized here
  for every page that adopts `.page-header`).
- Responsive: below 900px, stack to column (existing `.panel-head` mobile
  rule already does this correctly — reused as-is).
- No page invents its own title size/weight/spacing for this role once it
  adopts `.page-header`.

---

## PHASE 7 — FilterBar contract

- One shared control height (`--control-height`, 36px desktop / 44px
  mobile) for every `input`/`select`/`.btn` inside a toolbar container —
  already enforced this session via one authoritative rule covering every
  known container class.
- Structure: `[free-text search, flexible width] [select filters, content-
  width] ... [ghost "Xóa bộ lọc" / secondary] [primary "Lọc"/"Làm mới" if
  present]`.
- All controls in a row share one bottom baseline (`align-items: flex-end`
  fix applied to `.ui-filter-controls` this session; classic toolbars
  already used `align-items:end`).
- Primary actions (e.g., "+ Tạo PO") belong in the **PageHeader**, not mixed
  into the FilterBar — the FilterBar's own trailing action is limited to
  filter-scoped actions (Lọc/Làm mới/Xóa bộ lọc).
- Wrapping at 1366px: verified clean (0 horizontal overflow) across all 16
  pages this session and re-verified for the golden pages in this task.

---

## PHASE 8 — Panel contract

```
Panel
├── PanelHeader (title/meta left, actions right)
└── PanelBody
```

Already implemented consistently: `border: 1px solid var(--border-default)`,
`border-radius: var(--radius-panel)` (8px), `padding: 16px` (12px mobile),
`box-shadow: var(--shadow-card)`, `.panel-head` for the header row with
`border-bottom: 1px solid var(--border-subtle)`. No change needed — this
contract was already close to `DESIGN.md` §5.3 before this task; verified
and left in place.

---

## PHASE 9 — Table contract

Already consistent: header height 38px / row height 42px (matches
`DESIGN.md`'s 36-44px range), uppercase header language, zebra striping,
hover state, `.table-wrap` horizontal scroll for overflow. **Added for the
golden pages in this task**: numeric-column right alignment (`text-align:
right` + `font-variant-numeric: tabular-nums` on quantity/count columns),
per `DESIGN.md` §5.5's explicit requirement — the one table-contract item
that was genuinely missing everywhere, not just inconsistent.

---

## PHASE 10 — Form/control contract

Already consistent this session: one control height per context, one radius
(`--radius-control`, 4-5px), one focus ring
(`outline: 2px solid var(--action-primary)`), real button-weight hierarchy
(primary/secondary/tertiary/ghost/danger all visually distinct). No further
change needed for this task.

---

## PHASE 11 — Overlay contract

`MFUI.openDrawer`/`openModal` already implement: header (title+close),
scrollable body, sticky footer with right-aligned actions, Escape-to-close,
focus trap/restore, standard width tiers (`--ui-drawer-sm/md/lg/xl`,
`--ui-modal-sm/lg`). Already matches `DESIGN.md` §5.9. Not modified in this
task — Session Exception Center's drawer (via `MFUI.openDrawer`) already
uses this contract correctly.

---

## PHASE 14 — Content Hierarchy contract (mandatory)

Phases 1–13 made every migrated page's *geometry* consistent (edges,
header height, filter/panel/control dimensions), but geometry consistency
does not by itself guarantee a page is easy to read. A migration can
produce a page that is structurally perfect and still show the same idea
twice — a large Topbar title immediately followed by a smaller in-content
heading that says essentially the same thing, or a technical
implementation detail (database backend, schema version) sitting in the
same visual band as the page's real content. This phase names that
problem and fixes it, without touching geometry, workflows, or business
logic. Real incident: Dashboard's Topbar ("Dashboard theo ngày" / "Tình
hình sản xuất, nhân lực và chất lượng theo từng ca") was immediately
followed by an in-content heading ("Báo cáo ca sản xuất" / "Chọn ngày và
ca để xem sản lượng...") saying the same thing in different words, plus a
static "PostgreSQL" badge with no operational meaning to a shift
supervisor — three redundant/irrelevant elements before the page's real
content (filters, KPIs) ever appeared.

### Roles

- **Topbar** (`.workspace-header`, `#pageTitle`/`#pageSubtitle`, set via
  `title.textContent`/`subtitle.textContent`) — global/module context
  only. Compact (72px, fixed). Persistent across every page. This is
  where the page's one real title+description live — see Page Title Rule
  below.
- **PageHeader** (`.page-header`, in-content, first child of
  `.page-shell` when present) — exactly one primary page title *only
  when the Topbar's title does not already cover it*, one concise
  supporting description, and/or primary/secondary page actions
  (`.page-header-actions`). **Optional as a whole.** A page with no
  distinct title to add and no page-level actions to host simply has no
  `.page-header` — content starts directly with FilterBar/StatsRow/
  ContentPanel. A page with page-level actions but no distinct title
  keeps `.page-header` as an **actions-only** row (`.page-header
  > .page-header-actions`, right-aligned via `margin-left:auto`) — this
  is not a violation of "PageHeader is the main heading," it is
  PageHeader's action-hosting role used on its own.
- **SectionHeader** (a `ContentPanel`'s `.content-panel-head`, or a
  page-specific banner like `.ec-command`) — only when there are multiple
  meaningful peer sections and the label describes a *real* subsection
  ("Operation cần chú ý", "Session đang mở", "Nhật ký theo bộ lọc"). Must
  not restate the PageHeader/Topbar's subject with a generic prefix swap
  ("Danh sách" + the same noun already named above it).
- **Technical metadata** (database backend, schema version, API mode,
  debug/runtime info) — must not appear in the primary business-content
  flow an operator scans every time they open a page. It stays available
  for admin/diagnostics (the dedicated Monitoring page already surfaces
  live `/api/system/monitoring` data; `/api/system/health` covers
  automated checks) but is demoted out of the persistent, always-visible
  chrome shown on every operational screen.

### No duplicate semantic headings

Before adding or keeping an in-content title, check it against the
Topbar's current title: **do they name the same subject with only a
generic qualifier different** ("Quản lý X" / "Danh sách X" / "X sản
xuất", or the same concept translated between English and Vietnamese —
"Production Order" vs. "Quản lý lệnh sản xuất")? If yes, it is a
duplicate — drop the in-content title (keep any actions). If the
in-content text names a genuinely different angle not covered by the
Topbar (QR Print's Topbar names the *catalogue* — "Danh sách QR Code" —
while its PageHeader names the *action* — "In tem QR"; Production
Schedule's Topbar names the *topic* — "Tiến trình sản xuất" — while its
PageHeader names the *specific visualization* — "Gantt + Material Flow"),
it earns its place and stays.

### Page Title Rule

Each page answers "what page am I on?" with **one** clear primary
heading — normally the Topbar's, since it is universal, always visible,
and already carries the larger "Page title" typography (24/30/700) one
level above PageHeader's "Section title" role (18/24/650–700). Do not
create a second near-synonym immediately below it merely to satisfy "the
template wants a PageHeader" — Phase 6's PageHeader contract is a
*format* for when a page-level title/description/actions block is
needed, not a mandate that one must always be manufactured.

### Panel Title Rule

ContentPanel/SectionHeader titles are optional. Use one only when it adds
information the page context doesn't already make obvious — real
examples already in the codebase: "Operation cần chú ý", "Lịch sử
retention", "Kiosk theo bộ lọc" (the "theo bộ lọc" qualifier is doing real
work — it tells the reader this list reflects the current filter state,
distinct from the StatsRow's unfiltered totals above it). Do not add a
bare "Danh sách"/"Báo cáo"/"Nội dung"/"Thông tin" panel title when the
page's own PageHeader or Topbar has already named the same subject one
qualifier away.

### Copy quality

Descriptions are one concise sentence. They orient the reader to *why*
this page exists, not enumerate every element already visible below it —
"Chọn ngày và ca để xem sản lượng, người đang làm, Operation có vấn đề và
lịch sử hoạt động" (lists four things the reader is about to see anyway)
became "Theo dõi sản lượng, nhân lực và tình trạng sản xuất theo ngày và
ca" (states the page's purpose once; the visible sections explain
themselves). Prefer this direction whenever a description reads as a
table of contents for what's already on screen.

### Do not force PageHeader + PanelHeader

The Golden template never required every page to stack a PageHeader and
another title immediately below it. **Required**: exactly one primary
heading, shown once (normally the Topbar's). **Optional**: PageHeader (as
title+description, or as an actions-only row, or omitted entirely) and
SectionHeader/PanelHeader, each used only where it adds real information.
This rule is why Phase 6's PageHeader contract describes a *format*, and
this phase describes *when to use it at all*.

### Applied fixes (this pass)

Removed a redundant in-content PageHeader title+description (content now
starts directly at FilterBar/StatsRow, or at an actions-only header row
when the page has page-level actions) on: Production Orders, Session
Management, Session Exception Center (its `.ec-command` banner also lost
its own duplicate "Action Required" heading — `#ecSummary`'s live counts
are the section's real content), Employees, Equipment, Working Calendar,
Overview, Dashboard, Production Trace, Kiosk Management, Business Audit
(whose in-content title was a byte-for-byte copy of its Topbar title).
Dashboard's Topbar description was also tightened per the Copy Quality
rule above. Kept as-is, on the genuinely-distinct-angle test: Users
("Người dùng hệ thống" vs. "Danh sách tài khoản" — people vs. their login
credentials, a real distinction), QR Print, Production Schedule, System
Logs, Templates.

The static `PostgreSQL` badge (`.db-state`, previously in the persistent
Topbar on every single page) was moved to a small `.sidebar-db-state`
line in the sidebar's account footer — demoted from "shown at the top of
every business screen" to "available near the account/system area for
whoever needs it," per the Technical Metadata rule. It was never a live
health indicator (no JS ever updated it); real diagnostics remain on the
Monitoring page and `/api/system/health`.
