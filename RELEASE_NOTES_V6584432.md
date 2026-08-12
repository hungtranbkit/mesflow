# MESFlow 65.8.44.32 — RBAC & Permission Matrix

## Added
- Role-based access control tables and additive Alembic migration `0025_rbac_permissions`.
- System roles: Admin, Manager, Supervisor, Operator, Viewer.
- Permission matrix by module/action.
- Sidebar hides tabs the logged-in role cannot view.
- Backend permission checks for user/role management and permission-aware compatibility for existing role decorators.
- System → Người dùng → Vai trò & phân quyền screen.
- Optional default role-account bootstrap via environment variables; disabled by default in production.

## Migration safety
- Does not delete/recreate/alter existing `users` rows.
- Does not touch passwords, PO, sessions, material-flow ledgers or PostgreSQL runtime data.
- Existing role strings are preserved.
- Admin is always full-access and cannot have permissions reduced.
- Downgrade drops only the three RBAC metadata tables.
