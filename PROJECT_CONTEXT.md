# PROJECT_CONTEXT.md

Living handoff for the MESFlow app repo (`hungtranbkit/mesflow`). Read after
`AGENTS.md` / `PROJECT.yaml`. Code, tests, git and the running stacks win over
anything stale here; fix this file when they disagree.

> Note: the long-lived UI refactor line `refactor/ui-consolidation-20260928`
> has its OWN `PROJECT_CONTEXT.md` (P0–P3 handoff). This file was created on
> main by the kiosk hotfix below. When main is next merged into that line,
> keep both sections (add/add conflict — concatenate, don't pick one).

## Environments (as of 2026-09-29)

- DEV = https://dev.mesflow.net → cloudflared `kiosk-local-test` →
  `127.0.0.1:8310` → container `mesflow-dev-app` (compose project
  `mesflow-dev`, `/home/dell/workspace/mesflow-dev/compose.dev.yml`, image
  pinned in `/home/dell/workspace/mesflow-dev/.env` `MESFLOW_IMAGE`).
  DEV currently runs the UI refactor line, so DEV images are built from an
  integration of `refactor/ui-consolidation-20260928` + main (see Current
  state). Never deploy a plain main image to DEV; it would wipe UI P0–P3.
- "production test" = https://mesflow.net (VPS). Not deployed by the hotfix
  below; still 71.0.0.376.
- Version bump on main: `scripts/bump-version.sh <X.Y.Z.W>` then
  `scripts/check-version-sync.sh`. Main hotfixes land as a fix commit + a
  `chore(release): bump …` commit.

## Current state (2026-09-29, after the productivity one-file export + print hotfix)

- main = 71.0.0.380: kiosk hotfixes 377/378, the 379 detail export, and
  380 (`2252e57` feature, `255b61f` bump), which REPLACES 379's export
  menu with one-file Excel + print. Handoff below.
- Refactor line `refactor/ui-consolidation-20260928` = `133cb22`: merge of
  main `685de6d` (all fixes through 380) into P3 `57a71d8`. It no longer
  lacks any main fix.
- DEV runs `mesflow-app:dev-380-133cb22` (built from the integration worktree;
  `.env` pinned, previous `mesflow-app:dev-kioskfix-37b1f79`, kept for
  rollback). `/api/system/ready` → 71.0.0.380, commit 133cb22, DEV.
  mesflow.net (PRODUCTION_TEST) untouched: 71.0.0.376.

## Recent handoff — Năng suất: one-file Excel + "In" (2026-09-29, 71.0.0.380)

Supersedes the 379 "Chi tiết từng nhân viên" menu (`80c6ca0`/`c0b988e`, kept
in history). The user changed the requirement: one Excel button, one file,
plus printing.

**Behavior.**
- Screen buttons: exactly "Xuất Excel" and "In" (+ the existing "Làm mới").
  There is no dropdown and no `mode` parameter any more.
- "Xuất Excel" → `GET /api/reports/employee-productivity/export.xlsx`
  (`from,to,search,department,team,employee_id,sort,dir`) → ONE workbook:
  - sheet 1 "Tổng hợp": the summary, written by the same
    `_write_summary_sheet()` as before. Verified cell/format/style-identical
    to main's pre-hotfix summary export in 5 filter cases; only the sheet
    title changed ("Năng suất nhân viên" → "Tổng hợp").
  - one sheet per employee in the filtered list, in summary order, one row
    per session. Columns: STT, Mã NV, Tên NV, Ngày, PO, Part, Mã OP,
    Operation, Bắt đầu, Kết thúc, Thời gian thực tế, Sản lượng đạt, Lỗi,
    Định mức (giây/SP), Thời gian định mức, % năng suất, Trạng thái / ghi chú,
    NV xác nhận (signature, blank), Mã phiên. Header row 4, freeze A5,
    auto-filter, date/`[h]:mm:ss`/`0.0%` formats, widths, A4 landscape.
  - `employee_id` given → Tổng hợp + that employee's sheet only.
  - sheet names (`employee_sheet_names`): "<Mã NV> <Tên>", `[]:*?/\`
    replaced, <=31 chars, leading/trailing `'` stripped, never
    "Tổng hợp"/"History", case-insensitive dedupe with " (2)", " (3)"…
- "In" → dialog "In toàn bộ" / "In theo nhân viên" (choices = the rows the
  table currently lists). It opens `GET /api/reports/employee-productivity/
  print?<same filters>[&employee_id]&autoprint=1` in a NEW tab
  (`window.open`), so the app never navigates away. The template is
  `templates/employee_productivity_print.html`:
  - A4 landscape, `thead` repeats per page, screen-only toolbar (Đóng / In).
  - Filter/date context and "In lúc … bởi …".
  - The summary, then each employee's section with a page break before it
    (no page break for a single employee), plus signature lines.
- Filters: this screen has date range, search and department. There are no
  PO/Part/Operation filters on it. `team`/`employee_id` pass through.
  Excel and print both go through `web/productivity_export.py`
  (`parse_filters` → `load_export_data`).
- Access: both routes are `@login_required` (same as before; anonymous 401).
  `employee_id` outside the current filters → 404; a non-numeric one → 400.
- Formula: unchanged. Session % = `_SESSION_COMPLETION_PERCENT_SQL`
  (expected ÷ actual). The employee % on "Tổng hợp" = AVG of the non-empty
  session % on their sheet. Scope = `_productivity_scope()` (shared).
- Queries: 2 per export/print (`employee_productivity` +
  `employee_productivity_sessions`), grouped in memory. No N+1.

**Files.** `web/productivity_export.py` (new), `web/productivity_excel.py`
(one-file builder, sheet names; the old summary-only and 379 builders
removed), `web/analytics.py` (export + print routes),
`templates/employee_productivity_print.html` (new),
`static/pages/employee-productivity.js` (buttons + print dialog),
`static/ui.css` (`.ep-print-options`),
`tests/test_employee_productivity_detail_export.py` (rewritten),
`tests/test_employee_productivity_excel_export.py` (reads "Tổng hợp").
379's `_productivity_scope` / `employee_productivity_sessions` are reused
unchanged.

**Tests.**
- Productivity tests: 30 passed. They cover:
  - one/multiple employees, the same OP twice, and filters deciding sheets;
  - detail mapping/formats and AVG reconciliation;
  - summary semantics and exactly-2-queries;
  - long/invalid/duplicate/reserved sheet names;
  - Flask test client: export sheets, print all (2 page-breaks), print
    one, 404 outside filters, 400 bad id, 401 anonymous;
  - frontend contract.
- Static suite (`mesflow-aw0926-tests`, `--ignore=tests/integration
  --ignore=tests/e2e`, `-m "not postgres and not integration and not
  slow"`): hotfix 1218 passed / 2 failed / 13 skipped vs main `ea0c3cc`
  1210 / 2 / 13. The same 2 baseline-only failures (`autologin_guard` ×2),
  no new ones.
- Browser (preview container on the DEV DB, Playwright image,
  `--network host`) at 1366×768 and 390×844:
  - labels exactly "Xuất Excel"/"In", no menu;
  - one download with sheets `Tổng hợp`, `NV001 Huỳnh Thị Mơ`,
    `DEV-001 Tho Dev` (3 and 7 session rows, freeze A5, auto-filter);
  - print dialog lists the 2 filtered employees;
  - print-all tab: `window.print()` called, 2 employee sections,
    2 page-breaks, PDF render = 3 A4 pages;
  - print-one tab: only employee 28, title "BÁO CÁO NĂNG SUẤT · DEV-001 ·
    Tho Dev";
  - app tab URL unchanged, 0 px body overflow, no JS errors.

**P3 integration + DEV.**
- Child branch `ui-refactor/merge-main-380-20260929` merged main `685de6d`
  into refactor `57a71d8` → `133cb22`; the integration branch was
  fast-forwarded and both were pushed.
- Conflicts:
  - `pages/employee-productivity.js`: kept the P3 layout. The action row
    is Làm mới · In · Xuất Excel (the single `.primary`). Export/print code
    comes from main.
  - `PROJECT_CONTEXT.md` add/add: concatenated, main first, then P0–P3.
  - Tests: `test_ui_productivity_consolidation` checks the shared
    `reportQuery()`; the frontend test accepts the P3 `.primary` export
    button.
- Merged-tree static suite: 1244 passed / 2 failed / 51 skipped (the same 2
  `autologin_guard` baseline failures). The P3 base `57a71d8` was 1204 / 3;
  its third failure is fixed by main.
- Browser on a merge preview AND on public https://dev.mesflow.net after
  deploy, P3 mode (`ui_refactor=1`) and legacy mode, 1366×768 + 390×844:
  - "Xuất Excel"/"In" labels, no menu;
  - one workbook `Tổng hợp` + `NV001 Huỳnh Thị Mơ` (3 rows) +
    `DEV-001 Tho Dev` (7 rows);
  - print-all → `window.print()` called, 2 sections, 2 page-breaks;
  - print-one → only employee 28;
  - app URL unchanged, 0 px overflow, no JS errors.
- Anonymous print → 401. `/kiosk` 200 with the 377/378 kiosk code present.

## (Superseded) Excel năng suất: "Chi tiết từng nhân viên" menu (71.0.0.379)

Replaced by 380 above. It added `ReportRepository._productivity_scope()` and
`employee_productivity_sessions()` (one query, one row per session), which
380 still uses. The export menu and `mode=detail` it added are gone. Its
live-DB check (NV001 3 sessions / DEV-001 7, % 267.79 = summary) still
holds for the shared query.

## Recent handoff — kiosk pass 2: start refusals were masked (2026-09-29)

**Live DEV root cause (reproduced ~06:00 ICT on the pass-1 build d144edd).**
Pass 1 was live and correct: demo employee scan 200 → OP scan 200 →
`/start {"employee_id":28,"operation_id":4}`. DEV refused it:
`409 {"error_code":"SES-409","message":"Ngoài ca làm việc. …","action":"Quét
lại thẻ nhân viên…"}`. DEV shifts: DAY 08:00–17:00, NIGHT 18:00–00:00, Mon–Sat;
starts allowed 30 min early (`MESFLOW_SHIFT_START_EARLY_TOLERANCE_MINUTES`).
The refusal was correct, but the backend labelled it a session conflict with
"re-scan the badge" advice, and `kiosk.js` `workerError()` turned every 409
into "Công đoạn này hiện không thể bắt đầu". To the user it looked exactly
like the old SCN-003 bug. The user's own tab (WEB-621f8a6f, already on 377)
was sitting on that error.

**Fix.**
- `app/mesflow/web/kiosk.py`: `OutsideShiftError(ConflictError)` →
  `SHF-409` / `reason=OUTSIDE_SHIFT`, message lists the configured shift
  hours. `_conflict_reason()` gives every 409 a `reason` + specific code:
  PO-001 PO_NOT_STARTED, OP-409 OPERATION_CLOSED/REWORK_BENCH/NOT_READY,
  DEP-409 DEPENDENCY, QTY-409 INPUT_QTY, SES-409 SESSION_OPEN /
  SESSION_CONFLICT (fallback). The "đang mở Operation này" check must stay
  BEFORE the QTY substring test (its text contains "sản lượng"). `/start`
  "employee inactive or missing" → 400 `EMP-001` / `EMPLOYEE_INACTIVE`
  (Vietnamese). HTTP statuses unchanged; `reason` is a new field.
- `app/mesflow/web/static/kiosk.js`: with `reason` on a 4xx (not 401/403),
  the screen shows the server message/action; `kiosk_status.last_error`
  becomes `<CODE> <REASON>: <message>`. No `reason` (old server) → old
  generic text.
- Contract change: the out-of-shift code went SES-409 → SHF-409, and a
  PO-not-started START refusal went SES-409 → PO-001 (same code the scan
  path already used). ESP / kiosk v2 endpoints are untouched.

**Tests.**
- New `tests/test_kiosk_refusal_reasons.py`; e2e D6–D8 in
  `tests/e2e/kiosk-demo-employee-then-op.spec.js`. e2e 19/19 on the fix;
  D6/D7 fail on pass-1 main, D8 (old-server compat) passes on both.
- `test_a_programming_bug_becomes_500_and_is_logged` now pins clock + shifts.
  It used to measure the shift gate (409 out of hours, ShiftConfigDegraded
  without a DB), which kept main CI red and hid the integration step.
- Local static suite: 1200 passed, 2 failed (`autologin_guard` ×2 fail only
  in the local container env; they pass in GitHub CI).
- GitHub CI on 5473c8a: first run at 06:20 ICT had 7 `test_kiosk_scan_to_board`
  + 1 `test_p0_scan_auth` failures, all 409 OUTSIDE_SHIFT. Integration tests
  hit the REAL shift gate with no calendar pinning, so they are
  time-of-day dependent (pre-existing; they were hidden while the unit step
  failed). Re-run at 07:34 ICT: all of those pass; 616 passed, 1 failed:
  `test_rework_overview_rollup` (`progress_percent` None). That one also
  fails on pre-hotfix code (throwaway probe branch on 8aa78a6, CI run
  36504419675, now deleted), so it is pre-existing and unrelated.

**Live DEV verification (image 37b1f79).**
- 06:15 ICT (outside shift): `/start` → `409 SHF-409 OUTSIDE_SHIFT "Ngoài ca
  làm việc. Không thể bắt đầu phiên mới (giờ ca: Ca ngày 08:00–17:00 · Ca tối
  18:00–00:00)."`, shown on screen as that exact message.
- 07:31–07:33 ICT (inside the early window): demo employee → demo OP →
  `/start` **201** → screen "started", at 1366×768 and 390×844. Each test
  session was closed through the kiosk (re-scan badge → 0/0 → confirm):
  DEV work_sessions #8, #9, #10 for DEV-001 / op 4, all CLOSED with 0 qty.
- mesflow.net / production not touched (still 71.0.0.376).

**Open items.**
- Integration tests that call `/start` need a pinned shift (e.g. an
  all-day fixture shift) or CI goes red outside 07:30–17:00 / 17:30–00:00
  Mon–Sat. Adding a shift changes shift attribution, so do it with care.
- `test_rework_overview_rollup` progress_percent None: pre-existing, not
  investigated.
- A kiosk tab with the demo panel open never auto-reloads to a new version
  (`isIdleForReload` requires the panel closed). Demo users can stay on old
  JS after a deploy until they close the panel or refresh.

## Recent handoff — kiosk demo scan P0 hotfix (2026-09-29, pass 1)

**Bug.** On `/kiosk` with the "Mô phỏng quét QR" panel open: demo employee →
demo OP (server rejects, e.g. SES-409 "Ngoài ca làm việc") → demo OP again →
SCN-003 "Hãy quét thẻ nhân viên trước / Quét thẻ nhân viên trước, sau đó mới
quét Operation." Reproduced live on DEV with Playwright.

**Root cause** (`app/mesflow/web/static/kiosk.js`, `scan()`): while the panel
is open, result screens `error`/`started` stay pinned (scheduleReset skips
them; `error` never auto-returns). A scan on a terminal screen did
`reset(); setTimeout(() => scan(qr), 50)` — `reset()` wiped `employee` /
`openSessions`, the re-scan ran in `ready`, so an OP QR always hit SCN-003.
The re-scan also POSTed `/scan` twice and left a `ready` gap the next click
could fall into.

**Fix.** `scan(qr, {source})`; demo panel buttons and
`MESFlowKioskDemo.scanEmployee/scanOperation` pass `{source:'demo'}`. On a
terminal screen a demo scan reuses the result it already fetched:
employee → reset + handle as `ready`; Operation with an identified employee →
continue the operation branch with the same employee/open sessions;
Operation with nobody → SCN-003 as before. Dispatch uses a local `flow`
(seeded from `state`). Real scanner input, camera, and
`MESFlowKioskDemo.scan(qr)` keep `source='scanner'` → old reset+rescan path,
intentionally unchanged (at a standalone station an OP scanned after a
result screen may belong to the next worker, so they must badge first).
No backend/API/schema change.

**Tests.**
- New `tests/e2e/kiosk-demo-employee-then-op.spec.js` (D1–D5, mocked API).
  Run against a tiny Jinja+static server + `mesflow-test-playwright` image
  on `--network host`: fixed code 16/16 (with existing
  `kiosk-multi-session` + `kiosk-result-auto-return` specs); unfixed main
  fails D1, D2, D3; D4/D5 (unchanged behaviour) pass on both.
- New `tests/test_kiosk_demo_scan_keeps_employee_context.py` (source contract).
- `tests/test_web_kiosk_v6564.py` token updated `state === 'operation'` →
  `flow === 'operation'` (same intent).
- Full static suite in `mesflow-aw0926-tests` (`--ignore=tests/integration
  --ignore=tests/e2e`): 1183 passed, 13 skipped, 3 failed = known baseline
  (autologin_guard ×2, kiosk_errors_are_logged). `tests/integration` not run
  (needs live Postgres).

**Release / deploy.**
- Branch `hotfix/kiosk-demo-scan-20260929`: `a290681` fix, `987d01b` bump to
  71.0.0.377, plus this handoff commit; fast-forwarded into `main`.
- DEV only: image `mesflow-app:dev-kioskfix-d144edd` built from a local,
  unpushed integration merge `d144edd` = refactor `57a71d8` (P3) + hotfix.
  `.env` pinned to it (previous: `mesflow-app:ui-p3-c78f040`).
  `/api/system/ready` → 71.0.0.377, commit d144edd, DEV, migration 0054.
- Live DEV browser check (1366×768 and 390×844): demo NV→OP→OP now retries
  `/start` with the same employee (`[[28,4],[28,4]]`, 3 `/scan` calls, no
  SCN-003); reset → demo OP → SCN-003 with no `/start`; real-scanner hook
  after error still SCN-003. The remaining SES-409 is the genuine backend
  out-of-shift rule (checked ~05:30 ICT), not this bug.

**Open items / next actions.**
- The UI refactor line does not yet contain this fix. Merge `main` into
  `refactor/ui-consolidation-20260928` (VERSION goes to 377; resolve the
  PROJECT_CONTEXT.md add/add conflict by concatenating). Until then, any DEV
  redeploy from the refactor line alone REGRESSES the kiosk bug.
- Pre-existing UX gap (not changed): kiosk `workerError()` maps every 409 to
  "Công đoạn này hiện không thể bắt đầu", hiding backend reasons like
  "Ngoài ca làm việc".
- mesflow.net / production were not touched; promote 377 only with explicit
  approval.
