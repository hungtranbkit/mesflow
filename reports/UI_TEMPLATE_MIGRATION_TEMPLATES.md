# UI Template Migration — Templates Module

VERSION BEFORE: 71.0.0.20
VERSION AFTER: 71.0.0.21

Migrates the Templates module (Thư viện Template) onto the same Golden
Foundation contract established in 71.0.0.17/.18/.19/.20, treated as the
explicit hybrid archetype the task called for: LIST (master) + DETAIL/EDITOR
(detail), rendered together on one page (Templates has always been a
side-by-side master-detail screen, not a separate list route + separate
editor route — the migration preserves that single-page shape while
normalizing both halves onto canonical primitives). This is a UI
structure/consistency migration only: no template/list/create/clone/edit/
save/delete/Part/Operation/drawing/permission/API/navigation behavior was
changed.

## TEMPLATE LIST

**BEFORE**: `<section class="template-command panel"><div><h2>Thư viện
Template</h2><p>…</p></div><div class="template-command-actions">` +Tạo
Template / Tạo Production Order / `<details class="template-tools">`Công
cụ`</details></div></section><section class="template-old-grid"><aside
class="template-old-list-panel"><div class="template-list-head"><div>
<h2>Danh sách Template</h2><span id="tplCount">…</span></div><label
for="tplSearch">…</label><input id="tplSearch" class="template-old-search">
</div><div id="tplList" class="template-old-list">…</div></aside>…`

**AFTER**: `.page-shell > .page-header (title + description +
.page-header-actions: +Tạo Template / Tạo Production Order / Công cụ) >
MFUI.filterBar({content: Tìm nhanh}) > .template-old-grid > aside.content-panel
.template-old-list-panel (head: "Danh sách Template" + live "N mẫu" count,
body: #tplList.template-old-list) + article#tplEditor…`. The search field
moved out of the list panel's own head into a canonical page-level
FilterBar (same pattern as every other List page in this migration series);
the list panel itself gained `.content-panel`/`.content-panel-head`/
`.content-panel-body` for structural consistency while keeping its own
`.template-old-list-panel` class for its specialized sticky positioning
(`position:sticky;top:88px;max-height:calc(100vh - 110px)`) and internal
scroll region (`.template-old-list{max-height:calc(100vh - 230px);
overflow:auto}`) — both untouched.

## TEMPLATE EDITOR

**BEFORE/AFTER** (unchanged structure, by design): `<article id="tplEditor"
class="panel template-old-editor">` stays a plain `.panel` — its entire
content, including its own head, is written by `drawTemplateOldEditor()`
in a single `innerHTML=` call on every redraw (same "JS-embedded dynamic
panel header" pattern established for `#ovRepairPlan`/`#kmDetail` in Batch
B, and measured there to share identical outer box geometry with
`.content-panel`). Editor hierarchy, unchanged and already-correct against
the task's requirement ("PageHeader: Back, template name/code, supporting
metadata, Save/primary actions… do not bury Save/primary actions inside
lower sub-panels"): `.panel-head.template-old-head` (template code·name +
description, `.template-editor-actions`: Lưu thay đổi (primary) + Xóa
Template (danger) — both already at the very top, never buried) → summary/
meta fields (`.template-old-form`: Mã/Tên/Sản phẩm/Phiên bản/Cho phép dùng)
→ `.template-old-section` ("Cấu trúc sản xuất" + "+ Thêm Part") → nested
Part boxes (`.template-old-part`, each with its own head/drawing-upload row/
Operation table). Templates has no separate "Back" affordance because the
list stays visible alongside the editor at all times (master-detail, not
full-page navigation) — no synthetic Back button was added, since forcing
one in would contradict "do not force editor content into a simple
list-page structure."

## GOLDEN PRIMITIVES USED

`.page-shell`, `.page-header`/`.page-header-actions`, `MFUI.filterBar()`,
`.content-panel`/`.content-panel-head`/`.content-panel-body` (list panel
only — the editor stays `.panel`, matching the established
identical-geometry precedent). No new header, toolbar, panel, button
family, or spacing scale was introduced.

## SPECIALIZED EDITOR UI PRESERVED

Part boxes (`.template-old-part`, code/name fields, drawing upload/replace/
remove), Operation rows (`.template-old-op-row`: code/name/equipment/cycle-
time value+unit/remove-icon-button/material-flow sub-row with source-OP
select + defect-consumption checkbox), `normalizeOldTree()`/
`applyOldParts()`/`bindOldEditorEvents()` state-sync logic, the "Công cụ"
tools dropdown (Nhập từ Excel / Xuất Excel / Nhân bản Template / Nạp·Xóa dữ
liệu mẫu), `saveTemplateOld()`/`cloneTemplateOld()`/`removeTemplate()`/
`importTemplateExcel()`/`exportTemplateExcel()` — none of this logic was
touched.

