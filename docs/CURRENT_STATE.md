# Current state (read this first)

Written 2026-08-25, end of the infrastructure/deployment/repository-
reconciliation phase. Keep this short and factual — update it, don't let
it go stale, and don't duplicate the full story (see the docs it points to
for that).

## Canonical

- **MESFlow backend**: this repo, `main` branch, commit `cd27d75` (this doc
  was written right after that push).
- **Kiosk**: **Kiosk Runtime v2** (`/home/dell/workspace/mesflow-kiosk-runtime-v2`,
  own repo). **Kiosk v1** (`mesflow/esp-kiosk`) is FROZEN — reference/read-only,
  no active feature work.

## Version / release metadata

- App version: `VERSION.txt` = `71.0.0.67` — this is the single source of
  truth; `mesflow.__version__` reads it at import time, `release.json`'s
  `version` field is kept in sync by `scripts/release-build.sh` (fixed
  2026-08-25 after being found stale once — was `71.0.0.62` while
  `VERSION.txt` had already moved on).
- Migration head: `0039_kiosk_v2_protocol`.
- Kiosk Runtime v2 firmware version: `0.9.0` (that repo's own `VERSION`
  file / commit `22a0047`).

## Environments

| | Domain | Server role | Notes |
|---|---|---|---|
| DEV | `dev.mesflow.net` | `DEV` | disposable data, no nginx, no deploy-agent |
| PROD-TEST | `prod.mesflow.net` | `PRODUCTION_TEST` | staging-grade, same digest as DEV, full deploy/rollback proven |
| Production | `mesflow.net` | `PRODUCTION` | **FROZEN** — real target host unconfirmed, `scripts/deploy.sh production` refuses (`PRODUCTION_TARGET_NOT_CONFIGURED`) until `scripts/production-target.env` is created with a verified non-local host |

Deploy model: **Architecture A** — build once on DEV
(`scripts/release-build.sh`, requires a clean tree), push to a self-hosted
local registry (`127.0.0.1:5000`, deliberately not remote-reachable yet —
no second host exists to justify that work), `scripts/deploy.sh <target>
<version>` pulls the exact digest, migrates with that same image, recreates
only the app container, health-gates, auto-rolls-back on failure. No nginx,
no Deploy Agent in this flow for DEV/PROD-TEST. Full details:
`docs/DEPLOY_ARCHITECTURE_A.md`, `docs/DEV_PRODTEST_ENVIRONMENTS.md`.

## Current priority

**Kiosk v2 bug fixing and product behavior.** The infrastructure/deploy
phase is done — see the two docs above for that whole story if needed, but
new work should not need to touch deploy tooling.

## Known deferred (intentional, not forgotten)

- Real Production's actual target host — best lead (`ssh-prod.mesflow.net`
  / user `kimex` via Cloudflare Access) not yet confirmed; see
  `docs/DEPLOY_ARCHITECTURE_A.md`'s "Production origin investigation".
- Remote/multi-host registry topology — fine on one host, revisit once a
  real second host exists.
- mTLS/secure boot/flash encryption on the kiosk — designed only, see that
  repo's `docs/SECURITY.md`.
- Touch (FT6336G) on the kiosk hardware — present, not driven.

## Branches (this repo)

- `main` — canonical, matches `origin/main`.
- `feat/kiosk-v2-deploy-architecture`, `feat/kiosk-v2-deploy-clean` —
  historical; content fully superseded by what's on `main` now (kept, not
  deleted).
- `feat/kiosk-v2-backend` — an earlier, superseded kiosk_v2.py snapshot
  (still had the old ASCII-transliteration workaround); its non-kiosk
  content (user-guide.vi.json changes) is already on `main` via a
  different path. Kept, not deleted.
- `feat/employee-productivity-wallboard` — genuinely unique, unmerged
  feature work (4 commits), deliberately NOT part of `main` yet. Not this
  phase's concern.
