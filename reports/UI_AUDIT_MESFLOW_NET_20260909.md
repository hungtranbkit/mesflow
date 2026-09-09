# MESFlow UI Audit — TEST (mesflow.net) — 2026-09-09

Independent QA/UI reviewer pass. **Audit only — no fixes deployed.** Backlog
and Go/No-Go at the end. Evidence: 101 real Playwright screenshots +
per-element DOM measurements + axe (WCAG2A/AA) + keyboard tab-order, captured
live against `https://mesflow.net` (v71.0.0.253) as `admin`.

Evidence bundle: `scratchpad/ui-audit/evidence/` (screenshots named
`<page>-<viewport>.png`, raw data `audit-results.json`).

---

## 0. Method & honesty notes

- **Target**: real deployed TEST at `https://mesflow.net` (had to use `https` —
  the session cookie is `Secure`, plain `http` silently drops it). Login by
  real password (`admin` / `Admin@123456`); autologin is **off** on this host
  (`data-test-auto-login="0"`).
- **Coverage**: 24 authenticated SPA routes + 2 public kiosk pages, each at up
  to 4 viewports — **1920, 1366, 768 (tablet), 390 (mobile)**. axe run on all
  20 content pages at 1366; keyboard tab-order walked on every page.
- **What the numbers are**: hard DOM measurements (right-edge overflow, clipped
  controls, sub-24px touch targets, empty-detail detection) + axe. Anything
  needing judgement (is a label meaningful? is REWORK confused with scrap?) was
  decided from the **screenshots**, not asserted by script.
- **One false positive caught and excluded**: my first-pass overflow probe
  flagged "15 overflowing elements at tablet on *every* page" — identical count
  everywhere. On inspection those are the **off-canvas sidebar** (translated
  `left:-768px` as the mobile/tablet drawer, working correctly), not layout
  breaks. All counts below are **right-edge overflow only**, sidebar excluded.
  Same class of false positive removed from the kiosk state-machine's hidden
  `#screen-*` panels.
- **NOT covered by this pass (needs a second, interactive pass)** — these are
  behind clicks/modals the URL sweep can't reach, and the brief explicitly
  lists them:
  - PO detail, Part detail, Operation detail drill-ins (no own URL — click-only)
  - **OP SETUP** section (lives inside the Operation modal, needs a saved OP)
  - every modal/drawer (session detail, exception resolution 4-tab drawer,
    material-flow trace, all CRUD modals)
  - `/print/setup/<id>` print sheet
  - kiosk state screens past the idle "ready" screen
  This is a real coverage gap, stated plainly — not silently skipped.

---

## 1. Executive summary

MESFlow's web UI is, overall, **in good shape and mostly release-worthy**. It
is a genuinely responsive, consistently-built SPA: 22 of 24 pages reflow
cleanly to mobile, the sidebar collapses to a hamburger drawer, KPI grids
re-column, **no page scrolls the body horizontally at any viewport**, every
page's data loaded (**0 network failures across 101 loads**), and only **one**
JavaScript error exists in the whole sweep (an unlinked broken route). Real
accessibility care is visible — a working "Bỏ qua điều hướng" skip-link is the
first focusable element and tab order is logical. The brief's two specific
worries are **satisfied**: REWORK ("Chờ sửa") is visually distinct from NG and
Phế (three separate KPIs, NG shown red), and the Templates master-detail
**auto-selects the first item** so it never opens blank.

The problems are concentrated, not systemic:

- **One page is visibly broken at every width** — `system-logs`' KPI cards row
  bleeds off the right edge (the first card stretches to fill the viewport and
  shoves the other two off-screen), on desktop-1920 included.
- **Accessibility is the weakest dimension.** Colour-contrast fails WCAG AA on
  **every** content page (185 nodes total, one root cause: the muted-grey text
  token), and the **Templates editor has 104 form `<select>`s and 26 inputs
  with no accessible name** (axe *critical*) — invisible to sighted users,
  opaque to screen-reader/keyboard users.
