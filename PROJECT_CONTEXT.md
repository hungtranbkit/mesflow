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

## Current state (2026-09-29 07:45 ICT)

- main = `5473c8a` (71.0.0.378) + this handoff commit. Kiosk hotfix pass 1
  (`a290681`/`987d01b`, 377) and pass 2 (`7bcfa31`/`5473c8a`, 378) are both
  on main.
- DEV runs `mesflow-app:dev-kioskfix-37b1f79` (`.env` pinned). `37b1f79` is a
  LOCAL, unpushed integration merge = refactor `57a71d8` (UI P3) + main
  `5473c8a`; local tag `dev-image/kioskfix-37b1f79`. `/api/system/ready` →
  71.0.0.378, commit 37b1f79, DEV, migration 0054.
- The refactor line still lacks both kiosk fixes: merge main into
  `refactor/ui-consolidation-20260928` before its next DEV deploy, or DEV
  regresses (resolve PROJECT_CONTEXT.md add/add by concatenating).

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
