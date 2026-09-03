# Deploy Architecture A: build-on-DEV, pull-by-digest, no Deploy Agent

Written 2026-08-25, proven end-to-end (deploy + rollback) on PROD-TEST.
Supersedes ad-hoc `docker compose up --build` on target servers.

## Current environment model (2026-08-25)

| Environment | Domain | Status |
|---|---|---|
| DEV | `dev.mesflow.net` | live, stable |
| PROD-TEST | `prod.mesflow.net` | live, stable -- full deploy/rollback/FAST-test workflow proven (see below) |
| PRODUCTION | `mesflow.net` | **2026-09-04: the 2026-09-02 "routes to `/opt/mesflow`" conclusion is disproven by a deterministic canary test** -- public `mesflow.net` is a genuinely different remote instance again. See "Production origin — 2026-09-04 follow-up" below before relying on anything above. `scripts/deploy.sh production` still refuses to run (`PRODUCTION_TARGET_NOT_CONFIGURED`) and that remains correct. |

**Update, 2026-09-02**: the 2026-08-25 conclusion below ("`mesflow.net`
is a different, unconfirmed remote host") is now **contradicted by
direct, repeated evidence** and is kept only as a historical record, not
current fact -- see "Production origin — 2026-09-02 follow-up" at the end
of this doc before relying on anything in the investigation section
immediately below. `/opt/mesflow` is the deploy-agent's own LOCAL/
PRODUCTION_TEST tier (per that agent's own `.env`, which correctly never
called it "PRODUCTION"), and per explicit user direction this session it
continues to be operated as PROD-TEST day to day -- `mesflow.net` now
routing here does not by itself mean every future deploy here should
skip the real-Production approval gate `scripts/deploy.sh production`
exists to enforce.

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

### Registry topology -- current limitation, deliberately deferred

```
CURRENT TOPOLOGY:   single physical host
                    (DEV, PROD-TEST, and real Production all run as
                    containers on this one machine -- confirmed, not
                    assumed, via `docker inspect`/`ssh` against each)
REGISTRY:           127.0.0.1:5000
SINGLE_HOST_DEPLOY_READY:  YES
REMOTE_DEPLOY_READY:       NO
```

`127.0.0.1:5000` only resolves for a puller on this exact host. That's
fine right now -- there is no second host for Production to actually be
remote from -- but it means this registry topology does **not** carry over
the moment Production moves to a separate machine. Two ready options were
scoped out but **intentionally not implemented** in this pass (2026-08-25):
Tailscale (bind the registry to this host's Tailscale IP, add it to
Docker's `insecure-registries`, requires a `sudo systemctl restart docker`
that restarts every container on this host -- a human call, not one to
make from here) or a Cloudflare Tunnel hostname gated behind Cloudflare
Access (needs dashboard-level auth config this session can't verify
blind). **Do not configure Tailscale, `daemon.json`, or a public registry
route as a side effect of an unrelated task** -- revisit this deliberately
when an actual second host exists to prove reachability against.

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
- ~~Kiosk v2 backend source is still uncommitted, on the wrong branch~~ --
  fixed 2026-08-25: committed on its own branch,
  `feat/kiosk-v2-deploy-architecture`, split cleanly from the unrelated
  pre-existing wallboard WIP (which got its own honest commit on its own
  branch first, so it wasn't lost or mixed in). `71.0.0.65-kiosk-v2-vn-font`
  (built dirty) was retired; `71.0.0.66` is the first release built from a
  clean, fully-committed tree (`release/mesflow-71.0.0.66.json` has
  `"dirty": false`). `release-build.sh` now refuses a dirty tree by default
  (`ALLOW_DIRTY_BUILD=1` overrides, for throwaway local iteration only).

## Production first-promotion prep (2026-08-25, prepare-only -- not deployed)

- **Real bug found and fixed**: `deploy.sh`'s compose-project-name
  preflight check did a bare `grep '^name:' compose.yml`. Production's
  `compose.yml` has no explicit `name:` key (Compose infers `mesflow` from
  the `/opt/mesflow` directory name instead) -- the grep silently returned
  empty, which would have aborted *every* production deploy at the very
  first preflight check. Fixed to resolve the name via
  `docker compose config` (which applies the same directory-fallback logic
  Compose itself uses), verified against both `production` and `prodtest`.
- **`SERVER_ROLE=PRODUCTION`** added to `/opt/mesflow/.env` (file only --
  confirmed via `RestartCount`/`StartedAt` that the running container was
  never touched). Takes effect on the next app recreate, i.e. the first
  real deploy.
- **Rollback baseline adopted**: since Production has never gone through
  this flow, there was no deploy history to roll back to if the *first*
  Architecture-A deploy fails. `/opt/mesflow/deploy-state.json` and
  `deploy-history.jsonl` were seeded with the CURRENTLY RUNNING
  `71.0.0.62` (real image ID/digest, confirmed still present locally) as a
  `BASELINE_ADOPTED` entry -- metadata only, no container/DB change.
- **`deploy-rollback.sh --dry-run`** added: reports what a rollback would
  target right now (falls back to the adopted baseline when no real
  Architecture-A deploy has happened yet) and, if a newer release manifest
  exists locally, what it would target after that release deploys. Zero
  remote mutation.
- **Migration 0039_kiosk_v2_protocol classified SAFE_FORWARD**: read in
  full -- four `CREATE TABLE` + one `INSERT` into a new table, no
  `ALTER`/`DROP`/`TRUNCATE`, never touches `employees`/`operations`/
  `production_orders`/`work_sessions`. This also means an app-only
  rollback (no `alembic downgrade`) is safe after this specific migration:
  the old app code simply doesn't know the new tables exist.
- **Config compatibility confirmed**: the only env var the new
  `kiosk_v2.py` module reads is `MESFLOW_ENV` (for a LOCAL_TEST-only
  timing diagnostic, gated on the literal string `'local_test'`) --
  production's `MESFLOW_ENV=production` already guarantees that stays off.
  No new required var is missing from `/opt/mesflow/.env`.
- **Kiosk v2 HTTP infra path confirmed no-redirect**, even though the
  routes don't exist in the currently-running `71.0.0.62` yet (404, as
  expected) -- `http://mesflow.net/api/kiosk/v2/*` and the known-working
  `http://mesflow.net/api/system/ready` both proxy over plain HTTP with no
  forced HTTPS redirect on this vhost.

**Correction, same day**: the "production" promotion this section
describes was actually executed against `/opt/mesflow` on this dev
machine, believed at the time to be real Production. It was not -- see
the investigation immediately below. `71.0.0.66` genuinely is running
healthy on this host, correctly migrated, correctly serving kiosk v2 --
it's just not reaching the public internet. Nothing here was undone; the
facts above remain true of *this host*.

## Production origin investigation (2026-08-25)

Public `mesflow.net` (verified via real DNS, and again forcing the exact
Cloudflare anycast IPs explicitly to rule out any local resolver
weirdness) kept serving `71.0.0.62` after this host's `/opt/mesflow` was
deployed to `71.0.0.66` -- proof they are different instances, not just a
version mismatch to reconcile.

Evidence gathered (all read-only):
- **No cloudflared process or config anywhere on this host** has an
  ingress rule for bare `mesflow.net` -- checked all 4 running tunnel
  connectors and every config file including timestamped backups.
- **`artifacts/releases/71.0.0.62/PROMOTION.json`** (this repo's own
  release pipeline bookkeeping) explicitly records:
  `"production": {"status": "NOT_DEPLOYED"}` for the exact version public
  `mesflow.net` is running -- this pipeline never sent it there.
- **`mesflow-deploy-agent`'s own env** has `MESFLOW_PRODUCTION_AGENT_URL`
  (the real remote-production target) completely **empty**; only
  `MESFLOW_PRODUCTION_TEST_AGENT_URL=https://deploy.mesflow.net/agent`
  (this same host) is configured.
- **`~/.ssh/config`** has a named alias, `Host prod` / `Host mesflow-prod`
  -> `ssh-prod.mesflow.net`, user `kimex` (matches the codebase's own
  hardcoded `"KIMEX Administrator"` admin display name), reached via
  Cloudflare Access rather than a plain tunnel -- the best lead, **not
  confirmed**: a read-only connection attempt reached Cloudflare Access's
  edge (a real websocket handshake attempt) but failed for lack of a valid
  Access session in this environment. Did not attempt to bypass this.

**Classification: DIFFERENT_REMOTE_HOST (high confidence on "not this
host"; specific candidate well-evidenced but not independently
confirmed).** `scripts/deploy.sh production` is frozen
(`PRODUCTION_TARGET_NOT_CONFIGURED`) until a human confirms the real
target and creates `scripts/production-target.env`.

## PROD-TEST stabilization (2026-08-25)

Full workflow re-proven end-to-end against `prod.mesflow.net` specifically
(not just localhost), after the production freeze was added:

- **Kiosk v2 FAST test, 2/2 PASS**: no real ESP32 hardware in this
  session, so a script drove the exact `/api/kiosk/v2/events` envelope the
  firmware sends (protocol_version/device/event/context/payload, per
  `kiosk_v2.py`'s own `_apply_event()`) against `http://prod.mesflow.net`
  for real. Cycle 1 (GOOD=25/DEFECT=0/REWORK=0) and Cycle 2
  (GOOD=20/DEFECT=4/REWORK=3) both PASS -- verified independently via
  direct DB query, not just trusting the API response: both
  `work_sessions` rows `CLOSED` with exact quantities, 0 `OPEN` sessions,
  8/8 distinct `kiosk_v2_events` rows (no duplicates). Fixture used:
  employee `NV001`, a seeded `PO-FASTTEST-01` / `OP-FASTTEST-01` (real
  production_orders/parts/operations rows, `IN_PROGRESS`, reproducible via
  the SQL in this doc's history rather than hand-preserved).
- **Recovery, targeted (not a long stress run)**: exact-duplicate event
  retry replayed the identical cached response with zero double-effect
  (1 DB row despite 2 requests); stopping/restarting `mesflow-prodtest-app`
  produced a clean `502` during the outage (not a hang) and a fully
  correct resync (`GET /state` returned the exact pre-restart projection)
  plus a working continuation event afterward.
- **Rollback, full lineage**: deployed release A -> release B -> rolled
  back to A (digest-exact, healthy, DB-compatible since both share
  migration head `0039`) -> restored B (digest-exact, healthy).
- **Same digest DEV = PROD-TEST**: confirmed via `docker image inspect`
  on both, not by tag string alone.
- **Tunnel persistence**: `systemctl --user restart
  cloudflared-prodtest.service` -- tunnel re-established within ~10s,
  `enabled` + `linger=yes` (reboot-persistent). No unrelated Docker
  service was restarted (`mesflow-app`/`mesflow-nginx` RestartCount
  confirmed unchanged before/after).
- **No nginx, no duplicate backends confirmed**: `mesflow-prodtest-net`
  contains exactly `mesflow-prodtest-app` + `mesflow-prodtest-db`; the
  only nginx container on the host (`mesflow-nginx`) is on a completely
  separate network, unreachable from PROD-TEST's path.

## Commands reference

```bash
cd /home/dell/workspace/mesflow/mesflow

./scripts/release-build.sh                                    # DEV only
./scripts/deploy.sh prodtest <version-or-digest>
./scripts/deploy.sh production <version-or-digest>             # NOT yet run for real -- ask first
./scripts/deploy-status.sh prodtest
ROLLBACK_YES=1 ./scripts/deploy-rollback.sh prodtest            # or omit the env var for an interactive prompt
```

## Production origin — 2026-09-02 follow-up

The 2026-08-25 investigation above was correct *for that day* — real
evidence, correctly read. It is no longer current. Something (most likely
Cloudflare tunnel/DNS work done earlier in the 2026-09-02 session, before
this note) now routes public `mesflow.net` to `/opt/mesflow` on this same
host.

**Evidence, this session (2026-09-02), repeated and consistent every
time**: every one of several deploys to `/opt/mesflow` this session
(`71.0.0.207` through `71.0.0.210`) was immediately followed by
`curl https://mesflow.net/api/system/version`, and separately by a real
Playwright browser session — actual login (`POST /api/auth/login`, real
credentials, real `200`), actual page navigation, actual screenshot —
against `https://mesflow.net` itself. Both consistently reflected the
exact version just deployed, every single time, across 4 separate
deploys. This is the same "different instance would show a stale
version" signal the 2026-08-25 investigation used, now pointing the
other way.

**User confirmation**: the user explicitly stated mid-session that
`mesflow.net` currently routes to what they consider the PROD-TEST tier
("mesflow.net đang trỏ vào prod test"), and on being asked directly,
confirmed this documentation update ("xác nhận đúng, cập nhật doc luôn
đi", 2026-09-02).

**What this does and does not change**:
- Does: correct this doc's factual claim about where `mesflow.net`
  currently routes — it is `/opt/mesflow` on this host, not an unconfirmed
  remote.
- Does **not**: change `scripts/deploy_lib.sh`'s `production` target
  refusal, or claim `/opt/mesflow` should now be treated as the final,
  human-approval-gated real-Production target that `scripts/deploy.sh
  production` was built for. The user's own framing keeps calling this
  tier "prod test" day to day. Loosening that code-level safety guard —
  the one that exists specifically to prevent "the exact mistake that
  caused the earlier incident" (its own comment) — is a separate decision
  from correcting this doc, and was not asked for here. If a future
  session wants `scripts/deploy.sh production` to target `/opt/mesflow`
  for real, that needs its own explicit, separate confirmation and a real
  `scripts/production-target.env`, not an inference from this note.
- Cloudflare tunnel config was not re-audited as part of this specific
  doc update (out of scope for a documentation correction) — if the exact
  ingress rule that now serves bare `mesflow.net` matters for a future
  investigation, re-run the same read-only checks the 2026-08-25
  investigation used (all 4 tunnel connectors' configs, including
  timestamped backups).

## Production origin — 2026-09-04 follow-up

The 2026-09-02 conclusion above ("`mesflow.net` routes to `/opt/mesflow`
on this host") is **disproven** by a deterministic canary test run this
session, not just a version-string mismatch like 2026-08-25's original
finding.

**Trigger**: a user screenshot of the real `mesflow.net` "Video hướng
dẫn" tab showed 13 tutorial videos; this host's `/opt/mesflow` tutorial
directory (believed to be what `mesflow.net` serves, per the 2026-09-02
note) was, before this session touched it, running a *14*-video set
(`generated_at 2026-08-21`, `mesflow_version 71.0.0.46`) — already a
mismatch in count, prompting the recheck below.

**Canary test** (deterministic, not probabilistic): this session
created a directory, `_backup_20260904_old-14ch/`, directly on this
host's `/opt/mesflow/runtime/tutorials/` (the bind-mounted host path
behind `mesflow-app`'s `/data/tutorials:ro` mount) — a path that could
not possibly exist anywhere else, since nothing else on Earth had
written it. An authenticated request to
`https://mesflow.net/tutorials/_backup_20260904_old-14ch/manifest.json`
immediately after creating it returned **404 `NOT_FOUND`**. If public
`mesflow.net` were this host, that request would have returned the file
verbatim (the route just does a `send_from_directory` off
`MESFLOW_TUTORIAL_DIR`, no allowlist beyond "must exist under the
tutorial root"). It did not. **Public `mesflow.net` is not this host.**

**Corroborating, independent evidence**: `https://mesflow.net/api/tutorials`
(authenticated) returned a *third*, distinct 13-item manifest — different
video count, different per-chapter durations, and missing
`09_kiosk_operator` entirely — matching neither this host's pre-session
14-video set nor the 15-video set this session published here. Three
distinct tutorial manifests across what should be one "production"
concept is itself strong evidence of three distinct filesystems/hosts.

**Why `/api/system/version` matched anyway**: that endpoint returns only
code-derived fields (`architecture`, `database_backend`, `phase`,
`version`) — nothing host- or container-identifying. Any two hosts
running the same Docker image report byte-identical JSON there. The
2026-09-02 investigation's core evidence (repeated version-match after
deploying here) only proves *the same code version reached both places*
— plausible if a separate, legitimate channel (`mesflow-deploy-agent`,
confirmed still running and still "what actually deploys real Production
today" per the 2026-08-25 section above) keeps the real remote Production
host in version lockstep with this one. It does not prove they are the
same host, and per this session's canary test, they are not.

**Current best lead, unchanged from 2026-08-25, still unconfirmed**:
`~/.ssh/config` still has `Host prod` / `Host mesflow-prod` →
`ssh-prod.mesflow.net`, user `kimex`, via `cloudflared access ssh`
(Cloudflare Access). Not attempted beyond this read-only config check —
per this doc's own standing rule, guessing or bypassing Access is out of
scope for an automated session.

**Practical effect on this doc**: revert to treating "where `mesflow.net`
really routes" as **unconfirmed** again, exactly as 2026-08-25 concluded.
The 2026-09-02 note's correction was made in good faith on real but
insufficient evidence (version-string matching); this note supersedes it
with a stronger, deterministic test. `scripts/deploy.sh production`'s
refusal to run without a real `scripts/production-target.env` remains
exactly the right behavior — this incident is a direct demonstration of
why that guard exists.

**What this does NOT mean**: the tutorial-video work done against
`/opt/mesflow` on this host earlier today was not wasted or wrong to do
— `/opt/mesflow` is a real, user-operated tier (day-to-day called
"prod test" per the user's own framing, 2026-09-02), now correctly
carrying the full 15-chapter set. It is simply not what the user's
screenshot was showing. Getting the same content onto the real public
`mesflow.net` requires either real credentials for the `kimex@
ssh-prod.mesflow.net` lead (or another host the user identifies) or the
user performing the final copy themselves from the artifact this session
staged.
