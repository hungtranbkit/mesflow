# UI Content Hierarchy Normalization

VERSION BEFORE: 71.0.0.21
VERSION AFTER: 71.0.0.22

Upgrades the Golden UI Template Standard with a **Content Hierarchy
contract** (`docs/architecture/UI_TEMPLATE_STANDARD.md`, new Phase 14),
then normalizes all 16 already-migrated pages against it. Prior phases
made every page's *geometry* consistent; this pass fixes *what the page
says*, not how it's laid out — duplicate/near-synonym headings, a
description that just lists everything already visible below it, and a
static technical badge sitting in every page's business-content flow.
Golden geometry, page edges, filter bars, content panels, workflows,
APIs, and business logic are all unchanged.

## CONTENT HIERARCHY CONTRACT (docs/architecture/UI_TEMPLATE_STANDARD.md, Phase 14)

- **Topbar**: global/module context only, compact, universal — this is
  where each page's one real title+description live.
- **PageHeader**: optional as a whole. A distinct title+description only
  when the Topbar doesn't already cover it; an actions-only row when the
  page has page-level actions but no distinct title to add; omitted
  entirely otherwise.
- **SectionHeader/PanelHeader**: optional, used only for a real
  subsection that isn't just "Danh sách" + the same noun already named
  above it.
- **Technical metadata** (DB backend, schema, API mode, debug/runtime):
  never in the primary business-content flow; stays available via
  Monitoring/`/api/system/health` for admin/diagnostics.
- **No duplicate semantic headings**: flag any in-content title that
  names the Topbar's subject with only a generic qualifier swapped
  ("Quản lý X"/"Danh sách X"/translated-synonym); keep titles that name a
  genuinely different angle (catalogue vs. print action, topic vs.
  specific visualization, etc.).

## PER-PAGE AUDIT AND NORMALIZATION

| PAGE | PRIMARY TITLE | REMOVED/MERGED HEADING | DESCRIPTION BEFORE | DESCRIPTION AFTER | TECHNICAL METADATA MOVED | RESULT |
|---|---|---|---|---|---|---|
| Production Orders | Production Order (Topbar) | h2 "Quản lý lệnh sản xuất" + p | (Topbar unchanged) | (unchanged) | PostgreSQL badge | Actions-only header (+Tạo PO từ Template/Nhập/Xuất Excel); StatsRow is now the first thing under Topbar |
| Session Management | Quản lý Session (Topbar) | h2 "Danh sách Session" + p | (Topbar unchanged) | (unchanged) | PostgreSQL badge | Actions-only header (Làm mới); FilterBar is first content |
| Session Exception Center | Trung tâm ngoại lệ (Topbar) | in-content h2 "Hàng đợi ngoại lệ"+p, **and** `.ec-command` banner's own h2 "Action Required"+p (3 headings → 1) | (Topbar unchanged) | (unchanged) | PostgreSQL badge | `.ec-command` banner kept (real alert content) but now shows only its live `#ecSummary` counts, right-aligned |
| Employees | Quản lý nhân viên (Topbar) | h2 "Danh sách nhân viên" + p | (Topbar unchanged) | (unchanged) | PostgreSQL badge | Actions-only header (+Thêm nhân viên) |
| Equipment | Thiết bị sản xuất (Topbar) | h2 "Danh sách thiết bị" + p | (Topbar unchanged) | (unchanged) | PostgreSQL badge | Actions-only header (+Thêm thiết bị) |
| Users | Người dùng hệ thống (Topbar) | *(kept — see below)* | (unchanged) | (unchanged) | PostgreSQL badge | No change: "Danh sách tài khoản" names accounts/credentials, a real distinction from "users" the people |
| Working Calendar | Ca làm việc (Topbar) | h2 "Danh sách ca làm việc" + p | (Topbar unchanged) | (unchanged) | PostgreSQL badge | Actions-only header (+Thêm ca) |
| Overview | Tổng quan sản xuất (Topbar) | h2 "Đang sản xuất" + p (whole `.page-header` removed, no actions to keep) | (Topbar unchanged) | (unchanged) | PostgreSQL badge | FilterBar is now the first thing under Topbar |
| Dashboard | Dashboard theo ngày (Topbar) | h2 "Báo cáo ca sản xuất" + p (whole `.page-header` removed) | "Tình hình sản xuất, nhân lực và chất lượng theo từng ca" (Topbar) + "Chọn ngày và ca để xem sản lượng, người đang làm, Operation có vấn đề và lịch sử hoạt động." (in-content, removed) | "Theo dõi sản lượng, nhân lực và tình trạng sản xuất theo ngày và ca." | PostgreSQL badge | The task's worked example: date/shift filters now the first content; description states purpose once instead of listing every visible section |
| Production Trace | Production Trace (Topbar) | h2 "Dòng thời gian sản xuất" + p (whole `.page-header` removed) | (Topbar unchanged) | (unchanged) | PostgreSQL badge | FilterBar (PO select) is first content |
| Kiosk Management | Quản lý trạm Kiosk (Topbar) | h2 "Thiết bị kiosk" + p | (Topbar unchanged) | (unchanged) | PostgreSQL badge | Actions-only header (Làm mới); KPI cards immediately follow |
| Business Audit | Nhật ký nghiệp vụ (Topbar) | h2 "Nhật ký nghiệp vụ" + p — **byte-for-byte identical to the Topbar title** | (Topbar unchanged) | (unchanged) | PostgreSQL badge | Whole `.page-header` removed; category chips are first content |
| System Logs | Nhật ký ứng dụng (Topbar) | *(kept — see below)* | (unchanged) | (unchanged) | PostgreSQL badge | No change: "Theo dõi vận hành hệ thống" frames operational monitoring, distinct from "application log records" |
| QR Print | Danh sách QR Code (Topbar) | *(kept — see below)* | (unchanged) | (unchanged) | PostgreSQL badge | No change: Topbar names the catalogue being browsed, PageHeader names the print action being taken |
| Production Schedule | Tiến trình sản xuất (Topbar) | *(kept — see below)* | (unchanged) | (unchanged) | PostgreSQL badge | No change: Topbar names the topic, PageHeader names the specific Gantt/Material-Flow visualization |
| Templates | Quy trình sản xuất mẫu (Topbar) | *(kept — see below)* | (unchanged) | (unchanged) | PostgreSQL badge | No change: "process template" (Topbar) vs. "template library" (PageHeader) are a real, not mechanical, distinction |

