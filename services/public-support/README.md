# Public support service (TEST only)

The landing at `/` and `/welcome` uses the approved public facts embedded in
`app/mesflow/web/templates/welcome.html#support-facts`. The browser sends only a
recognized topic ID to `POST /support/chat` with `credentials: omit`. No raw
question, history, session, business data, tool catalogue or customer data is
sent to the gateway. The model can select approved IDs, not publish free prose.

`server.py` intentionally runs separately from MESFlow. It has no database URL,
MES signing key, authenticated endpoint, or business application imports.

The verified real gateway is `https://ai-gateway.mesflow.net/v1` (m910), bearer
authenticated. The existing `facebook-chat` route is non-queued and currently
contains only grok-web, gemini-web and deepseek-web. The adapter verifies the
live route candidates before each uncached completion and validates the actual
provider and JSON output. Mock, Claude, queued routes and arbitrary output are
rejected. It never switches to auto, a paid model, or the HP mock gateway.

The UI reports `gateway`, `gateway_cached`, or `faq` truthfully. HTTP 202,
timeouts, invalid output, rate limits, absent credentials and service outages
all leave the approved FAQ answer usable. A healthy `/health` is NOT evidence
that AI is working. Gateway questions must be observed completing before
claiming live integration.

Limits: 256-byte JSON body, 1–2 known topic IDs, six requests/minute/client IP,
20 upstream attempts/hour, two in flight, 20-second completion timeout,
four-second model check, 60-second failure cooldown, five-minute memory cache.
One worker is required; restarting resets the memory budgets. Nginx overwrites
the IP header with its peer address (visitors sharing a proxy may share limits).
No chat body logging or persistence. Only public topic facts reach provider
accounts; the gateway may retain those public prompts under its own policy.

## Build and TEST rollout

Build from the tested commit; do not rebuild the MES business app:

```sh
docker build -f services/public-support/Dockerfile -t mesflow-public-support:<commit> .
```

On the confirmed `PRODUCTION_TEST` VPS only, transfer/load the image and place
`compose.yml` under `/opt/mesflow/public-support/`. Root-owned mode-0600
`/opt/mesflow/public-support.env` contains:

```text
SUPPORT_GATEWAY_URL=https://ai-gateway.mesflow.net/v1
SUPPORT_GATEWAY_MODEL=facebook-chat
SUPPORT_GATEWAY_KEY=<dedicated managed client key>
```

Do not print or commit the key. No host port is published. The external Docker
network is **mesflow-edge**, verified from the actual nginx container (not the
legacy mesflow_network). Set SUPPORT_IMAGE in the service directory `.env` and
run `docker compose up -d`. This starts only `mesflow-public-support`.

Backup the current gateway config and both copies of welcome.html. Prepare a
candidate with `scripts/prepare-public-root-nginx.py`, based on the ACTUAL
`/opt/mesflow-gateway/nginx/nginx.conf`. Copy welcome.html into both
`/opt/mesflow/public-showcase/` and
`mesflow-nginx:/usr/share/nginx/html/mesflow-showcase/`. Test candidate nginx
config inside that container. Replace the bound config **in place** (preserve
inode), run `nginx -t`, then reload. Do not recreate nginx or the MES app.

The exact `/support/chat` route strips Cookie/Authorization and response
Set-Cookie. Its runtime-resolved upstream lets nginx continue running if the
support container is unavailable; the browser then supplies FAQ fallback.

Verify public HTTPS root 200, mobile chat/layout, real `mode=gateway`, explicit
outage fallback, demo, manual login form, anonymous `/app` 302 and API 401, and
unchanged MES app image/start time. Authentication tests run separately against
the disposable PostgreSQL stack, never using live accounts for destructive tests.

Rollback: restore backed-up HTML to both locations, restore nginx.conf in place,
validate/reload nginx, then `docker compose down` in the **support-only** directory.
Never run this in `/opt/mesflow` or change the MES app/DB. Revoke the dedicated
gateway key if retiring the integration.
