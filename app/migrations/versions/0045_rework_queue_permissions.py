"""RBAC for the Hàng chờ sửa page (rework queue UI).

Migration 0044 shipped the rework queue backend; the 2026-09-09 audit found
it had no UI at all, so this pairs with the new pages/rework-queue.js.

Why a migration and not just RBACRepository.seed(): seed() adds missing
CATALOG rows unconditionally (ON CONFLICT DO NOTHING), so the two permissions
below would appear on their own -- but it deliberately refuses to touch
rbac_role_permissions for any role that already has at least one grant, so
that a deliberately-narrowed role is never silently re-widened on the next
boot. Every role on an existing install already has grants, so without this
migration nobody except admin/super_admin (who bypass the permission check by
role) would ever see the page. Same CROSS JOIN pattern migrations 0028/0029
already used to add the OTA grants.

Grants mirror the endpoints' own gates (web/execution.py): GET
/api/rework/queue is @login_required, POST .../resolve is
@roles_required('admin','manager','supervisor') -- so viewer gets view only,
and operator gets nothing (it has no exceptions.view either; shop-floor
operators work through the kiosk, not this desk).
"""
from alembic import op

revision = "0045_rework_queue_permissions"
down_revision = "0044_rework_queue"
branch_labels = None
depends_on = None

PERMISSIONS = ("rework.view", "rework.resolve")


def upgrade():
    op.execute("""INSERT INTO rbac_permissions(code,module,name,page,action,sort_order) VALUES
      ('rework.view','Hàng chờ sửa','Xem hàng chờ sửa','rework-queue','view',62),
      ('rework.resolve','Hàng chờ sửa','Ghi nhận sửa được / loại','rework-queue','edit',63)
      ON CONFLICT DO NOTHING""")
    op.execute("""INSERT INTO rbac_role_permissions(role_code,permission_code)
      SELECT r.code,p.code FROM rbac_roles r CROSS JOIN rbac_permissions p
      WHERE p.code IN ('rework.view','rework.resolve') AND (
        r.code IN ('admin','manager','supervisor')
        OR (r.code='viewer' AND p.code='rework.view')
      ) ON CONFLICT DO NOTHING""")
    op.execute("UPDATE system_meta SET value='72.0.5.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")


def downgrade():
    op.execute("UPDATE system_meta SET value='72.0.4.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
    op.execute("DELETE FROM rbac_role_permissions WHERE permission_code IN ('rework.view','rework.resolve')")
    op.execute("DELETE FROM rbac_permissions WHERE code IN ('rework.view','rework.resolve')")
