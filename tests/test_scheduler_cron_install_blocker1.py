"""Codex audit Blocker 1: the scheduler installer/verifier scripts must be
idempotent, upgrade-safe, capability-safe, and observable -- proven here
against a FAKE `crontab` shim (a local file, never the real host/CI
crontab) so this is safe to run anywhere, including this dev machine.

Also proves scripts/deploy.sh actually invokes both installers plus the
verifier and folds the verifier's result into its PASS/FAIL decision --
the actual Blocker 1 bug ("code present, cron missing, scheduler never
runs") was that nothing in the real deploy path called these scripts at
all.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.static

ROOT = Path(__file__).resolve().parents[1]
RECONCILE = ROOT / 'scripts/install-reconcile-cron.sh'
LOG_RETENTION = ROOT / 'scripts/install-log-retention-cron.sh'
VERIFY = ROOT / 'scripts/verify-scheduler-cron.sh'
DEPLOY = ROOT / 'scripts/deploy.sh'


def _fake_crontab_bin(bindir: Path, store: Path) -> None:
    """A minimal `crontab` stand-in: `crontab -l` prints `store` (empty if
    absent), `crontab -` reads stdin into `store`. Mirrors real crontab's
    exit-0-on-missing-crontab-for-user behavior via `store` simply not
    existing yet.

    `crontab -` writes to a TEMP file then renames it into place, exactly
    like the real vixie-cron/cronie `crontab -` implementation -- this is
    what makes the standard `crontab -l | ... | crontab -` idiom (used by
    both installer scripts) safe against the reading and writing ends of a
    shell pipeline touching the same file concurrently (all pipeline
    stages run as parallel processes). A naive `cat > "$STORE"` here would
    truncate the file in-place the instant it opens, racing the OTHER side
    of the same pipeline that is still trying to read it -- a bug in this
    test double, not in the scripts under test.
    """
    script = bindir / 'crontab'
    script.write_text(
        '#!/usr/bin/env sh\n'
        'set -eu\n'
        f'STORE="{store}"\n'
        'if [ "${1:-}" = "-l" ]; then\n'
        '  [ -f "$STORE" ] && cat "$STORE" || exit 1\n'
        '  exit 0\n'
        'fi\n'
        'if [ "${1:-}" = "-" ]; then\n'
        '  TMP="$STORE.tmp.$$"\n'
        '  cat > "$TMP"\n'
        '  mv "$TMP" "$STORE"\n'
        '  exit 0\n'
        'fi\n'
        'echo "fake crontab: unsupported args: $*" >&2\n'
        'exit 2\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def _env_with_fake_crontab(tmp_path: Path, store: Path, extra: dict | None = None) -> dict:
    bindir = tmp_path / 'bin'
    bindir.mkdir(exist_ok=True)
    _fake_crontab_bin(bindir, store)
    env = dict(os.environ)
    env['PATH'] = f'{bindir}:{env["PATH"]}'
    env['MESFLOW_ROOT'] = str(tmp_path)
    if extra:
        env.update(extra)
    return env


def test_clean_install_creates_both_job_lines(tmp_path):
    store = tmp_path / 'crontab.txt'
    env = _env_with_fake_crontab(tmp_path, store)
    r = subprocess.run(['sh', str(RECONCILE)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    content = store.read_text()
    assert 'reconcile-exceptions' in content
    assert 'reconcile-shift-sessions' in content
    assert content.count('reconcile-exceptions') == 1
    assert content.count('reconcile-shift-sessions') == 1


def test_reinstall_is_idempotent_no_duplicates(tmp_path):
    store = tmp_path / 'crontab.txt'
    env = _env_with_fake_crontab(tmp_path, store)
    for _ in range(3):
        r = subprocess.run(['sh', str(RECONCILE)], env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    content = store.read_text()
    assert content.count('reconcile-exceptions') == 1
    assert content.count('reconcile-shift-sessions') == 1


def test_duplicate_invocation_same_process_twice_in_a_row(tmp_path):
    store = tmp_path / 'crontab.txt'
    env = _env_with_fake_crontab(tmp_path, store)
    subprocess.run(['sh', str(RECONCILE)], env=env, check=True, capture_output=True, text=True)
    r2 = subprocess.run(['sh', str(RECONCILE)], env=env, capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert store.read_text().count('reconcile-shift-sessions') == 1


def test_upgrade_changes_schedule_without_duplicating(tmp_path):
    store = tmp_path / 'crontab.txt'
    env = _env_with_fake_crontab(tmp_path, store)
    subprocess.run(['sh', str(RECONCILE)], env=env, check=True, capture_output=True, text=True)
    assert '*/5 * * * *' in store.read_text()

    env2 = dict(env)
    env2['MESFLOW_SHIFT_RECONCILE_CRON'] = '*/2 * * * *'
    r = subprocess.run(['sh', str(RECONCILE)], env=env2, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    content = store.read_text()
    assert content.count('reconcile-shift-sessions') == 1
    assert '*/2 * * * * cd' in content


def test_install_preserves_unrelated_existing_crontab_entries(tmp_path):
    store = tmp_path / 'crontab.txt'
    store.write_text('0 3 * * * /usr/bin/some-other-unrelated-job.sh\n')
    env = _env_with_fake_crontab(tmp_path, store)
    subprocess.run(['sh', str(RECONCILE)], env=env, check=True, capture_output=True, text=True)
    content = store.read_text()
    assert 'some-other-unrelated-job.sh' in content
    assert 'reconcile-exceptions' in content


def test_app_service_name_is_parameterized_not_hardcoded(tmp_path):
    """Regression for a real latent bug found while fixing Blocker 1: the
    cron line hardcoded `docker compose exec -T mesflow ...`, which is
    correct for production's compose service name but WRONG for prodtest
    (mesflow-prodtest-app) -- a cron job installed via this route on
    prodtest would silently target a service that doesn't exist."""
    store = tmp_path / 'crontab.txt'
    env = _env_with_fake_crontab(tmp_path, store, extra={'MESFLOW_APP_SERVICE': 'mesflow-prodtest-app'})
    subprocess.run(['sh', str(RECONCILE)], env=env, check=True, capture_output=True, text=True)
    content = store.read_text()
    assert 'docker compose exec -T mesflow-prodtest-app' in content
    assert 'docker compose exec -T mesflow ' not in content