## LEGACY CSS REMOVED

All removals individually confirmed 0-referenced in `app.js`/`pages/*.js`
before deletion:

- `.template-command`, `.template-command-actions` (+ their 900px/600px
  media-query fragments) — dead, replaced by canonical `.page-shell`/
  `.page-header`/`.page-header-actions`.
- `.template-list-head` (+4 descendant rules), `.template-old-search` (both
  cascade layers — an older definition at the top of the file and the
  active one further down) — dead, search moved into FilterBar.
- `.template-old-toolbar` — dead everywhere it appeared: standalone rule,
  its 6 appearances inside shared toolbar-selector lists (the same
  `.toolbar,…,.panel-toolbar{…}` family cleaned for `.qr-toolbar` in Batch
  C1), and both copies of the control-height-unification rule.
- `.template-old-layout` — dead (2 fragments).
- Confirmed-dead pre-existing debt unrelated to this migration but
  matching the task's explicit `.template-*` audit scope: `.template-grid`,
  `.template-card`/`.template-card-head`/`.template-card h3`/`.template-card
  b`, `.template-meta`, `.template-actions`, `.template-builder-backdrop`,
  `.template-builder{width:…}`, `.template-create-panel` (+3 sub-rules) —
  remnants of an even earlier Templates UI generation, already fully
  replaced before this session; left every interleaved live rule in the
  same blocks untouched (`.btn.success`, `.check-label`, `.builder-*`
  survived — `.builder-*` is separately-dead pre-existing debt outside the
  `.template-*` pattern this task scoped, left alone per scope discipline).

## LIVE CSS PRESERVED

`.template-old-grid`, `.template-old-list-panel` (sticky/scroll math),
`.template-old-list`, `.template-old-card` + `.active`/`:hover` states,
`.template-status` (+`.active`/`.inactive`), `.template-old-editor`,
`.template-old-head`, `.template-old-form` + label styling, `.template-old-
check`, `.template-old-section`, `.template-old-part` + `-head` + `-title`,
`.template-part-drawing` + `-number`, `.template-drawing-link`,
`.template-old-op-table` + `-header` + `-row` (+ `.no-order`) + `-actions`,
`.template-op-remove`, `.template-flow-row`, `.template-editor-actions`,
`.template-tools` (dropdown positioning/backdrop), and every associated
responsive (1100px/1050px/900px/760px/600px) media-query fragment — none
of these were modified beyond the targeted control-height fix below.

## ACTION HIERARCHY

Unchanged, already correct against the task's spec: **Primary** — "+ Tạo
Template" and "Lưu thay đổi" (`.btn.primary`). **Secondary/Utility** —
"Tạo Production Order" (distinct call-to-action color, `.btn.success`),
"Công cụ" dropdown bundling Nhập/Xuất Excel, Nhân bản Template, Nạp/Xóa dữ
liệu mẫu (kept bundled — restructuring which actions live inside vs.
outside the dropdown is a behavior change, not a structural-consistency
one, and was out of scope). **Danger** — "Xóa Template" / "Xóa Part" /
per-Operation remove icon (`.btn.danger`/`.template-op-remove`), visually
distinct (red outline) from primary/secondary at every level.

## FORM CONSISTENCY

`.template-old-form input`, `.template-old-part input`, `.template-old-op-
row input,select` previously rendered at ~40–42px (10px vertical padding)
despite the shared canonical `input,select,textarea{min-height:36px}`
rule, because their own non-`!important` `padding:10px 11px` won on
specificity over the bare global selector. Fixed by changing that padding
to `7px 10px` (both cascade layers) so every form control in the editor —
summary/meta fields, Part fields, Operation fields — now renders at the
canonical 36px, confirmed by direct measurement (see CONTROL HEIGHTS).
Border-radius was already canonical pre-migration (the global
`border-radius:var(--radius-control)!important` rule already won
regardless of any page-specific value). Labels, vertical gaps, and
focus-visible treatment were already consistent with the rest of the app
and were not touched. File-upload button ("Đính kèm bản vẽ") kept its
standard `.btn` sizing; the cycle-time value+unit compact control keeps
its specialized combined width.

## EDGE ALIGNMENT

`.page-shell` left/right edges measured against Golden Production Orders:

| Viewport | Left / Right | Diff vs Golden |
|---|---|---|
| 1920×1080 | 272 / 1896 | 0px |
| 1366×768 | 248 / 1346 | 0px |

