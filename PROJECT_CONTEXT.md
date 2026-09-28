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
  integration of `refactor/ui-consolidation-20260928` + whatever hotfix.
- "production test" = https://mesflow.net (VPS). Not deployed by the hotfix
  below; still 71.0.0.376.
- Version bump on main: `scripts/bump-version.sh <X.Y.Z.W>` then
  `scripts/check-version-sync.sh`. Main hotfixes land as a fix commit + a
  `chore(release): bump …` commit.

## Recent handoff — kiosk demo scan P0 hotfix (2026-09-29)

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