- **Mobile has a handful of clipped controls** on the densest editors
  (Templates editor, Overview repair-plan), never on the core list/dashboard
  pages.

No page fails to load. No data is wrong. No destructive-path issue. This is a
polish-and-a11y backlog, not a rebuild.

---

## 2. Top 10 UI fragility / UX problems

| # | Sev | Page | Problem (measured) | Evidence |
|---|-----|------|--------------------|----------|
| 1 | **P1** | Nhật ký ứng dụng (`system-logs`) | KPI cards row (`.cards`) overflows **6,000–7,600px** past the right edge at **all four** viewports; first card ("Request 24h 6444") fills the whole width, "Lỗi 24h"/"Chậm 24h" are pushed off-screen and clipped (body doesn't scroll, so they're unreachable). Visibly broken on desktop-1920. | `system-logs-desktop-1920.png` |
| 2 | **P1** | Template (`templates`) | Template editor: **104 `<select>` with no accessible name + 26 unlabeled inputs** (axe *critical*: `select-name` n=104, `label` n=26). Keyboard/screen-reader users can't tell the per-Operation dropdowns apart. | axe, `templates-desktop-1366.png` |
| 3 | **P2** | Every content page | **Colour-contrast below WCAG AA on all 20 pages, 185 nodes.** Worst: Gantt/Material Flow (80), Dashboard·Nhân viên (34), Users (12). One root cause: muted-grey secondary-text token too light on the light ground. | axe all pages |
| 4 | **P2** | ESP OTA (`?page=esp-ota`) | Page renders **blank content** (only the shell), throws `ReferenceError: renderEspOta is not defined`, and shows the wrong fallback title "Dashboard". Unlinked route (URL-only) but a real broken page + the sweep's only console error. | `esp-ota-desktop-1366.png` |
| 5 | **P2** | Tổng quan (`overview`) | `aria-prohibited-attr` **188 nodes** (axe *serious*) — aria attributes on elements whose role forbids them, repeated across the repair-plan rows. Plus an **empty orphan KPI cell** (grey, bottom-right of the KPI block) at every viewport. | axe, `overview-desktop-1366.png` |
| 6 | **P2** | Template (mobile) | **182 form controls clipped** by `overflow:hidden` on the template editor at 390px — the 2-column editor grid doesn't reflow, so inputs/selects/buttons get cut off. | `templates-mobile-390.png` |
| 7 | **P2** | Template, QR Code | Checkboxes are **16×16px**, below the WCAG 2.5.8 / practical 24×24 touch-target minimum — 27 on Templates, 26 on QR list. One root cause (global checkbox size). | axe/measure |
| 8 | **P3** | Gantt & Material Flow, Hướng dẫn | `scrollable-region-focusable` (axe *serious*): the horizontally-scrollable Gantt / tutorial region can't be reached or scrolled by keyboard. | axe |
| 9 | **P3** | Năng suất nhân viên (mobile) | Wallboard action row (hint + "Xem trước / Áp dụng lên Kiosk / Mở màn hình Kiosk ↗") overflows **+38px** at 390px. | `employee-productivity-mobile-390.png` |
| 10 | **P3** | Nhật ký nghiệp vụ (mobile), Tổng quan (mobile) | Business Audit filter chips overflow **+10px**; Overview repair-plan PO buttons (6) clipped at 390px. Minor, mobile-only. | `business-audit-mobile-390.png`, `overview-mobile-390.png` |

---

## 3. Page PASS / FAIL

