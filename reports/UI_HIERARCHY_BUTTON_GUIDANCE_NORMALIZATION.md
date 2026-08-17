# UI Hierarchy, Button & Guidance Normalization

VERSION BEFORE: 71.0.0.22
VERSION AFTER: 71.0.0.23

Finishes the remaining content-hierarchy normalization work (Phase 14,
`docs/architecture/UI_TEMPLATE_STANDARD.md`) on the pages the previous
pass missed, restructures the Guidance page's navigation, and fixes the
one bespoke button implementation the user reported (Business Audit). No
workflow, API, or business-logic change anywhere in this pass.

## GUIDANCE PAGE NAVIGATION

**GUIDANCE BEFORE**: a small vertical left-rail (`.guide-layout` /
`.guide-subtabs`) — a mini second sidebar next to the main content,
sticky, column-stacked "Hướng dẫn MESFlow" / "ESP Kiosk" buttons.

**GUIDANCE AFTER**: one main `Hướng dẫn` page with a compact horizontal
sub-tab bar (`[MESFlow] [ESP Kiosk]`) directly below the PageHeader,
inside the content area — no second sidebar. Reuses the existing
canonical sub-tab visual language (`.sl-tab`, already used by System
Logs) rather than inventing a new one: `.system-log-tabs`'s CSS rule was
generalized to also match a new `.guide-tabs` wrapper class
(`.system-log-tabs,.guide-tabs{...}`), so both pages share the exact same
tab markup/styling. Collapses to a stacked layout under 900px (the
existing `.ui-page-header`/`.ui-filter-bar` breakpoint convention) and
stays a compact horizontal pair even at narrow widths (`.toolbar wrap`'s
existing wrap behavior), never reverting to a vertical rail. Each
render function's own redundant hero heading ("Hướng dẫn sử dụng
MESFlow" / "Hướng dẫn ESP Kiosk" — a third, near-synonym repeat of the
Topbar's "Hướng dẫn") was also dropped per Phase 14, keeping the small
eyebrow label and (for ESP Kiosk) the real firmware/tutorial version
badges.

**GUIDANCE CHILD TABS**: `MESFlow` (video catalogue + search/category
filter), `ESP Kiosk` (firmware-version banner + video list/player) — both
functionally unchanged, verified switching correctly and surviving a full
page refresh + re-navigation.

## CONTENT HIERARCHY: TEMPLATES / BUSINESS AUDIT / PRODUCTION SCHEDULE / SYSTEM LOGS / QR PRINT / USERS / ALL REMAINING PAGES