## CONTROL HEIGHTS

FilterBar search input: 36px. `.template-old-form` fields: 36px.
`.template-old-part` fields: 36px. `.template-old-op-row` fields: ~36px
(36.02px, sub-pixel from line-height rounding). All measured at both
viewports, before and after deploy — identical.

## PANEL GEOMETRY

`.content-panel` (list side) and `.panel.template-old-editor` (editor
side) share the canonical border/radius/background/shadow tokens (already
enforced pre-migration by the shared `.panel,.card,…,.template-old-list-
panel,.template-old-part,…{border-radius:var(--radius-panel)!important}`
rule) — no visible seam between the two halves of the master-detail grid
and the rest of the Golden UI. No clipped Part/Operation rows; the list
panel's own internal scroll region continues to work exactly as before.

## 1920x1080

BEFORE/AFTER screenshots captured and inspected. AFTER reads cleaner: a
single canonical page-header + filter row replaces the old ad-hoc
`.template-command` bar, the master-detail grid is unchanged in
proportion/density, Save/Delete remain immediately visible at the top of
the editor, and every text field in the editor is visibly shorter (36px)
and more consistent than before.

## 1366x768

Same layout holds — two-column grid intact (list ~330px fixed + editor
flexible), FilterBar wraps correctly, no horizontal overflow, editor
actions (Lưu thay đổi/Xóa Template) remain reachable without scrolling
past the fold on template selection, nested Part/Operation tables do not
clip.

## FUNCTIONAL SMOKE

11/11 checks, run twice (live-preview container + real deployed 71.0.0.21
build), all passing both times, using existing local demo data
(non-destructive throughout):

- Templates list loads (4 demo templates present).
- Search/filter narrows the list to the matching template.
- Selecting a different template updates `.active` state and the editor
  fields.
- Editor loads (`#tplCode` etc. populated).
- Parts section present; Operations section present (21 operation rows
  across the demo template's parts).
- Re-selecting the first template correctly reloads its code into the
  editor (the master-detail equivalent of "back navigation" for this
  single-page hybrid — no separate route to return from).
- Create UI opens (`#tplNew` resets the editor to a blank `TPL-` draft).
- "Công cụ" tools menu (Clone/Import/Export/Seed/Delete-demo) opens.
- Save wiring verified non-destructively: the PATCH/tree-PUT request was
  intercepted and aborted before reaching the server, confirming the
  button correctly triggers the save call without ever mutating real
  data.
- Delete confirmation opens (native `confirm()` dialog fires) and was
  dismissed, not accepted — no template was deleted.

## CSS VALIDATION

Brace balance: 2881 `{` / 2881 `}` (matched), paren balance 1272/1272
(matched); custom string/comment-aware depth scanner: final nesting depth
0 (balanced); `git diff --check`: clean, no whitespace errors.

## JS CHECK

`node --check app.js` — OK (only `app.js` was touched; `pages/*.js` files
were not modified for this task).

## PYTEST

`pytest tests/test_v71_ui_foundation.py tests/test_web_ui.py` → 7 passed
(run twice: preview container and real deployed 71.0.0.21 build).

## FULL UI AUDIT

Full 16-page × 2-viewport Playwright audit (32 captures), run twice: 32/32
clean both times — 0 overflowing, 0 console/request errors. General
12-check functional regression suite (login, PO nav/back, session
filters, exception tabs/drawer, **templates-tools-toggle** — a
pre-existing check in this suite, confirming the Công cụ dropdown still
works — 0 console errors, 0 failed requests): 12/12 pass both times.

## LOCAL BUILD

`scripts/build-release.sh --bump` → `IMAGE RELEASE PASS`, version
71.0.0.21, schema `0037_v72_audit_operations_separation`, package
`artifacts/releases/71.0.0.21/MESFlow_71.0.0.21.deploy.zip`.

## LOCAL DEPLOY

Deploy Agent `POST /agent/api/release-manager/deploy-local
{"version":"71.0.0.21"}` → job `success`. Steps: backup → stage → install
→ restart ("MES Docker stack started; PostgreSQL data preserved") →
health ("Version 71.0.0.21 and health verified") → rollback skipped (not
required). `from_version: 71.0.0.20`.

## LOCAL HEALTH

`GET /api/system/health` → `{"ok": true, "status": "healthy", "version":
"71.0.0.21", "postgres_version": "17.10", "schema_version": "72.0.0.0"}`.

POSTGRES RESTARTED: NO
PRODUCTION TEST TOUCHED: NO
PRODUCTION TOUCHED: NO
