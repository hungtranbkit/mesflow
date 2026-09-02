"""Regression coverage for the RBAC self-heal fix (found live, 2026-09-02):
local DEV's rbac_permissions/rbac_role_permissions were found completely
empty -- every user, including admin, silently got permissions:[] and no
page would open. Root cause: Alembic migrations 0025/0028/0029/0037/0043
only ever run their INSERTs the ONE time each revision is first applied;
once recorded as applied, `alembic upgrade head` on every future boot
skips them even if the DATA is later lost by some out-of-band event --
unlike users (seed-admin/seed-default-users/seed-super-admin, which DO
idempotently re-verify on every boot).

This test simulates exactly that incident against the real test database
(the same one `api`/`db` already use, already fully seeded by the real
entrypoint's `seed-rbac` step) -- deletes the RBAC tables' contents, then
confirms RBACRepository().seed() restores the full, correct set. Never
touches a live/production database (session-scoped `db` fixture, same
throwaway compose.test.yml stack every other integration test in this
file uses).
"""
import os
import sys
from pathlib import Path

import pytest

# Import the app package the same way the real entrypoint does (mounted
# under /app inside the tests image; add REPO_ROOT/app to sys.path when
# running this file directly against a host venv).
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / 'app'))
os.environ.setdefault('DATABASE_URL', os.environ.get('DATABASE_URL', ''))


@pytest.fixture
def clean_rbac_state(db):
    """Delete rbac_role_permissions/rbac_permissions/rbac_roles (children
    first, FK order), simulating the real incident, then restore the
    known-good state afterward regardless of test outcome -- this must
    never leave the shared test database (other tests in this session
    depend on RBAC being correctly seeded) in a broken state."""
    with db.cursor() as cur:
        cur.execute('DELETE FROM rbac_role_permissions')
        cur.execute('DELETE FROM rbac_permissions')
        cur.execute('DELETE FROM rbac_roles')
    yield
    from mesflow.db.repositories.rbac import RBACRepository
    RBACRepository().seed()


def test_seed_restores_full_rbac_state_after_simulated_data_loss(db, clean_rbac_state):
    from mesflow.db.repositories.rbac import RBACRepository, SEED_ROLES, SEED_PERMISSIONS, SEED_ROLE_PERMISSIONS

    with db.cursor() as cur:
        cur.execute('SELECT count(*) AS n FROM rbac_roles')
        assert cur.fetchone()['n'] == 0
        cur.execute('SELECT count(*) AS n FROM rbac_permissions')
        assert cur.fetchone()['n'] == 0
        cur.execute('SELECT count(*) AS n FROM rbac_role_permissions')
        assert cur.fetchone()['n'] == 0

    RBACRepository().seed()

    with db.cursor() as cur:
        cur.execute('SELECT count(*) AS n FROM rbac_roles')
        assert cur.fetchone()['n'] == len(SEED_ROLES)
        cur.execute('SELECT count(*) AS n FROM rbac_permissions')
        assert cur.fetchone()['n'] == len(SEED_PERMISSIONS)
        cur.execute('SELECT count(*) AS n FROM rbac_role_permissions')
        assert cur.fetchone()['n'] == len(SEED_ROLE_PERMISSIONS)
        # The exact incident symptom: admin must come back with a real,
        # non-empty permission set, not permissions:[].
        cur.execute("SELECT permission_code FROM rbac_role_permissions WHERE role_code='admin'")
        admin_perms = {row['permission_code'] for row in cur.fetchall()}
        assert len(admin_perms) > 0
        assert 'overview.view' in admin_perms


def test_seed_is_idempotent_never_duplicates_or_errors(db, clean_rbac_state):
    """Calling seed() twice in a row (e.g. two container starts without an
    intervening loss) must be a pure no-op the second time -- ON CONFLICT
    DO NOTHING, not an error, not duplicate rows."""
    from mesflow.db.repositories.rbac import RBACRepository, SEED_ROLES

    repo = RBACRepository()
    repo.seed()
    repo.seed()  # must not raise, must not duplicate

    with db.cursor() as cur:
        cur.execute('SELECT count(*) AS n FROM rbac_roles')
        assert cur.fetchone()['n'] == len(SEED_ROLES)


def test_seed_never_overwrites_a_manually_customized_role(db, clean_rbac_state):
    """seed() must only ADD missing rows, never revert a real admin's own
    customization (e.g. Users & Roles -> edit a role's permission set via
    RBACRepository.set_role_permissions) back to the canonical default."""
    from mesflow.db.repositories.rbac import RBACRepository

    repo = RBACRepository()
    repo.seed()
    repo.set_role_permissions('viewer', ['overview.view'])  # deliberately narrowed

    repo.seed()  # must not restore viewer's original, wider permission set

    with db.cursor() as cur:
        cur.execute("SELECT permission_code FROM rbac_role_permissions WHERE role_code='viewer'")
        perms = {row['permission_code'] for row in cur.fetchall()}
    assert perms == {'overview.view'}
