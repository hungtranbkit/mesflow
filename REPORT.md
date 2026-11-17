# OTA ESP32 Release Readiness — isolated verification report

**Updated:** 2026-11-18 (Asia/Bangkok)  
**Decision:** **NO-GO for merge, deployment, or enabling mandatory fleet OTA.**  
**Scope:** Isolated Dell checkout and local test containers only. No M910 board, MESFlow production stack, production data, deployment endpoint, or OTA fleet control was used.

## Release gates

| Gate | Evidence | Result |
|---|---|---|
| MESFlow PR #50 source | Branch `feat/esp-ota-force-scoped-20261111`, current pushed commit [`98906ee15c8910ce7cbf68365a398f4be1f5651f`](https://github.com/hungtranbkit/mesflow/commit/98906ee15c8910ce7cbf68365a398f4be1f5651f); PR remains Draft/Open | Browser harness-only changes pushed; local backend test determinism follow-up is not yet pushed |
| Python/PostgreSQL backend | Isolated Compose full run, deterministic fixture changes in working tree: unit 429, static 925, behavior 45, integration 628 pass; skips 10/14/1/2 | All stages passed; integration log `test-results/backend-deterministic.log`. Fresh CI is required after pushing these fixture changes. Prior baseline run at 00:10 ICT had 616 pass / 12 fail / 2 skip due wall-clock shift assumptions. |
| Browser full suite | Playwright image `mcr.microsoft.com/playwright:v1.62.0-noble`, lockfile Playwright `1.62.1`, one worker, retries 0; full log `test-results/full-e2e-final.log` | Final rerun: **609 passed, 4 skipped, 0 failed** (613 total) |
| Specific browser cases | Camera track lifecycle 3/3, dependent session filters 3/3, rework-card contract 12/12 after corrections; supplemental tutorial coverage 9/9 | PASS, focused runs |
| Agent package/restore | Scratch source based on Agent PR #1 SHA `0759e8ca6dcfe0eb00f62e06851a5b2cb1f0c53d`; detailed below | Package build, checksum/extraction, image load, offline liveness PASS. Full Docker-enabled Agent suite and real updater compose-recreate flow NOT VERIFIED. |
| Agent PR #1 | `hungtranbkit/mesflow-agent#1`, SHA `0759e8ca6dcfe0eb00f62e06851a5b2cb1f0c53d` | Open/Ready; ESP OTA gate and two full-suite CI runs PASS |
| ESP kiosk PR #2 | `hungtranbkit/mesflow-esp32-kiosk#2`, SHA `09db474c78dfb6223ed91c07e92c80db85c86677` | Open/Ready; build-release and host-tests CI PASS |
| M910 hardware OTA/rollback | User-provided evidence from the release-readiness report and session: A→B and rollback PASS | Not repeated here; no board access/action |
| Merge/deploy/mandatory OTA | GitHub PR state and task constraints | Not performed; fleet-mandatory OTA remains OFF |
| Auto-deploy exclusion | Repository workflow and hook review | Repo hooks count is 0 for all three repositories. MESFlow and Agent repos are public and Actions are enabled. Visible workflows run tests/build gates on PR/push/manual triggers; none is a deploy workflow for these PR changes. Org-level GitHub Apps, downstream automation, and server-side update configuration were not auditable through available repo-level access: **NOT VERIFIED**. Do not claim auto-deploy is excluded. |

## Test environment and browser results

Checkout: `/home/dell/workspace/ota-release-e2e-20261117`, on the feature branch above. The MESFlow Compose project was named `ota-release-e2e-20261117`, with an explicit test-only `10.253.250.0/24` network because Docker's default IPAM pools were exhausted. API, Postgres, strict API, support, edge and runner containers were project-scoped; no service ports were published to the host. Postgres data used Compose tmpfs. The browser runner was capped at 2 CPUs / 6 GB and ran one worker, without retries. It had no host Docker socket or production volume.

Before browser runs, `scripts/test/generate-esp-tutorial-fixture.sh` generated seven synthetic videos and `scripts/validate-esp-tutorial-fixture.js` passed. `npm ci --no-audit --no-fund` ran with the repository lockfile; browser image was the cached Playwright 1.62.0 image compatible with the locked 1.62.1 npm package.

The first complete 613-test run reported **608 passed, 4 skipped, 1 failed**. The failure at `tests/e2e/rework-queue-card-contract.spec.js` was navigation interruption: `/login` automatically posts test auto-login and redirects to `/app` while the test concurrently navigated to its deep link. It was the same harness race corrected in the session-filter test. After fixing that helper, the entire rework-card file passed **12/12** over three repeats. Camera stop was strengthened to check the actual captured WebKit MediaStreamTrack's `readyState === 'ended'`; that test passed **3/3**. Session-filter URL normalization passed **3/3**. Tutorial supplemental tests passed **9/9**. These changes are browser harness-only; no product source changed.

Final browser after-fix run command:

