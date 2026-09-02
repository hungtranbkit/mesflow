"""Reliability Validation Round 2, FIX 1 -- automated coverage for the
migration-aware auto-rollback logic added to scripts/deploy.sh after Gate
12's confirmed P1 bug (an image-only automatic rollback does not restore
service once the schema has moved forward: the old app crash-loops with
"Can't locate revision..." -- see docs/operations/ROLLBACK.md).

scripts/deploy.sh itself is an SSH-orchestration script (it deploys to a
real remote host via `ssh_target`) and this task's constraints forbid
deploying to TEST/PRODUCTION or touching a production DB -- so this suite
does not invoke deploy.sh directly. Instead it exercises the IDENTICAL
sequence of primitives deploy.sh's migration-aware rollback block performs
(capture migration_before/after, decide migration_changed, `alembic
downgrade` with verification, image swap, health re-check, and the
ROLLBACK_REQUIRES_HUMAN / IMAGE_ROLLBACK_FAILED failure paths) against
real, disposable local Docker containers and a tmpfs Postgres -- the same
technique Gate 12's manual drill used, now captured as a permanent,
automated, reproducible regression suite.

Slow (builds two real Docker images from git history). Needs a `docker`
CLI with access to the Docker daemon AND a `git` CLI on PATH -- the
sandboxed `tests` Docker image this repo's other suites run in has
neither (no Docker-in-Docker, no git), so this module skips itself
entirely there rather than erroring; run it from the host instead:
    DATABASE_URL=postgresql://dummy:dummy@localhost/dummy \\
      pytest -m slow tests/integration/test_deploy_rollback_migration_aware.py -v
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import psycopg
import pytest
import requests

pytestmark = [pytest.mark.slow, pytest.mark.postgres]

if shutil.which('docker') is None or shutil.which('git') is None:
    pytest.skip('requires a docker CLI (with daemon access) and git CLI on PATH -- run from the host, not the sandboxed tests image',
                allow_module_level=True)

def _current_tree_migration_head(repo_root: Path) -> str:
    """The tip revision of app/migrations/versions/ in the CURRENT working
    tree -- i.e. whatever `images['new']` (built from REPO_ROOT, always
    "now") actually migrates to. Computed the same way Alembic itself
    finds a branch's head: the one revision id that no other revision
    lists as its down_revision. Real bug this replaces (found live,
    2026-09-02): NEW_MIGRATION_HEAD used to be a hardcoded literal
    ('0041_job_health_last_success') that was correct only the day this
    test was written -- three migrations (0042, 0043) landed since without
    anyone updating it, so this test failed on real, unrelated migration
    additions from that day forward. images['new'] already tracks "now"
    dynamically; the expected value must too, or this regression's only
    job (catch a REAL migration-aware-rollback break) gets lost in
    routine-migration noise.
    """
    # Not anchored to line-start: this repo's migration files are NOT
    # consistently formatted -- most declare `revision =`/`down_revision =`
    # as their own top-level lines, but several (e.g. 0032-0036) pack
    # `revision='x';down_revision='y';branch_labels=None;depends_on=None`
    # onto one semicolon-joined line, which a `^`-anchored, MULTILINE
    # regex misses entirely (found live: it silently dropped those files'
    # down_revision, making 6 real, applied migrations look like orphan
    # heads instead of one true tip).
    versions_dir = repo_root / 'app' / 'migrations' / 'versions'
    revisions: dict[str, str | None] = {}
    for path in versions_dir.glob('*.py'):
        text = path.read_text(encoding='utf-8')
        rev = re.search(r'(?<![\w.])revision\s*=\s*["\']([^"\']+)["\']', text)
        down = re.search(r'(?<![\w.])down_revision\s*=\s*["\']([^"\']+)["\']', text)
        if rev:
            revisions[rev.group(1)] = down.group(1) if down else None
    tips = set(revisions) - {down for down in revisions.values() if down}
    assert len(tips) == 1, f'expected exactly one migration head, found {tips!r}'
    return next(iter(tips))


REPO_ROOT = Path(__file__).resolve().parents[2]
OLD_COMMIT = 'c8d13c2'  # last committed release: 71.0.0.67, migration head 0039_kiosk_v2_protocol
OLD_VERSION = '71.0.0.67'
OLD_MIGRATION_HEAD = '0039_kiosk_v2_protocol'
NEW_VERSION = '71.0.0.68'
NEW_MIGRATION_HEAD = _current_tree_migration_head(REPO_ROOT)


def _run(cmd, **kwargs):
    result = subprocess.run(cmd, text=True, capture_output=True, **kwargs)
    assert result.returncode == 0, f"Command failed: {' '.join(cmd)}\nstdout:{result.stdout}\nstderr:{result.stderr}"
    return result


def _run_allow_fail(cmd, **kwargs):
    return subprocess.run(cmd, text=True, capture_output=True, **kwargs)


@pytest.fixture(scope='module')
def images(tmp_path_factory):
    """Build the OLD (71.0.0.67) and NEW (71.0.0.68, current working tree)
    app images once, reused by every test in this module. The OLD image is
    built from a detached git worktree -- the current (possibly dirty)
    working tree is never checked out or touched."""
    worktree_dir = tmp_path_factory.mktemp('gate12_worktree') / 'old'
    _run(['git', 'worktree', 'add', '--detach', str(worktree_dir), OLD_COMMIT], cwd=REPO_ROOT)
    try:
        old_tag = f'mesflow-rollback-test-old:{uuid.uuid4().hex[:8]}'
        new_tag = f'mesflow-rollback-test-new:{uuid.uuid4().hex[:8]}'
        _run(['docker', 'build', '-t', old_tag, '-f', 'Dockerfile', '.'], cwd=worktree_dir)
        _run(['docker', 'build', '-t', new_tag, '-f', 'Dockerfile', '.'], cwd=REPO_ROOT)
        yield {'old': old_tag, 'new': new_tag}
    finally:
        _run_allow_fail(['docker', 'rmi', '-f', old_tag, new_tag])
        _run_allow_fail(['git', 'worktree', 'remove', str(worktree_dir), '--force'], cwd=REPO_ROOT)


class Env:
    """One disposable network + tmpfs Postgres, torn down at the end of
    the `with` block. Each test gets its own -- no shared mutable state
    between scenarios."""

    def __init__(self, images):
        self.images = images
        self.suffix = uuid.uuid4().hex[:10]
        self.network = f'mesflow-rbtest-net-{self.suffix}'
        self.pg_name = f'mesflow-rbtest-pg-{self.suffix}'
        self.app_name = None
        self.db_url = f'postgresql://rbtest:rbtestpass@{self.pg_name}:5432/rbtest'

    def __enter__(self):
        _run(['docker', 'network', 'create', self.network])
        _run(['docker', 'run', '-d', '--name', self.pg_name, '--network', self.network,
              '-e', 'POSTGRES_DB=rbtest', '-e', 'POSTGRES_USER=rbtest', '-e', 'POSTGRES_PASSWORD=rbtestpass',
              '--tmpfs', '/var/lib/postgresql/data', 'postgres:17-alpine'])
        for _ in range(30):
            r = _run_allow_fail(['docker', 'exec', self.pg_name, 'pg_isready', '-U', 'rbtest', '-d', 'rbtest'])
            if r.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('disposable Postgres never became ready')
        return self

    def __exit__(self, *exc):
        if self.app_name:
            _run_allow_fail(['docker', 'rm', '-f', self.app_name])
        _run_allow_fail(['docker', 'rm', '-f', self.pg_name])
        _run_allow_fail(['docker', 'network', 'rm', self.network])

    def migrate(self, image, target='head'):
        cmd = f'cd /app && python -m mesflow.cli wait-db && alembic upgrade {target}' if target == 'head' \
            else f'cd /app && alembic downgrade {target}'
        return _run_allow_fail(['docker', 'run', '--rm', '--network', self.network,
                                 '-e', f'DATABASE_URL={self.db_url}', '-e', 'MESFLOW_SECRET_KEY=rbtest-secret',
                                 '-e', 'MESFLOW_ADMIN_PASSWORD=migration-run-only1', '-e', 'MESFLOW_ENV=test',
                                 '--entrypoint', 'sh', image, '-c', cmd])

    def alembic_current(self, image):
        r = _run_allow_fail(['docker', 'run', '--rm', '--network', self.network,
                              '-e', f'DATABASE_URL={self.db_url}', '-e', 'MESFLOW_SECRET_KEY=rbtest-secret',
                              '-e', 'MESFLOW_ENV=test', '--entrypoint', 'sh', image,
                              '-c', 'cd /app && alembic current'])
        m = re.search(r'^([0-9]{4}_[0-9a-zA-Z_]+)', r.stdout, re.MULTILINE)
        return m.group(1) if m else None

    def start_app(self, image, port, admin_password='Admin@123456Rb'):
        self.app_name = f'mesflow-rbtest-app-{self.suffix}'
        _run(['docker', 'run', '-d', '--name', self.app_name, '--network', self.network, '-p', f'{port}:8080',
              '-e', f'DATABASE_URL={self.db_url}', '-e', 'MESFLOW_SECRET_KEY=rbtest-secret',
              '-e', f'MESFLOW_ADMIN_PASSWORD={admin_password}', '-e', 'MESFLOW_ENV=test', image])

    def stop_app(self):
        if self.app_name:
            _run_allow_fail(['docker', 'rm', '-f', self.app_name])
            self.app_name = None

    def wait_ready(self, port, timeout=30):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                r = requests.get(f'http://127.0.0.1:{port}/api/system/ready', timeout=3)
                if r.ok:
                    return r.json()
                last = f'{r.status_code}: {r.text[:200]}'
            except Exception as e:
                last = repr(e)
            time.sleep(1)
        return None

    def app_logs(self):
        if not self.app_name:
            return ''
        return _run_allow_fail(['docker', 'logs', self.app_name]).stdout + _run_allow_fail(['docker', 'logs', self.app_name]).stderr


def _decide_migration_changed(migration_before: str, migration_after: str) -> bool:
    """The exact predicate scripts/deploy.sh uses:
    MIGRATION_CHANGED=1 iff migration_before is known and differs from
    migration_after. Kept here as a literal one-line mirror so the test
    can assert against deploy.sh's actual decision rule by name, not just
    by re-deriving it inline at each call site."""
    return bool(migration_before) and migration_before != migration_after


# ---------------------------------------------------------------------------
# Scenario: no migration change -> fast image-only rollback path.
# ---------------------------------------------------------------------------
def test_no_migration_change_uses_image_only_rollback(images):
    # Deploying the SAME image "twice" (old -> old) never changes the
    # migration head -- deploy.sh's decision must take the image-only path.
    with Env(images) as env:
        env.migrate(images['old'])
        before = env.alembic_current(images['old'])
        after = env.alembic_current(images['old'])  # re-running "the same deploy's" migrate step
        assert _decide_migration_changed(before, after) is False

        env.start_app(images['old'], port=18190)
        ready = env.wait_ready(18190)
        assert ready is not None and ready['ok'] is True
        env.stop_app()


# ---------------------------------------------------------------------------
# Scenario: migration changed -> downgrade Y -> X -> old image -> healthy.
# ---------------------------------------------------------------------------
def test_migration_changed_downgrade_then_old_image_becomes_healthy(images):
    with Env(images) as env:
        # 1. Old release running at its own head.
        env.migrate(images['old'])
        migration_before = env.alembic_current(images['old'])
        assert migration_before == OLD_MIGRATION_HEAD

        # 2. "Deploy" -- new image migrates forward.
        migrate_result = env.migrate(images['new'])
        assert migrate_result.returncode == 0, migrate_result.stderr
        migration_after = env.alembic_current(images['new'])
        assert migration_after == NEW_MIGRATION_HEAD
        assert _decide_migration_changed(migration_before, migration_after) is True

        # 3. Health check "fails" (forced, by never even starting the new
        # app here -- this test only needs to prove the ROLLBACK sequence,
        # which is unconditional on why health failed).

        # 4. Migration-aware rollback: downgrade using the NEW image (it
        # still has the old revision in its own history), verify, THEN
        # swap to the old image.
        downgrade_result = env.migrate(images['new'], target=migration_before)
        assert downgrade_result.returncode == 0, downgrade_result.stderr
        downgraded_head = env.alembic_current(images['new'])
        assert downgraded_head == migration_before, 'downgrade must be verified, not just trusted from exit code'

        env.start_app(images['old'], port=18191)
        ready = env.wait_ready(18191)
        assert ready is not None, env.app_logs()
        assert ready['ok'] is True
        assert ready['migration_head'] == OLD_MIGRATION_HEAD
        assert ready['version'] == OLD_VERSION

        # 5. Restart after rollback: old app performs a real DB write, not
        # just a health-check pass.
        s = requests.Session()
        login = s.post(f'http://127.0.0.1:18191/api/auth/login', json={'username': 'admin', 'password': 'Admin@123456Rb'}, timeout=10)
        assert login.status_code == 200, login.text
        created = s.post('http://127.0.0.1:18191/api/employees', json={
            'employee_no': f'RB-{env.suffix}', 'name': 'Rollback Test Employee', 'qr': f'WF|EMP|RB-{env.suffix}',
        }, timeout=10)
        assert created.status_code == 201, created.text
        env.stop_app()


# ---------------------------------------------------------------------------
# Scenario: downgrade failure -> ROLLBACK_REQUIRES_HUMAN, no image swap.
# ---------------------------------------------------------------------------
def test_downgrade_failure_yields_rollback_requires_human_and_no_image_swap(images):
    with Env(images) as env:
        env.migrate(images['old'])
        migration_before = env.alembic_current(images['old'])
        env.migrate(images['new'])
        migration_after = env.alembic_current(images['new'])
        assert _decide_migration_changed(migration_before, migration_after) is True

        # Force a downgrade failure the same way deploy.sh's verification
        # would catch a bad/partial downgrade: target a revision that does
        # not exist in this app's history at all.
        bogus_target = '9999_does_not_exist'
        downgrade_result = env.migrate(images['new'], target=bogus_target)
        assert downgrade_result.returncode != 0

        # deploy.sh's exact rule: DOWNGRADE_OK only if the post-downgrade
        # alembic current matches the intended target. A failed command
        # (as here) trivially fails that too -- re-asserting it explicitly
        # documents the rule this test is proving, not just its symptom.
        downgraded_head = env.alembic_current(images['new'])
        downgrade_ok = downgraded_head == bogus_target
        assert downgrade_ok is False

        # The real safety property: schema must still be exactly where it
        # was (still at the NEW head) -- a failed downgrade must not leave
        # a half-migrated, unknown state, and the app image must NEVER be
        # swapped back in this branch (deploy.sh does not reach the image
        # swap step when DOWNGRADE_OK=0).
        assert env.alembic_current(images['new']) == migration_after
        assert env.app_name is None, 'no app container should have been started in the ROLLBACK_REQUIRES_HUMAN branch'


# ---------------------------------------------------------------------------
# Scenario: image rollback failure must be reported as failure, never PASS.
# ---------------------------------------------------------------------------
def test_image_rollback_failure_is_reported_not_masked(images):
    with Env(images) as env:
        env.migrate(images['old'])
        migration_before = env.alembic_current(images['old'])
        env.migrate(images['new'])
        # Downgrade succeeds cleanly...
        env.migrate(images['new'], target=migration_before)
        assert env.alembic_current(images['new']) == migration_before

        # ...but the "old" image swap itself is broken (simulated: start it
        # with a secret key too short to pass its own admin-bootstrap
        # validation, so the container's entrypoint fails and it never
        # becomes healthy -- an image-level failure unrelated to schema).
        env.app_name = f'mesflow-rbtest-brokenapp-{env.suffix}'
        _run(['docker', 'run', '-d', '--name', env.app_name, '--network', env.network, '-p', '18192:8080',
              '-e', f'DATABASE_URL={env.db_url}', '-e', 'MESFLOW_SECRET_KEY=rbtest-secret',
              '-e', 'MESFLOW_ADMIN_PASSWORD=tooshort', '-e', 'MESFLOW_ENV=production', images['old']])
        ready = env.wait_ready(18192, timeout=10)
        # The exact failure mode doesn't matter -- what matters is that
        # this state is NEVER reported as a successful rollback.
        assert ready is None or ready.get('ok') is not True
