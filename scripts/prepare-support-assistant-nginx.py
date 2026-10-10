#!/usr/bin/env python3
"""Upgrade only public support locations; preserve live report/app routes."""
import re
import sys
from pathlib import Path

PUBLIC = '''    # Shared public FAQ assets; no business/session context.
    location = /support/assistant.js {
      if ($host != mesflow.net) { return 404; }
      limit_except GET { deny all; }
      set $public_support_backend http://mesflow-public-support:8088;
      proxy_pass $public_support_backend;
      proxy_set_header Cookie "";
      proxy_set_header Authorization "";
      proxy_connect_timeout 2s;
      proxy_read_timeout 3s;
      proxy_hide_header Set-Cookie;
    }
    location = /support/knowledge {
      if ($host != mesflow.net) { return 404; }
      limit_except GET { deny all; }
      set $public_support_backend http://mesflow-public-support:8088;
      proxy_pass $public_support_backend;
      proxy_set_header Cookie "";
      proxy_set_header Authorization "";
      proxy_connect_timeout 2s;
      proxy_read_timeout 3s;
      proxy_hide_header Set-Cookie;
    }

'''
PATTERN = r'    location = /support/chat \{\n.*?^    \}\n'

def prepare(config):
    matches=list(re.finditer(PATTERN,config,re.M|re.S))
    if len(matches)!=1 or 'location = /support/assistant.js' in config:
        raise ValueError('Unexpected support layout')
    match=matches[0];old=match[0]
    if 'proxy_set_header Cookie "";' not in old or 'proxy_set_header Authorization "";' not in old:
        raise ValueError('Missing auth isolation')
    new=old.replace('client_max_body_size 256;', 'client_max_body_size 1024;').replace('proxy_read_timeout 27s;', 'proxy_read_timeout 11s;')
    if new==old: raise ValueError('Unexpected support limits')
    return config[:match.start()]+PUBLIC+new+config[match.end():]

if __name__=='__main__':
    Path(sys.argv[2]).write_text(prepare(Path(sys.argv[1]).read_text()))