**PASS** = loads, no visible layout break at any viewport, no blocking a11y-critical, data present.
**PASS\*** = works and looks correct, but carries the shared contrast/AA debt (item #3) — not counted as a per-page fail because the cause is global.
**FAIL** = a visible break or an a11y-*critical* on that specific page.

| Page | Route | Verdict | Note |
|------|-------|---------|------|
| Login | `/login` | **PASS** | 0 overflow, 0 axe violations — cleanest page |
| Tổng quan sản xuất | `overview` | **PASS\*** | aria-prohibited (188) + orphan KPI cell; no visible break |
| Dashboard theo ngày (A/B/C) | `dashboard&tab=…` | **PASS\*** | 3 tabs stable; contrast on the timeline legend |
| Production Order (list) | `production-orders` | **PASS\*** | — |
| Template | `templates` | **FAIL** | a11y-critical: 104 unlabeled selects + 26 inputs; mobile editor clips 182 controls |
| Quản lý Session | `session-management` | **PASS\*** | — |
| Trung tâm ngoại lệ | `session-exceptions` | **PASS\*** | 5 tabs OK |
| Hàng chờ sửa (REWORK) | `rework-queue` | **PASS\*** | REWORK clearly distinct from NG/phế |
| Production Trace | `production-trace` | **PASS\*** | empty-state prompt (not blank) until PO chosen — correct |
| Nhật ký nghiệp vụ | `business-audit` | **PASS\*** | +10px chip overflow at mobile only |
| Gantt & Material Flow | `production-schedule` | **PASS\*** | worst contrast (80) + keyboard-unreachable scroll region |
| Trạm kiosk (admin) | `kiosk-management` | **PASS\*** | list+detail; prompt not blank — correct |
| Báo cáo năng suất NV | `employee-productivity` | **PASS\*** | +38px wallboard row at mobile only |
| Nhật ký ứng dụng | `system-logs` | **FAIL** | KPI cards overflow 6–7k px at ALL viewports |
| Nhân viên | `employees` | **PASS\*** | — |
| Danh sách QR Code | `qr-print` | **PASS\*** | 26 sub-24px checkboxes |
| Thiết bị | `equipment` | **PASS\*** | — |
| Người dùng | `users` | **PASS\*** | contrast (12) on RBAC table |
| Lịch làm việc | `working-calendar` | **PASS\*** | — |
| Hướng dẫn | `tutorials` | **PASS\*** | nested tabs OK; keyboard-unreachable scroll region |
| Part / Operation (raw CRUD) | `parts`,`operations` | **PASS\*** | — |
| ESP OTA | `esp-ota` | **FAIL** | blank content + ReferenceError + wrong title (unlinked route) |
| Kiosk web (public) | `/kiosk` | **PASS** | clean, purposeful, KIMEX-branded |
| Wallboard năng suất (public) | `/kiosk/employee-productivity` | **PASS** | 0 overflow both viewports |

**Score: 2 FAIL (system-logs, templates), 1 FAIL-unlinked (esp-ota), 23 PASS/PASS\*.**

---

## 4. Mobile / responsive matrix

Right-edge overflow (sidebar-excluded) / clipped interactive controls, per viewport:

| Page | 1920 | 1366 | 768 tablet | 390 mobile |
|------|:----:|:----:|:---------:|:---------:|
| Most list/dashboard/CRUD pages (18) | clean | clean | clean | clean |
| system-logs | **ovf** | **ovf** | **ovf** | **ovf** |
| templates | clean | clean | clean | **182 clipped** |
| overview | clean | clean | clean | 6 clipped |
| business-audit | clean | clean | clean | +10px |
| employee-productivity | clean | clean | clean | +38px |

Structural responsive behaviour (spot-checked on screenshots): sidebar →
hamburger drawer ✓, KPI grids re-column 4→2 ✓, filter bars stack ✓, **no body
horizontal scroll anywhere** ✓. The mobile problems are confined to the two
densest *editors/panels*, never the core operational pages.

---

## 5. Backlog / issue mapping

No existing open issues to dedupe against (repo issue tracker has **0 open**;
all closed issues are QC API/permission, none about UI/layout). This audit does
**not** duplicate the earlier `reports/UI_TEMPLATE_*`, `UI_QUALITY_AUDIT_FINAL`,
or `MESFLOW_NET_DEPLOY_20260907` passes — those covered composition/geometry;
the findings below (a11y-critical form labelling, the system-logs KPI overflow,
contrast at scale, esp-ota breakage) are new.

| Proposed issue | Sev | Pages | Minimal fix (no refactor) |
|----------------|-----|-------|---------------------------|
| **UI-1** system-logs KPI cards row overflows all viewports | P1 | system-logs | Constrain `.cards` to a grid (`grid-template-columns: repeat(3, 1fr)`) or cap the first card; it's a single container losing its width. |
| **UI-2** Template editor form controls have no accessible name | P1 | templates | Add `aria-label`/`<label for>` to the per-Operation `<select>`s and the 26 inputs in `poOperationRow`/template editor markup. |
| **UI-3** Colour-contrast below WCAG AA site-wide | P2 | all | Darken the muted secondary-text token (one CSS var in `ui.css`) to reach 4.5:1. Fixes ~185 nodes at once; re-run axe to confirm. |
| **UI-4** ESP OTA route is broken | P2 | esp-ota | Either implement `renderEspOta()`, or remove the `?page=esp-ota` dispatch and add an error-boundary so unknown pages show a message, not a silent blank + wrong title. |
| **UI-5** Overview aria-prohibited-attr (188) + orphan KPI cell | P2 | overview | Drop the prohibited aria attrs from the repair-plan rows; fill or collapse the empty KPI grid cell. |
| **UI-6** Template editor clips controls on mobile | P2 | templates | Let the editor grid reflow to one column below ~640px (drop the fixed 2-col + `overflow:hidden`). |
| **UI-7** Checkbox touch targets 16×16 | P2 | templates, qr-print, others | Global checkbox min 24×24 (or larger hit-area) in `ui.css`. |
| **UI-8** Keyboard can't scroll Gantt / tutorial regions | P3 | production-schedule, tutorials | Add `tabindex="0"` + `role`/`aria-label` to the scroll container. |
| **UI-9** Mobile overflow on wallboard actions / audit chips | P3 | employee-productivity, business-audit | Allow the action row / chip row to wrap at narrow widths. |

**Quick-fix candidates** (small, safe, no large refactor — but **not applied**,
per the brief's "KHÔNG deploy khi chưa báo audit summary"): UI-1 (one grid rule),
UI-3 (one token), UI-7 (one checkbox rule) are each a single-CSS-line change
with wide payoff. I can batch these three behind your go-ahead.

---

## 6. Go / No-Go for the current UI

**GO, with two must-fix-before-wide-release items.**

The UI is stable, responsive, data-correct and broadly accessible-aware; it is
fit for continued TEST use and a controlled release **now**. Two items should
land before it's put in front of a broad or accessibility-sensitive audience:

- **UI-1** (system-logs KPI overflow) — the one *visibly broken* page; embarrassing on an admin screen, trivial fix.
- **UI-2** (Template editor unlabeled controls) — the one *a11y-critical*; blocks keyboard/screen-reader use of a core authoring screen.

Everything else (contrast, esp-ota, mobile editor clipping, touch targets) is
real debt to schedule, not a release blocker. The unaudited surfaces (modals,
PO/Part/OP detail, OP SETUP, print sheet, kiosk state screens) are a **known
coverage gap** — a Go here covers the 26 surfaces actually tested, and I'd
recommend the interactive second pass before calling the *whole* UI audited.

---

### Awaiting direction
Per the brief I'm stopping at the audit. On your word I can: (a) run the
interactive second pass over the modals / PO-Part-OP detail / OP SETUP / print
sheet, (b) apply the 3 safe quick-fixes (UI-1/3/7) on a branch, and/or (c) open
these as tracked issues. No changes deployed.
