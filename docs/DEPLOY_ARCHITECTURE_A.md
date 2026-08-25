# Deploy Architecture A: build-on-DEV, pull-by-digest, no Deploy Agent

Written 2026-08-25, proven end-to-end (deploy + rollback) on PROD-TEST.
Supersedes ad-hoc `docker compose up --build` on target servers.

## Flow

```
DEV MACHINE (this box)
  ./scripts/release-build.sh
    -> docker build (tags with GIT_COMMIT baked into the image)
    -> ephemeral-Postgres smoke test (migrate + boot + health, NOT the full
       pytest suite -- see "What this does not do" below)
    -> docker push to the registry
    -> release/mesflow-<version>.json  (version, commit, image, digest,
       migration_head, built_at)

  ./scripts/deploy.sh prodtest <version-or-digest>
    -> SSH preflight (hostname, compose project name, current SERVER_ROLE)
    -> docker pull <digest>            (never builds on the target)
    -> run migration using that SAME image (one-shot container, --entrypoint
       sh override, `wait-db && alembic upgrade head`, exits)
    -> recreate ONLY the app service (db, cloudflared untouched)
    -> health check: container healthy, /api/system/ready version/commit/
       server_role/migration_head/db-ok, and the RUNNING IMAGE's digest
       (via `docker image inspect` on the image the container was created
       from -- not the container itself, see gotcha below) all match
    -> on any failure: automatic rollback to the previous digest (app only)
    -> records REMOTE_DIR/deploy-state.json + appends deploy-history.jsonl

  ./scripts/deploy-status.sh prodtest   -- current state, health, history tail
  ./scripts/deploy-rollback.sh prodtest -- manual rollback to the digest recorded
                                            as "previous" in the last deploy
```

Registry: **self-hosted**, `127.0.0.1:5000` (container `mesflow-registry`,
`registry:2`, bound to localhost only -- nothing leaves this machine).
Chosen over an external registry (Docker Hub/GHCR) specifically to avoid
publishing source/images externally without a separate decision to do so.

## Why "SSH deploy" is SSH-to-self here

DEV, PROD-TEST, and real Production all run as containers **on this same
machine** -- there is no separate physical/VM target to SSH into. `deploy.sh`
still does a real `ssh dell@127.0.0.1 ...` for every remote step (passwordless
key auth set up 2026-08-25), so the mechanism -- and the guarantee that
nothing builds on the target -- is real, not simulated. If a genuinely
separate target host is ever introduced, only `SSH_HOST` in
`scripts/deploy_lib.sh`'s `target_config()` needs to change.

## Target definitions (`scripts/deploy_lib.sh`)

| | prodtest | production |
|---|---|---|
| REMOTE_DIR | `/home/dell/deploy/mesflow-prodtest` | `/opt/mesflow` (existing, unchanged) |
| compose project | `mesflow-prodtest` | `mesflow` |
| app service/container | `mesflow-prodtest-app` | `mesflow` / `mesflow-app` |
| SERVER_ROLE | `PRODUCTION_TEST` | `PRODUCTION` |
| image var | `MESFLOW_IMAGE` in `.env` | `MESFLOW_IMAGE` in `.env` (already the existing convention -- `compose.yml` there already reads `${MESFLOW_IMAGE:-mesflow-app:71.0.0.62}`, this predates this task) |

Neither target's deploy directory contains a source checkout -- just
`compose.yml`, `.env`, and the state files `deploy.sh` writes.

## Runtime minimalism

Both PROD-TEST and real Production run **app + postgres** only.
PROD-TEST's `cloudflared` runs as a host systemd service
(`cloudflared-prodtest`), not a container -- see `DEV_PRODTEST_ENVIRONMENTS.md`.
No nginx in either compose file. No Deploy Agent required by either target
to receive a deploy -- `deploy.sh` does everything the agent used to do,
from DEV, over SSH.

## Proven on PROD-TEST (2026-08-25)

- Two full deploys (different versions/digests), one **fully automated
  rollback proof** via `deploy-rollback.sh` (confirmed: correct previous
  digest redeployed, container healthy, `/api/system/ready` matched the
  older build exactly).
- **Real bug found and fixed during this proof**: `deploy.sh`'s digest
  check was inspecting the *container* for `.RepoDigests` (a field that
  only exists on `docker image inspect`, not container inspect) -- it
  silently returned empty and the pass condition's substring check made
  that vacuously true. Fixed: `running_digest()` in `deploy_lib.sh` now
  resolves the container's image ID first, then inspects *that*. Re-ran
  after the fix; digest now compared for a real exact match.
- **Second real bug found**: `__version__` in `mesflow/__init__.py` was a
  hardcoded string literal, completely disconnected from `VERSION.txt` --
  bumping the version file for a release did nothing to what
  `/api/system/ready` reported. Fixed at the source: `__init__.py` now
  reads `VERSION.txt` at import time (single source of truth), falling
  back to the old literal only if the file is missing.
- `deploy-rollback.sh`'s confirmation prompt doesn't work under
  `run_in_background` (piped stdin isn't attached) -- added a
  `ROLLBACK_YES=1` env-var bypass for non-interactive/scripted use;
  interactive use still prompts by default.

## What this does NOT do (honest gaps)

- **The smoke test in `release-build.sh` is migrate+boot+health, not the
  full pytest suite** (354 tests, needs a longer-lived Postgres fixture
  than an inline ephemeral container). Run the real suite separately
  before trusting a release beyond boot/migrate correctness.
- **Rollback never reverts the DB schema** (no `alembic downgrade`) --
  `deploy-rollback.sh` only ever recreates the app container. It's safe
  exactly when the older image tolerates the current (possibly newer)
  schema, which is a judgment call the operator makes, not something this
  script verifies automatically. The script's confirmation prompt says so.
- **Production is prepared, not executed.** `target_config production` in
  `deploy_lib.sh` is real and points at the actual `/opt/mesflow`, whose
  existing `compose.yml` already expects `MESFLOW_IMAGE=image@digest` (that
  convention predates this task). `deploy.sh production <version>` has
  **not been run**. Per the standing rule in this workspace: don't touch
  real Production without separate, explicit authorization -- ask before
  running it for real.
- **`mesflow-deploy-agent` (the old target-side agent) was left running,
  untouched.** It's still what actually deploys real Production today.
  Removing it is requirement #15's job, gated on Production actually being
  cut over to this flow -- which hasn't happened yet.
- Kiosk v2 backend source is still uncommitted, on the wrong branch
  (`feat/employee-productivity-wallboard`) -- unchanged from the prior
  outstanding gap.

## Commands reference

```bash
cd /home/dell/workspace/mesflow/mesflow

./scripts/release-build.sh                                    # DEV only
./scripts/deploy.sh prodtest <version-or-digest>
./scripts/deploy.sh production <version-or-digest>             # NOT yet run for real -- ask first
./scripts/deploy-status.sh prodtest
ROLLBACK_YES=1 ./scripts/deploy-rollback.sh prodtest            # or omit the env var for an interactive prompt
```
