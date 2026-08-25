# DEV and PRODUCTION-TEST environments (canonical, no Nginx)

Written 2026-08-25. Kiosk v2 is canonical; kiosk v1 firmware/backend work is
frozen (legacy reference only, not actively developed).

## Architecture

Both environments route **Cloudflare Tunnel → MESFlow app directly**. No
Nginx, no TLS termination at the origin — Cloudflare terminates HTTPS at
its edge; the origin only ever speaks plain HTTP. This is deliberate for
kiosk v2: the ESP32 firmware talks plain HTTP (no TLS/mTLS complexity on
the device), and the same origin serves browsers over HTTPS via Cloudflare
with zero extra config.

```
DEV:
  https://dev.mesflow.net  (also: kiosk-v2-local-test.mesflow.net, same tunnel)
    -> Cloudflare Tunnel "kiosk-local-test" (5b430ab8-...)
    -> http://localhost:8199
    -> mesflow-local-test-app  (SERVER_ROLE=DEV, MESFLOW_ENV=local_test)
    -> mesflow-local-test-db

PRODUCTION-TEST:
  https://prod.mesflow.net
    -> Cloudflare Tunnel "mesflow-prodtest" (36306af3-...)
    -> http://localhost:8299
    -> mesflow-prodtest-app  (SERVER_ROLE=PRODUCTION_TEST, MESFLOW_ENV=production)
    -> mesflow-prodtest-db

Real production (unchanged, out of scope for this doc):
  https://mesflow.net, https://deploy.mesflow.net
    -> Cloudflare (DNS, not a named Tunnel) -> origin :443/:80 -> mesflow-nginx -> mesflow-app:8080 / mesflow-deploy-agent:8090
```

Real production still runs behind `mesflow-nginx` (TLS termination,
`/opt/mesflow/certs`) and was intentionally left untouched — this task's
scope was DEV + PRODUCTION-TEST only.

**`prod.mesflow.net` note**: this hostname previously had an orphaned
Cloudflare Tunnel route (tunnel `mesflow-production`, created 2026-08-21,
never connected) that would have resolved to real production's origin if
ever brought online. Confirmed abandoned and repointed to the new
`mesflow-prodtest` tunnel. The old `mesflow-production` tunnel (id
`1f16fbfb-ba28-432a-bd33-d08f6bc3ff5d`) was left as-is (not deleted) in
case it was the start of an unfinished real-production Tunnel migration —
worth checking with whoever created it before reusing or deleting it.

## Ports

| Env         | App port (host) | DB              |
|-------------|------------------|-----------------|
| DEV         | 8199             | mesflow-local-test-db (internal only) |
| PROD-TEST   | 8299             | mesflow-prodtest-db (internal only)   |

## Files

| Purpose                | DEV                          | PRODUCTION-TEST              |
|-------------------------|------------------------------|-------------------------------|
| Compose                | `compose.local-test.yml`     | `compose.prod-test.yml`       |
| Env (secrets, gitignored) | `.env.local-test`          | `.env.prod-test`              |
| Cloudflare tunnel config | `~/.cloudflared/kiosk-local-test-config.yml` | `~/.cloudflared/prodtest-config.yml` |
| systemd (user, linger enabled -> reboot-persistent) | `cloudflared-kiosk-local-test.service` | `cloudflared-prodtest.service` |

Both environments are fully isolated from each other and from real
production: separate compose project name, container names, Docker
network, volume, Postgres database/credentials, and app secrets. Neither
env file is committed.

## Start / stop / rebuild

```bash
cd /home/dell/workspace/mesflow/mesflow

# DEV
docker compose -f compose.local-test.yml --env-file .env.local-test up -d --build
docker compose -f compose.local-test.yml --env-file .env.local-test down       # stop
docker compose -f compose.local-test.yml --env-file .env.local-test logs -f mesflow-local-test-app

# PRODUCTION-TEST -- reuses the SAME image tag DEV validated (set
# PRODTEST_IMAGE in .env.prod-test), never rebuilt separately.
docker compose -f compose.prod-test.yml --env-file .env.prod-test up -d
docker compose -f compose.prod-test.yml --env-file .env.prod-test down
```

Migrations run automatically on container start (see
`scripts/docker-entrypoint.sh`); both stacks logged
`migration_head: 0039_kiosk_v2_protocol` cleanly from a fresh DB on
2026-08-25.

## Reset DEV DB (disposable by design)

```bash
docker compose -f compose.local-test.yml --env-file .env.local-test down -v   # drops the volume
docker compose -f compose.local-test.yml --env-file .env.local-test up -d --build
```

Never do this against `compose.prod-test.yml` without deliberately meaning
to wipe PROD-TEST's staging data.

## Health / identity check

Every environment reports `server_role` and `environment` from
`GET /api/system/ready` (added 2026-08-25 specifically so it's never
ambiguous which stack you're hitting):

```bash
curl -s https://dev.mesflow.net/api/system/ready   # server_role: "DEV"
curl -s https://prod.mesflow.net/api/system/ready  # server_role: "PRODUCTION_TEST"
```

`server_role` is a human/operator-facing label only (env var `SERVER_ROLE`)
-- distinct from `MESFLOW_ENV`, which is what code (e.g. kiosk_v2.py's
`_TIMING_ENABLED`) actually gates behavior on. Never assume the two are
interchangeable.

## Tunnel status / logs

```bash
systemctl --user status cloudflared-kiosk-local-test.service
systemctl --user status cloudflared-prodtest.service
journalctl --user -u cloudflared-prodtest.service -f
cloudflared tunnel list
```

**Known cloudflared gotcha**: `cloudflared tunnel route dns <name> <hostname>`
resolved to the *wrong* tunnel by name once during setup (silently pointed
a hostname at a same-account tunnel with an unrelated name). Always pass
the tunnel's UUID (from `cloudflared tunnel list`), not its name, to
`route dns` -- verify with `dig +short <hostname> @1.1.1.1` and a live
`curl` afterward regardless.

## Kiosk v2 plain HTTP -- verified

```bash
curl -v http://dev.mesflow.net/api/kiosk/v2/health    # 200, no redirect
curl -v http://prod.mesflow.net/api/kiosk/v2/health   # 200, no redirect
```

Confirmed 2026-08-25: neither domain forces an HTTP->HTTPS redirect on the
kiosk v2 API path. Point ESP32 firmware at `http://dev.mesflow.net` (DEV)
or `http://prod.mesflow.net` (PRODUCTION-TEST) directly.

## What did NOT get built in this pass

- No real ESP32 hardware was attached to this session, so the FAST
  2-cycle GOOD/DEFECT/REWORK kiosk test (see the kiosk-v2 firmware repo's
  own test plan) was **not run** against either environment -- only
  route-level smoke checks (`bootstrap`/`health`/`ready`) were verified
  live. Run the real FAST cycle from a physical device before trusting
  the full business flow here.
- `scripts/smoke-test.sh` is real-production-specific (hardcoded
  `Host: mesflow.net`, checks `/nginx-health`) and was left untouched --
  it doesn't apply to DEV/PROD-TEST and real production still has Nginx.
- The kiosk v2 backend source (`app/mesflow/web/kiosk_v2.py`, migration
  `0039_kiosk_v2_protocol.py`, this doc, etc.) is still **uncommitted**,
  sitting on branch `feat/employee-productivity-wallboard` (unrelated
  work) -- a proper commit/branch cleanup is still outstanding from an
  earlier consolidation pass and should happen before this is considered
  durable.
