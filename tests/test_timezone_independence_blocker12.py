"""Codex audit Blocker 12 -- MESFlow business-calendar logic must be
explicit about its timezone (Asia/Ho_Chi_Minh via settings.timezone_name /
core.time_policy.site_zone()), never incidentally correct because the host
OS locale happens to also be UTC+7. No PostgreSQL needed -- pure process/
source-level checks."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.static

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / 'app'


def test_no_host_local_timezone_calls_in_business_logic():
    """Regression for a real bug found and fixed during this audit:
    OfflineSyncRepository.snapshot() used to build `generated_at` via
    `datetime.now().astimezone()` -- the host/container OS-local timezone
    (whatever `TZ` happens to be), not an explicit business timezone. Only
    "worked" because every compose file currently sets
    TZ=Asia/Ho_Chi_Minh. Scans every .py file under app/mesflow for the
    same class of mistake (bare `datetime.now()` with no tz argument,
    `.astimezone()` with no argument, `date.today()`/`datetime.today()`)
    so a new one can't quietly reappear."""
    offenders = []
    for path in APP_DIR.rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if 'datetime.now()' in line:
                # datetime.now() with literally no arguments (host-local, naive)
                offenders.append(f'{path.relative_to(ROOT)}:{lineno}: {stripped}')
            if '.astimezone()' in line:
                offenders.append(f'{path.relative_to(ROOT)}:{lineno}: {stripped}')
            if 'date.today()' in line or 'datetime.today()' in line:
                offenders.append(f'{path.relative_to(ROOT)}:{lineno}: {stripped}')
    assert offenders == [], (
        'Found host-local-timezone-dependent call(s) -- use '
        'mesflow.core.time_policy (utc_now()/site_now()/business_date()) instead:\n'
        + '\n'.join(offenders)
    )


def test_business_timezone_is_explicit_and_independent_of_host_tz():
    """Runs the SAME shift-resolution logic under two different process-level
    TZ env vars and asserts byte-identical results -- proves the business
    calendar does not read the host/container OS timezone at all (only
    zoneinfo.ZoneInfo(settings.timezone_name), which is env-var-driven via
    MESFLOW_TIMEZONE, defaulting to Asia/Ho_Chi_Minh explicitly in code,
    never derived from `TZ` or system tzdata)."""
    script = """
import json, sys
sys.path.insert(0, {app_dir!r})
from datetime import datetime, timezone
from mesflow.core.working_calendar import resolve_shift_window_for_datetime
from mesflow.core.config import settings

shifts = [{{
    'id': 1, 'code': 'DAY', 'timezone': 'Asia/Ho_Chi_Minh',
    'anchor_start': '08:00', 'anchor_end': '17:00', 'cross_midnight': False,
    'target_minutes': 480, 'working_weekdays': None,
}}]
moment = datetime(2026, 8, 10, 3, 0, tzinfo=timezone.utc)  # 10:00 in Ho Chi Minh
result = resolve_shift_window_for_datetime(moment, shifts)
shift, start, end = result
print(json.dumps({{
    'business_timezone': settings.timezone_name,
    'shift_code': shift['code'],
    'start': start.isoformat(),
    'end': end.isoformat(),
}}))
"""
    script = script.format(app_dir=str(APP_DIR))

    def run_with_tz(tz_value):
        env = dict(os.environ)
        env['TZ'] = tz_value
        env.pop('MESFLOW_TIMEZONE', None)  # exercise the code default, not an override
        # core.config.settings validates the DATABASE_URL scheme at import
        # time (no real connection attempted) -- a placeholder is enough,
        # this test never touches a database.
        env.setdefault('DATABASE_URL', 'postgresql://placeholder:placeholder@localhost/placeholder')
        env.setdefault('MESFLOW_ENV', 'test')
        env.setdefault('MESFLOW_SECRET_KEY', 'test-secret-key')
        r = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])

    result_bangkok = run_with_tz('Asia/Bangkok')
    result_utc = run_with_tz('UTC')
    result_ny = run_with_tz('America/New_York')

    for result in (result_bangkok, result_utc, result_ny):
        assert result['business_timezone'] == 'Asia/Ho_Chi_Minh'
    assert result_bangkok == result_utc == result_ny


def test_system_ready_endpoint_declares_business_timezone_source():
    """Static check that the /api/system/ready contract Blocker 12 asks for
    (explicit business/host/database timezone visibility) actually exists
    in source -- see test_system_ready_reports_timezones (integration) for
    the live-endpoint proof."""
    text = (APP_DIR / 'mesflow/web/app.py').read_text(encoding='utf-8')
    block = text[text.index("def ready()"):text.index("@app.get('/api/system/monitoring')")]
    assert 'business_timezone' in block
    assert 'host_timezone' in block
    assert 'database_timezone' in block