**REAL SECTIONS preserved everywhere** (unaffected by this pass):
StatsRow/KPI strips, FilterBar rows, every `ContentPanel`/table/card
region, `.ec-command`'s live summary counts, tabs, drawers, modals — none
of this content or its data/logic changed.

## DUPLICATE HEADINGS

BEFORE: 12 redundant heading instances across 11 pages (Session Exception
Center counted twice — its in-content PageHeader and its `.ec-command`
banner were both redundant with the Topbar and with each other).

AFTER: 0.

## TECHNICAL BADGES IN BUSINESS FLOW

BEFORE: 1 (`PostgreSQL`, a static, never-dynamically-updated `.db-state`
badge baked into the persistent Topbar in `app.html` — present in the
business-content flow of all 16 pages simultaneously, every time any page
was opened).

AFTER: 0 — relocated to a small `.sidebar-db-state` line in the sidebar's
account footer (near the username/role, an admin/system-identity zone,
not the operational content band). The underlying information was not
deleted: it was never a live indicator to begin with (no JS ever updated
it), and real diagnostics remain on the Monitoring page
(`/api/system/monitoring`) and `/api/system/health`.

## REGRESSION

Preserved and verified unchanged: Golden geometry (page-shell edges
measured at 0px deviation vs. Golden Production Orders on every affected
page, both viewports), filter bars, content panels, all workflows/APIs/
business logic. No route, permission, or data-fetching code was touched
anywhere in this pass — only heading markup, one CSS relocation, and one
shell-template badge move.

**CSS validation**: brace/paren-balanced `ui.css`, `git diff --check`
clean.

**JS check**: `node --check` clean on `app.js`, `pages/exception-center.js`,
`pages/overview.js`, `pages/production-trace.js`.

**pytest**: `tests/test_v71_ui_foundation.py tests/test_web_ui.py` → 7
passed (run against the preview container and the real deployed
71.0.0.22 build).

**Full 16-page UI audit**: 32/32 captures clean (0 overflowing, 0
console/request errors), run twice.

**General functional regression suite**: 12/12 pass, run twice (login, PO
nav/back, session filters, exception tabs/drawer, templates-tools-toggle,
0 console errors, 0 failed requests).

## VISUAL VERIFY

Real LOCAL browser screenshots captured at 1920×1080 for every one of the
16 pages, before and after, with a dedicated top-300px crop inspected for
each (the viewport band the task asked to focus on). Confirmed for every
normalized page: one obvious page title, no immediately-repeated synonym
title, no unexplained technical badge, first useful content (filters/KPI/
list) appears within the first ~150px of scrollable content instead of
after two stacked heading blocks. Dashboard's before/after crop is the
clearest example — the redundant "Báo cáo ca sản xuất" heading and the
"PostgreSQL" badge are both gone, and the date/shift filter row now sits
directly under the Topbar's description line.

## LOCAL BUILD

`scripts/build-release.sh --bump` → `IMAGE RELEASE PASS`, version
71.0.0.22, schema `0037_v72_audit_operations_separation`, package
`artifacts/releases/71.0.0.22/MESFlow_71.0.0.22.deploy.zip`.

## LOCAL DEPLOY

Deploy Agent `POST /agent/api/release-manager/deploy-local
{"version":"71.0.0.22"}` → job `success`. Steps: backup → stage → install
→ restart ("MES Docker stack started; PostgreSQL data preserved") →
health ("Version 71.0.0.22 and health verified") → rollback skipped (not
required). `from_version: 71.0.0.21`. (The Topbar/sidebar template change
in `app.html` required one container restart during local-preview
verification for Flask's cached Jinja template to pick it up — confirmed
via before/after HTML fetch; this restarted only the `mesflow-app`
container, not PostgreSQL, and happened before the official
build/deploy, not as part of it.)

## PLAYWRIGHT

Full 16-page × 2-viewport audit (32 captures) plus a dedicated 16-page ×
top-300px content-hierarchy screenshot pass, both run against the preview
container and the real deployed 71.0.0.22 build.

## PAGE ERRORS

None across any capture.

## CONSOLE ERRORS

None across any capture.

POSTGRES RESTARTED: NO
PRODUCTION TEST TOUCHED: NO
PRODUCTION TOUCHED: NO
