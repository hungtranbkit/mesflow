from pathlib import Path

CONF = Path("nginx/nginx.conf").read_text()
COMPOSE = Path("compose.yml").read_text()
VERSION = Path("VERSION.txt").read_text().strip()


def test_agent_subdomain_proxy_contract():
    assert "server_name agent.mesflow.net;" in CONF
    assert "upstream mesflow_agent_backend" in CONF
    assert "server host.docker.internal:8090;" in CONF
    assert "proxy_pass http://mesflow_agent_backend;" in CONF
    assert "proxy_set_header Upgrade $http_upgrade;" in CONF
    assert "proxy_read_timeout 3600s;" in CONF


def test_linux_host_gateway_is_available_to_nginx():
    assert '"host.docker.internal:host-gateway"' in COMPOSE


def test_agent_http_redirects_to_https():
    assert "return 301 https://agent.mesflow.net$request_uri;" in CONF


def test_release_version_is_synced():
    assert VERSION == "65.8.44.13"
    assert "mesflow-app:65.8.44.13" in COMPOSE