| PAGE | OLD PRIMARY TITLE | REMOVED/MERGED HEADING | FINAL TITLE | FINAL DESCRIPTION | BUTTONS NORMALIZED |
|---|---|---|---|---|---|
| Templates | Quy trình sản xuất mẫu | "Thư viện Template" + p | Quy trình sản xuất mẫu | Chuẩn hóa Part, Operation và thời gian định mức để tái sử dụng khi lập Production Order. | — (already canonical) |
| Business Audit | Nhật ký nghiệp vụ | *(none — already fixed in prior pass)* | Nhật ký nghiệp vụ | Ai đã làm gì, với đối tượng nào, khi nào, thay đổi gì và tại sao | `.ba-card-actions` "Xem Session"/"Chi tiết thay đổi": bespoke `.btn.small` (11px font, 4px/10px padding, no shared token) → canonical `.btn.mini` (already used elsewhere, e.g. Employee report's "Xem Session") |
| Production Schedule | Tiến trình sản xuất | "Gantt + Material Flow" + p (top page-header) | Tiến trình sản xuất | Theo dõi kế hoạch, thực tế, tiến độ và dòng vật liệu giữa các Operation theo Production Order. | — (internal "Material Flow" section label kept — identifies a real distinct visualization region, not a page-title duplicate) |
| System Logs | Nhật ký ứng dụng | "Theo dõi vận hành hệ thống" + p (infrastructure-sounding wording, also a duplicate) | Nhật ký ứng dụng | Theo dõi Action Log, Error Trace và lịch sử retention của ứng dụng. | — (already canonical) |
| QR Print | Danh sách QR Code | "In tem QR" + p (as a second page title) | In tem QR | Lọc, chọn và in tem QR cho nhân viên, Production Order, Part và Operation. | — (already canonical) |
| Users | Người dùng hệ thống | "Danh sách tài khoản" + p | Người dùng hệ thống | Quản lý tài khoản, vai trò, quyền truy cập và trạng thái sử dụng. | — (already canonical) |
| Guidance | Hướng dẫn | Redundant hero `<h2>`+`<p>` on both tabs (duplicated Topbar) | Hướng dẫn | (unchanged Topbar description) | — (tab buttons now use canonical `.sl-tab`, not a bespoke rail button) |

**QR Print note**: "Danh sách QR Code" was not deleted outright — it now
labels the catalogue's `ContentPanel` (`.content-panel-head h3`), a real
subsection distinct from the page's print-action title, per the task's
own fallback instruction, without a second explanatory paragraph
repeating the PageHeader.

**Scan of all remaining pages (Section 9)**: every one of the 16
Golden-migrated pages was already normalized in the prior pass
(`UI_CONTENT_HIERARCHY_NORMALIZATION.md`) except the six above, which
this pass closes out. No further "PageHeader + same thing again" pairs
were found on Production Orders, Session Management, Session Exception
Center, Employees, Equipment, Working Calendar, Overview, Dashboard,
Production Trace, or Kiosk Management.

## BUTTON STANDARDIZATION — WHOLE APP CHECK

| PAGE | BUTTON TEXT | CURRENT CLASS (before) | CANONICAL VARIANT (after) |
|---|---|---|---|
| Business Audit | "Xem Session" / "Chi tiết thay đổi" | `.btn.small` (bespoke: 11px font, 4px/10px padding, no design token) | `.btn.mini` (canonical compact variant: 32px height, 12px font, 5px/9px padding, `var(--radius-control)`) |
| Production Orders | "+ Tạo PO từ Template" | `.btn.primary` | unchanged (already canonical) |
| Templates | "+ Tạo Template" | `.btn.primary` | unchanged (already canonical) |
| System Logs | "Làm mới" | `.btn.primary` (inside FilterBar actions) | unchanged (already canonical) |
| QR Print | "In tem đã chọn" | `.btn.primary` | unchanged (already canonical) |
| Users | "+ Tạo người dùng" | `.btn.primary` | unchanged (already canonical) |

A full sweep of every `.btn.*` compound selector in `ui.css` found no
other bespoke duplicate: `.btn.mini`'s several declarations are
cumulative refinements of the same canonical variant (base size +
media-query adjustments), `.btn.danger`'s pre-canonical definition in an
older cascade layer is already superseded (not rendered) by the later
`!important` canonical rule, `.btn.success`'s color override is likewise
pre-existing and superseded, and `.btn.primary{background:#e79b24;...}`
is an intentional themed exception scoped to a dark command banner
(`.control-command`, on `pages/po-control.js` — not one of the
Golden-migrated pages, out of this task's scope, and a legitimate
semantic departure rather than a geometry duplicate). No tab control
(`.ba-chip`, `.sl-tab`, `.pt-filter`, `.ec-tabs button`) was restyled as
a `.btn` — they remain their own defined tab controls, per the explicit
instruction not to conflate the two.

## BUTTON HIERARCHY

Verified already correct across the six audited pages, one visually
dominant Primary per action group: Production Orders (+Tạo PO từ
Template), Business Audit (Lọc), Templates (+Tạo Template — Tạo
Production Order and Công cụ read as secondary/utility), System Logs
(Làm mới), QR Print (In tem đã chọn), Users (+Tạo người dùng — Vai trò &
phân quyền / Đổi mật khẩu của tôi read as secondary/ghost-weight
utility). Danger reserved for destructive actions only (Xóa Template, Xóa
Part, Xóa Template demo).

## DUPLICATE HEADINGS

BEFORE (this pass): 6 remaining redundant heading instances (Templates,
Production Schedule, System Logs, QR Print, Users, plus Guidance's
duplicated hero title present on both its tabs).

AFTER: 0.

## BUTTON VARIANTS

BEFORE: `.btn` (canonical, 36px), `.btn.primary`, `.btn.danger`,
`.btn.mini` (32px), `.btn.tertiary`/`.btn.ghost`, `.btn.success`, and one
bespoke outlier — `.btn.small` (Business Audit only, 2 buttons).

AFTER: same canonical set; `.btn.small` removed (both its usages
converted to `.btn.mini`, its now-fully-dead CSS rule deleted).

## BUTTON HEIGHT DEVIATION

0px — measured via `getBoundingClientRect()` on Production Orders
(`#addPO`), Business Audit (`#baSearch`), Templates (`#tplNew`), System
Logs (`#slLoad`), QR Print (`#qrPrint`), Users (`#addUser`): all six
render at exactly 36px, both on the preview container and the real
deployed 71.0.0.23 build. Business Audit's now-fixed card-action buttons
measure 32px, matching every other `.btn.mini` instance in the app
exactly.

## BUTTON RADIUS DEVIATION

0px — all six measured canonical buttons render `border-radius: 5px`
(the `var(--radius-control)` token); Business Audit's `.btn.mini` also
renders 5px, identical to the canonical mini variant elsewhere.

## LEGACY CSS REMOVED

- `.guide-layout` / `.guide-subtabs` (both the base rule and its 700px
  media-query fragment) — the old vertical left-rail styling, confirmed
  0-referenced after `attachGuideTabs()` was rewritten.
- `.btn.small` — confirmed 0-referenced after both its Business Audit
  usages were converted to `.btn.mini`.

`.system-log-tabs`'s CSS was not deleted — it was generalized (paired
with the new `.guide-tabs` class in the same selector list) rather than
duplicated, per the explicit instruction not to invent another tab
visual language.

