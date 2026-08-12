# RBAC migration 0025

## Production safety

Migration `0025_rbac_permissions` is additive. It creates three RBAC metadata tables only and does not rewrite `users`, passwords, PostgreSQL runtime data, PO, sessions, material-flow ledgers, or production aggregates. Existing users preserve their role values.

Before production migration, take the normal PostgreSQL backup and record the current Alembic head. Run `alembic upgrade head` only through the approved deployment path.

Default role accounts are **not** automatically created in production. To seed manager/supervisor/operator/viewer on a fresh/test installation, set `MESFLOW_SEED_DEFAULT_USERS=1` plus each password environment variable. Existing accounts are preserved and passwords are never overwritten.

Admin remains immutable full-access.
