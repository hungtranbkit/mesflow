#!/usr/bin/env python3
"""Prepare the TEST gateway's exact root override; output must pass nginx -t.

Usage: prepare-public-root-nginx.py existing.conf candidate.conf
Does not deploy, reload, or modify the source config. Only accepts the known
HTTP + HTTPS showcase layout, so unexpected drift fails closed.
"""
import sys
from pathlib import Path

MARKER = '    # Public showcase only; independent of application auth and business data.\n'
HTTP = '''    # Public root; keep login and all business routes on the backend.
    location = / {
      if ($host != mesflow.net) { return 404; }
      return 301 https://mesflow.net/;
    }

'''
HTTPS = '''    # Public product-only support service; never forward auth or cookies.
    location = /support/chat {
      if ($host != mesflow.net) { return 404; }
      limit_except POST { deny all; }
      client_max_body_size 256;
      proxy_pass http://mesflow-public-support:8088;
      proxy_set_header Host mesflow.net;
      proxy_set_header Cookie "";
      proxy_set_header Authorization "";
      proxy_set_header X-Support-Client-IP $remote_addr;
      proxy_connect_timeout 2s;
      proxy_read_timeout 27s;
      proxy_hide_header Set-Cookie;
      add_header Cache-Control "no-store" always;
    }

    # Public root; keep login and all business routes on the backend.
    location = / {
      if ($host != mesflow.net) { return 404; }
      alias /usr/share/nginx/html/mesflow-showcase/welcome.html;
      default_type text/html;
      charset utf-8;
      add_header X-Content-Type-Options nosniff always;
      add_header X-Frame-Options SAMEORIGIN always;
      add_header Referrer-Policy strict-origin-when-cross-origin always;
      add_header Cache-Control "no-cache" always;
      limit_except GET { deny all; }
    }

'''


def prepare(config):
    if config.count(MARKER) != 2 or '    # Public root;' in config:
        raise ValueError('Unexpected gateway layout: inspect existing root/showcase routing first')
    first, second, third = config.split(MARKER)
    if 'listen 80 default_server;' not in first or 'listen 443 ssl default_server;' not in second:
        raise ValueError('Unexpected HTTP/HTTPS server order')
    return first + HTTP + MARKER + second + HTTPS + MARKER + third


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(prepare(Path(sys.argv[1]).read_text()))