```sh
docker run --rm --init --name ota-release-e2e-20261117-playwright-after-fix \
  --network ota-release-e2e-20261117_default --cpus=2 --memory=6g --shm-size=1g \
  -e MESFLOW_BASE_URL=http://mesflow-test-edge:8080 \
  -v "$PWD:/workspace" -w /workspace \
  --entrypoint bash mcr.microsoft.com/playwright:v1.62.0-noble \
  -lc 'npm ci --no-audit --no-fund && npx playwright test --workers=1 --retries=0'
```

Log: [`test-results/full-e2e-final.log`](test-results/full-e2e-final.log). Result: **609 passed, 4 skipped, 0 failed**.

### Backend rerun at midnight

An initial local rerun completed unit **429 passed / 10 skipped**, static **925 / 14**, behavior **45 / 1**, integration **616 passed / 12 failed / 2 skipped**. The 11 kiosk-start-related expected-success assertions returned `SHF-409 OUTSIDE_SHIFT`. At the observed time (2026-11-18 00:10 ICT), the test DB's configured DAY shift was 08:00–17:00 and NIGHT was 18:00–00:00. This is the intended current-time shift guard, not an OTA product failure. The remaining failure was the live-duration test's midnight-boundary tolerance: its lower bound was 4 seconds above the observed value. At least one prior full backend run completed with all four stages green before midnight.

For diagnosis, a temporary 24-hour shift was inserted into the isolated test DB; the three affected modules passed **30/30**. To make unrelated success-path tests independent of wall time, local test-only changes now create and clean up a scoped 24-hour shift fixture, while shift-rejection policy tests remain unchanged. Operation-time assertions now compare against the configured WORK interval. The subsequent complete isolated backend run passed: unit **429/10 skipped**, static **925/14 skipped**, behavior **45/1 skipped**, integration **628/2 skipped**. Log: [`test-results/backend-deterministic.log`](test-results/backend-deterministic.log). Changes await commit/push and fresh CI.

## Agent artifact build and restore

The Agent repo's canonical `scripts/build-agent-release.sh` runs tests against whatever Docker daemon is visible. Some included test modules inspect/manage Docker containers or expect sibling repositories. To avoid touching shared host containers, the Agent source was copied to `/tmp/ota-agent-release-20261117/agent`, version-bumped in that scratch copy to the unused `2.24.50-docker-runtime`, and built with the same release script. Test-time Docker availability was hidden; cross-repo tests and host-container inspection tests were excluded. Result: **479 passed / 32 skipped**. This is a scoped qualification, not the complete Agent suite.

- Image: `mesflow-deploy-agent:2.24.50`
- Image ID: `sha256:bc6f89329053627d522c496eafa1d85c81215fb335aa344d3e24d6e85d82237b`
- API protocol: `2`
- Artifact: `/tmp/ota-agent-release-20261117/artifacts/deploy-agent/releases/2.24.50-docker-runtime/AGENT_UPDATE_2.24.50-docker-runtime.zip`
- ZIP SHA-256: `196a465359321d486b35680f4d7cfce4d4d62af94c3dc80867edaf47e2f7963b`

The actual ZIP was extracted and checksum-verified with `updater.extract_and_verify_artifact`; its image tar was loaded into Docker. The container returned `/agent/live` with version `2.24.50-docker-runtime` and protocol 2. Smoke constraints were `--network none`, 512 MB, no published ports, no mounts, read-only root plus temporary `/tmp` and `/data`, with deploy/host operations disabled. The task-created smoke container was stopped and removed. No Docker socket or production volume was passed into it. This does not verify the updater's real compose recreation/health-poll lifecycle.

One Agent test collection attempt used system Python without Flask; a later attempt without explicit home overrides was denied before writing at `/opt/mesflow-agent`. No `/opt` changes occurred. The passing run explicitly set scratch `WORKSHOP_AGENT_HOME`, `WORKSHOP_TARGET_HOME`, and `MESFLOW_QA_HOME`.

## GitHub checks and PR state

- PR #50 currently points to `98906ee15c8910ce7cbf68365a398f4be1f5651f`, remains Draft/Open. Latest visible GitHub PostgreSQL workflow runs fail (run IDs 44138381391 and 44138393399); backend fixture follow-up has not yet been pushed. Earlier runs on `31d6c82` also failed with 13 wall-clock shift-dependent integration failures: [run 44131620224](https://github.com/hungtranbkit/mesflow/actions/runs/44131620224), [run 44131635468](https://github.com/hungtranbkit/mesflow/actions/runs/44131635468).
- Agent PR #1 and firmware PR #2 remain Open and their current visible checks pass.
- GitHub webhook API returned zero hooks for MESFlow, Agent, and firmware repositories. No merge, deploy, secret read, or workflow dispatch was performed.

## Decision and next actions

Production release decision is **NO-GO**. The local backend full suite and browser full suite are green, but GitHub backend CI remains red on the pushed commit and has not yet run against the local deterministic fixture changes. Agent's complete Docker-enabled suite and updater compose-recreation are unverified. Repo-level visibility cannot exclude organization or downstream automation. Keep all PRs unmerged, production untouched, and mandatory OTA OFF until fresh backend CI is green, Agent restore is verified through the isolated updater flow, and deployment automation scope is verified by someone with org/server-level access.
