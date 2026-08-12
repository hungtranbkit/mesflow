from pathlib import Path

CONF = Path("nginx/nginx.conf").read_text()

def test_kiosk_device_routes_are_proxied_on_http():
    required = [
        "location ^~ /api/kiosk/",
        "location ^~ /api/station/",
        "location = /api/lookup",
        "location ^~ /api/session/group/",
        "location = /api/demo-codes",
    ]
    for marker in required:
        assert marker in CONF
    assert "proxy_set_header X-Forwarded-Proto http;" in CONF

def test_other_http_still_redirects_https():
    assert "return 301 https://mesflow.net$request_uri;" in CONF