def test_missing_cron_capability_fails_clearly(tmp_path):
    # A PATH with the ordinary tools the script needs (grep, cat, mv --
    # `sh` itself is invoked by absolute path below, no lookup needed) but
    # deliberately NO `crontab` anywhere reachable.
    import shutil
    curated = tmp_path / 'curatedbin'
    curated.mkdir()
    for tool in ('grep', 'cat', 'mv'):
        src = shutil.which(tool)
        assert src, f'{tool} not found on this host -- cannot build curated PATH for the test'
        (curated / tool).symlink_to(src)
    env = dict(os.environ)
    env['PATH'] = str(curated)
    env['MESFLOW_ROOT'] = str(tmp_path)
    r = subprocess.run(['/bin/sh', str(RECONCILE)], env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert 'crontab' in (r.stderr + r.stdout).lower()


def test_cron_install_failure_propagates_nonzero(tmp_path):
    """A `crontab -` that itself fails (e.g. cron daemon rejects the
    input/host policy blocks it) must make the installer exit non-zero, not
    silently report success."""
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    failing = bindir / 'crontab'
    failing.write_text('#!/usr/bin/env sh\nexit 1\n')
    failing.chmod(failing.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ)
    env['PATH'] = f'{bindir}:{env["PATH"]}'
    env['MESFLOW_ROOT'] = str(tmp_path)
    r = subprocess.run(['sh', str(RECONCILE)], env=env, capture_output=True, text=True)
    assert r.returncode != 0


def test_verify_scheduler_cron_passes_after_install_fails_before(tmp_path):
    store = tmp_path / 'crontab.txt'
    env = _env_with_fake_crontab(tmp_path, store, extra={'MESFLOW_LOG_RETENTION_HOST_CRON': '0'})

    before = subprocess.run(['sh', str(VERIFY)], env=env, capture_output=True, text=True)
    assert before.returncode != 0
    assert 'MISSING' in before.stdout + before.stderr

    subprocess.run(['sh', str(RECONCILE)], env=env, check=True, capture_output=True, text=True)
    after = subprocess.run(['sh', str(VERIFY)], env=env, capture_output=True, text=True)
    assert after.returncode == 0, after.stdout + after.stderr


def test_verify_scheduler_cron_checks_log_retention_when_enabled(tmp_path):
    store = tmp_path / 'crontab.txt'
    env = _env_with_fake_crontab(tmp_path, store)  # MESFLOW_LOG_RETENTION_HOST_CRON defaults to "1"
    subprocess.run(['sh', str(RECONCILE)], env=env, check=True, capture_output=True, text=True)
    still_missing = subprocess.run(['sh', str(VERIFY)], env=env, capture_output=True, text=True)
    assert still_missing.returncode != 0
    assert 'log_retention' in still_missing.stdout + still_missing.stderr

    subprocess.run(['sh', str(LOG_RETENTION)], env=env, check=True, capture_output=True, text=True)
    now_ok = subprocess.run(['sh', str(VERIFY)], env=env, capture_output=True, text=True)
    assert now_ok.returncode == 0, now_ok.stdout + now_ok.stderr


def test_deploy_sh_installs_and_verifies_scheduler_before_reporting_pass():
    """Static contract check (no live remote deploy -- deploy.sh only talks
    to real prodtest/production hosts over SSH, out of scope for a
    sandboxed test run): proves the actual bug is fixed at the source
    level -- the normal deploy path now calls both installers AND the
    verifier, and folds the verifier's result into PASS."""
    text = DEPLOY.read_text(encoding='utf-8')
    assert 'install-reconcile-cron.sh' in text
    assert 'install-log-retention-cron.sh' in text
    assert 'verify-scheduler-cron.sh' in text
    assert 'SCHEDULER_OK' in text
    assert '[[ "$SCHEDULER_OK" == "1" ]] || PASS=0' in text