## 1920x1080

Top-350px crops captured and inspected for Guidance (both tabs),
Templates, Business Audit, Production Schedule, System Logs, QR Print,
and Users, before and after. Every page now shows: one obvious title, no
immediate near-synonym heading, filters/content beginning immediately
after the title+description (or after the sub-tab bar, for Guidance), no
unnecessary vertical whitespace from a removed redundant heading block.

## 1366x768

Guidance's sub-tab bar re-checked: 0px horizontal overflow, tabs stay a
compact horizontal pair (no reversion to stacking/rail), video grid
reflows normally.

## PLAYWRIGHT

Full 16-page × 2-viewport audit (32 captures) run twice (preview
container + real deployed 71.0.0.23 build): 32/32 clean both times. A
dedicated 22-check functional-safety suite covering Guidance (tab
switching + survives a full page refresh), Templates (tools menu),
Business Audit (category filter, actor filter, mini buttons), Production
Schedule (Gantt present, Material Flow present, reload, sticky toolbar
pinned at `top:72px` after a 600px scroll — unchanged from before this
pass), System Logs (Errors/Retention tabs, refresh), QR Print (catalogue,
selection, print wiring verified non-destructively via a stubbed
`window.print`), and Users (list, search) — 22/22 pass, both times.
General 12-check regression suite: 12/12 pass, both times. `pytest`:
7/7 passed, both times.

## PAGE ERRORS

None.

## CONSOLE ERRORS

None.

## OVERFLOW

None — 0px on every checked page at both viewports.

## LOCAL BUILD

`scripts/build-release.sh --bump` → `IMAGE RELEASE PASS`, version
71.0.0.23, schema `0037_v72_audit_operations_separation`, package
`artifacts/releases/71.0.0.23/MESFlow_71.0.0.23.deploy.zip`.

## LOCAL DEPLOY

Deploy Agent `POST /agent/api/release-manager/deploy-local
{"version":"71.0.0.23"}` → job `success`. Steps: backup → stage → install
→ restart ("MES Docker stack started; PostgreSQL data preserved") →
health ("Version 71.0.0.23 and health verified") → rollback skipped (not
required). `from_version: 71.0.0.22`.

## LOCAL HEALTH

`GET /api/system/health` → `{"ok": true, "status": "healthy", "version":
"71.0.0.23", "postgres_version": "17.10", "schema_version": "72.0.0.0"}`.

POSTGRES RESTARTED: NO
PRODUCTION TEST TOUCHED: NO
PRODUCTION TOUCHED: NO
