"""ESP kiosk UX-hardening pass (2026-08-26), §2 "Server Environment
Visibility" -- real, confirmed gap found reading app/mesflow/web/kiosk_v2.py
top to bottom: none of /health, /bootstrap, /heartbeat, /state, /events ever
returned environment/server_role/version, so a device had no way to know
whether it was talking to DEV/TEST/PROD (and therefore no way to ever detect
a server mismatch). Fixed by adding the exact same three fields
app/mesflow/web/app.py's /api/system/ready already returns, read the exact
same way (settings.environment/settings.server_role/mesflow.__version__),
to /health and /bootstrap.
"""
from __future__ import annotations

import uuid

import pytest
import requests

from mesflow import __version__
from mesflow.core.config import settings

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def test_health_reports_server_identity():
    r = requests.get(f'{BASE_URL}/api/kiosk/v2/health', timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['environment'] == settings.environment, body
    assert body['version'] == __version__, body
    # server_role is None when unset (e.g. bare local dev with no SERVER_ROLE
    # env var) -- never an empty string a device might render as a blank label.
    assert body['server_role'] == (settings.server_role or None), body


def test_bootstrap_reports_server_identity():
    device = f'V2-ENV-{uuid.uuid4().hex[:10]}'
    r = requests.post(f'{BASE_URL}/api/kiosk/v2/bootstrap',
                       json={'device_id': device, 'hardware_id': device}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['accepted'] is True
    assert body['environment'] == settings.environment, body
    assert body['version'] == __version__, body
    assert body['server_role'] == (settings.server_role or None), body
    # Every existing field must still be present -- this is a pure addition,
    # never a replacement of the protocol.
    assert body['protocol']['accepted_version'] == 1
    assert 'desired' in body and 'ui_bundle_version' in body['desired']
