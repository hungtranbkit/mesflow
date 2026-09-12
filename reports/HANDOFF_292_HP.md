# Handoff — MESFlow integration lane, HP (2026-09-12)

## BUILT & GATED, **NOT DEPLOYED**: 71.0.0.292

Deploy to TEST (https://mesflow.net) is **blocked on HP** — credentials only
exist on Dell. Everything up to and including the release build is done.
mesflow.net is still serving 291 (verified live). Real production was never
touched.

## What is in 292 (one P0 hotfix on 291 / d8f971d)

Kiosk web double-tap → "XÁC NHẬN 0/0" (REQ-KIOSK-013, new).

- Lane commit `5267a33`, merge commit `5e3c12f`, release commit `74e997e`.
- Measured cause, not guessed: one tap = one click (checked), and
  `touch-action:manipulation` was already set, so no ghost clicks. The real
  cause is that the "advance" control of consecutive screens **overlaps** at
  one coordinate — Pixel 7 x≈306: `good-next` y 396–444, `defect-next`
  y 418–466, `rework-next` y 395–443, `finish-confirm-ok` y 382–458 — combined
  with the default `0` in a quantity box being read as a real answer. Three
  taps at one unmoving point submitted `good=0, defect=0`.
- Fix is state + layout, no timer, no swallowed tap: `qtyTouched` (a default
  `0` is not an answer; every input path marks it, including soft
  keyboard/Gboard/IME via `beforeinput`/`input`), plus the confirm row pinned
  to the bottom so XÁC NHẬN no longer intersects any TIẾP TỤC band.
- ESP parity untouched: `*` left / `#` right, NG=0 skips ASK_REWORK, key
  meanings and payload unchanged. The one deliberate web-only divergence
  (web requires an explicit digit) is written up in `KIOSK_ESP_PARITY.md` §2.4.
- **No new migration** — `migration_head` stays `0050_user_session_epoch`,
  same as 290/291.

## Gate (on the exact merged tree, `--retries=0`)

- pytest: **140 unit + 590 static + 44 behavioral + 502 integration =
  1276 passed**, 21 skipped, 1 xfailed (the pre-existing `rework_qty`
  two-meaning bug, Rework lane, already documented), **0 failed**.
- Playwright full: **459 passed, 1 failed, 4 skipped** of 464, `--retries=0`.
  - The 1 failure is `network-resilience.spec.js:79` "mất mạng thật" — the
    same ambient flake Dell identified for 291. **Isolated rerun
    `--retries=0`: 9/9 passed (56.2s).** Unrelated to Kiosk.
  - `mesflow.spec.js` "seven runtime videos" passes here — the ESP tutorial
    fixture was generated first (HP has no ffmpeg/passwordless sudo, so it was
    built through `Dockerfile.esp-tutorial-fixture`, not the bare script).
- Focused Kiosk: **68 Playwright** (double-tap, esp-parity, quantity-entry-p0,
  setup-flow, po-focus, control-contrast, daily-dashboard-kiosk) +
  **186 pytest** (`-k "kiosk or confirm_slot"`) — all green.
- Negative proof for the hotfix was done on the lane before merge: removing
  the state guard reddens 4 tests, removing the layout pin reddens 4 more;
  restoring turns them green.

## Release artifact (built on HP, ready to ship)

- image `127.0.0.1:5000/mesflow-app:71.0.0.292`
- digest `sha256:c94697ba07495f995f85f0a3a611824c54e29b4bc7c2f6344b7d8c8614408309`
- commit `74e997e86c4b`, dirty=false, migration_revision `0050_user_session_epoch`
- manifest `release/mesflow-71.0.0.292.json`; release-build smoke (ephemeral
  Postgres + migrate + health) passed.
- NOTE: HP had no local registry — `mesflow-registry` (`registry:2`, bound to
  127.0.0.1:5000 only) was started here to hold it.

## Why the deploy did not happen (blocker, needs a human)

`scripts/deploy-remote-test.sh 71.0.0.292` → `REMOTE_TEST_TARGET_NOT_CONFIGURED`.

- `scripts/remote-test-target.env` is gitignored and exists only in Dell's
  checkout (`/home/dell/workspace/mesflow/mesflow`). It is nowhere on HP.
- HP has **no SSH private key at all** (`~/.ssh` holds only `authorized_keys`
  and `known_hosts`; no ssh-agent), so the remote TEST host is unreachable
  from here even with the hostname.

No substitute target was used, deliberately:
- `deploy.sh prodtest` points at `dell@127.0.0.1:/home/dell/deploy/mesflow-prodtest`
  — a Dell-local tier. HP has no `dell` user and no such directory.
- `deploy.sh production` is frozen and needs its own gitignored target file.
- HP's own `/opt/mesflow` + `mesflow-deploy-agent` self-report
  **`SERVER_ROLE=PRODUCTION`** (this box is `prod.mesflow.net`, currently
  71.0.0.46). Deploying 292 there would be a real-production deploy — out of
  scope and explicitly excluded.

### To finish the deploy

Either copy `scripts/remote-test-target.env` + the deploy SSH key onto HP (then
`bash scripts/deploy-remote-test.sh 71.0.0.292`), or run that same command from
Dell once it is back — the image is already built and pushed to HP's registry,
so from Dell it would need a rebuild (`bash scripts/release-build.sh` on
`74e997e`) or a transfer of the image tar.

Post-deploy verification to run: `https://mesflow.net/api/system/ready` must
report version `71.0.0.292`, commit `74e997e86c4b`, `server_role
PRODUCTION_TEST`, `migration_head 0050_user_session_epoch`; then smoke the
Kiosk — open `/kiosk`, scan a badge with an open session, tap TIẾP TỤC three
times without entering anything, and confirm it stays on SẢN PHẨM ĐẠT with the
`Nhập số sản phẩm đạt — bấm 0 nếu không có` line and nothing submitted.

## Queue / known conflicts

- `origin/hp2/kiosk-demo-po-filter` conflicts on `kiosk.js`, `kiosk.css` and
  both REQ docs — **pre-existing**: it conflicts identically against 291
  (`d8f971d`, 4 conflicts) with none of 292's changes present. It is based on
  `0ea03df` and needs a rebase. Kept separate; it did not block this release.
- `origin/hp/mesflow-kiosk-scan-audit`: merges clean.
- `hp3/kiosk-dense-control-room`, `fix/ui-consistency-kiosk-qr-utility-hp4`:
  unchanged from the 291 handoff — still need rebases, not ready.
