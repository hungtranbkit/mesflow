# Codex Task — Integrate `agent.mesflow.net` reverse proxy

## Goal
Update the current MESFlow repository so the Dockerized Nginx publishes the Linux-host Server Agent running on port `8090` at:

- `http://agent.mesflow.net` → redirect to HTTPS
- `https://agent.mesflow.net` → reverse proxy to Linux host port `8090`

Target release: **65.8.44.12**.

## Important architecture
- MESFlow Nginx runs **inside Docker**.
- Server Agent runs **directly on the Linux host**, port `8090`.
- Do **not** proxy to `127.0.0.1:8090` from inside the Nginx container; that would point back to the Nginx container itself.
- Use Docker Linux host gateway:
  - Compose: `extra_hosts: ["host.docker.internal:host-gateway"]`
  - Nginx upstream: `host.docker.internal:8090`
- Agent should listen on an address reachable from the Docker bridge, normally `0.0.0.0:8090` or the host bridge address.
- Port `8090` does not need to be directly exposed to the public Internet.

## Required changes
1. `compose.yml`
   - Add `extra_hosts` to the `nginx` service:
     `"host.docker.internal:host-gateway"`.
   - Keep ports `80:80` and `443:443`.
2. `nginx/nginx.conf`
   - Add upstream `mesflow_agent_backend` using `host.docker.internal:8090`.
   - Add HTTP vhost for `agent.mesflow.net` that redirects to HTTPS.
   - Add HTTPS vhost for `agent.mesflow.net` using the existing MESFlow certificate.
   - Reverse proxy all paths to the Agent.
   - Preserve Host/X-Forwarded headers.
   - Support WebSocket upgrade for interactive SSH terminal.
   - Disable proxy buffering.
   - Set read/send timeout to 3600 seconds.
3. Version metadata
   - Synchronize `VERSION.txt`, `app/mesflow/__init__.py`, `release.json`, and Docker image tag to `65.8.44.12`.
4. Add contract test:
   - `tests/test_agent_nginx_contract_v6584412.py`

## Apply strategy
- Prefer applying `agent_nginx_v6584412.patch` with `git apply --3way`.
- If the current branch has newer unrelated changes, **merge semantically instead of overwriting newer code**.
- `payload/` contains the exact known-good target versions of the affected files for reference only.
- Do not revert unrelated changes.

## Commands
```bash
# From MESFlow repository root
git status --short
git apply --check agent_nginx_v6584412.patch || true
git apply --3way agent_nginx_v6584412.patch

python -m pytest -q tests/test_agent_nginx_contract_v6584412.py
nginx -t -c "$PWD/nginx/nginx.conf"   # if nginx is installed locally; otherwise use Docker check below

docker compose config >/dev/null
docker compose run --rm --no-deps nginx nginx -t
```

If `git apply --3way` conflicts, inspect the patch and merge only the Agent-related sections manually.

## Runtime verification after deployment
```bash
sudo ss -lntp | grep ':8090'
docker compose exec nginx getent hosts host.docker.internal
docker compose exec nginx wget -S -O- http://host.docker.internal:8090/ 2>&1 | head -40
curl -I http://agent.mesflow.net
curl -kI https://agent.mesflow.net
```

Expected:
- HTTP returns `301` to `https://agent.mesflow.net/...`.
- HTTPS reaches Agent instead of MESFlow app.
- WebSocket/terminal stays connected.

## DNS / TLS prerequisites
- DNS `agent.mesflow.net` must point to the MESFlow server/public reverse proxy.
- `/etc/nginx/certs/mesflow.net.pem` must cover either `agent.mesflow.net` or `*.mesflow.net`.

## Acceptance criteria
- Existing `mesflow.net` routing continues working.
- `agent.mesflow.net` proxies to host `:8090`.
- WebSocket Upgrade headers are present.
- No direct public mapping of `8090` is added.
- Contract test passes.
- Version metadata is synchronized.
