from pathlib import Path

CONF = Path("nginx/nginx.conf").read_text()
COMPOSE = Path("compose.yml").read_text()
VERSION = Path("VERSION.txt").read_text().strip()
# The nginx gateway was later split out into its own independent compose
# project (gateway/compose.yml) so the public gateway is never coupled to
# application deployment/rollback (Deploy Agent Phase 2B: "keeps the
# production nginx gateway independent from application deployment").
# host.docker.internal:host-gateway now lives there, not in MESFlow's own
# app-level compose.yml.
GATEWAY_COMPOSE = Path("gateway/compose.yml").read_text()


def test_agent_subdomain_proxy_contract():
    assert "server_name agent.mesflow.net;" in CONF
    assert "upstream mesflow_agent_backend" in CONF
    assert "server host.docker.internal:8090;" in CONF
    assert "proxy_pass http://mesflow_agent_backend;" in CONF
    assert "proxy_set_header Upgrade $http_upgrade;" in CONF
    assert "proxy_read_timeout 3600s;" in CONF


def test_linux_host_gateway_is_available_to_nginx():
    assert '"host.docker.internal:host-gateway"' in GATEWAY_COMPOSE


def test_agent_http_redirects_to_https():
    assert "return 301 https://agent.mesflow.net$request_uri;" in CONF


def test_release_version_is_synced():
    current = Path("VERSION.txt").read_text().strip()
    assert f"mesflow-app:{current}" in COMPOSE
