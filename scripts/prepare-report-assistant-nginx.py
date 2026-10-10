#!/usr/bin/env python3
"""Add the report service to the verified TEST root config; no deployment."""
from pathlib import Path
import sys

MARKER = '    # Public root; keep login and all business routes on the backend.\n'
HTTP = '''    # Report assistant is HTTPS only.
    location = /reports {
      if ($host != mesflow.net) { return 404; }
      return 301 https://mesflow.net/reports;
    }
    location ^~ /reports-api/ { return 404; }

'''
HTTPS = '''    # Report service verifies the existing MES session and current RBAC.
    location = /reports {
      if ($host != mesflow.net) { return 404; }
      limit_except GET { deny all; }
      set $report_backend http://mesflow-report-assistant:8089;
      proxy_pass $report_backend;
      proxy_set_header Host mesflow.net;
      proxy_set_header Cookie "";
      proxy_set_header Authorization "";
      proxy_connect_timeout 2s;
      proxy_read_timeout 30s;
    }
    location ^~ /reports-api/ {
      if ($host != mesflow.net) { return 404; }
      limit_except GET POST { deny all; }
      client_max_body_size 2048;
      set $report_backend http://mesflow-report-assistant:8089;
      proxy_pass $report_backend;
      proxy_set_header Host mesflow.net;
      proxy_set_header Cookie $http_cookie;
      proxy_set_header Authorization "";
      proxy_set_header X-Report-Client-IP $remote_addr;
      proxy_connect_timeout 2s;
      proxy_read_timeout 30s;
      proxy_cache off;
      add_header Cache-Control "no-store, private" always;
    }

'''


def prepare(config):
    if config.count(MARKER) != 2 or 'location = /reports {' in config:
        raise ValueError('Unexpected gateway layout: inspect root/report routing first')
    first, second, third = config.split(MARKER)
    if 'listen 80 default_server;' not in first or 'listen 443 ssl default_server;' not in second:
        raise ValueError('Unexpected HTTP/HTTPS server order')
    return first + HTTP + MARKER + second + HTTPS + MARKER + third


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(prepare(Path(sys.argv[1]).read_text()))
