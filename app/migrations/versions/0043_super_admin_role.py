"""Add SUPER_ADMIN role + append-only System Audit trail.

Safe migration:
- purely additive: one new rbac_roles row, one new table;
- does not touch users/passwords/sessions/production data;
- does not modify rbac_permissions/rbac_role_permissions for existing
  roles (admin's blanket bypass, and every other role's grants, are
  untouched -- SUPER_ADMIN-only routes are gated by a literal role check
  in mesflow.web.auth.super_admin_required, not by the permission matrix,
  so there is nothing to seed here for the System Console itself);
- no account is auto-created here. The first SUPER_ADMIN is created by
  mesflow.cli.seed_super_admin() (MESFLOW_SUPER_ADMIN_USERNAME/
  MESFLOW_SUPER_ADMIN_PASSWORD), the same idiom seed_admin()/
  seed_default_users() already use -- never via a public API.
"""
from alembic import op
import sqlalchemy as sa

revision = "0043_super_admin_role"
down_revision = "0042_session_review_and_exclusion"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text(
        "INSERT INTO rbac_roles(code,name,description,system_role,sort_order) "
        "VALUES ('super_admin','Super Admin / IT','Bao tri he thong MESFlow: suc khoe, "
        "loi he thong, nhat ky, chan doan, dieu khien dich vu, audit ky thuat',true,5) "
        "ON CONFLICT(code) DO NOTHING"
    ))
    op.create_table(
        "system_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_username", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_role", sa.Text(), nullable=False, server_default=""),
        sa.Column("environment", sa.Text(), nullable=False, server_default=""),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("result", sa.Text(), nullable=False, server_default=""),
        sa.Column("correlation_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_system_audit_log_occurred_at", "system_audit_log", ["occurred_at"])
    op.create_index("ix_system_audit_log_action", "system_audit_log", ["action"])


def downgrade():
    # Intentionally leaves users and all production data untouched.
    op.drop_index("ix_system_audit_log_action", table_name="system_audit_log")
    op.drop_index("ix_system_audit_log_occurred_at", table_name="system_audit_log")
    op.drop_table("system_audit_log")
    op.execute("DELETE FROM rbac_roles WHERE code='super_admin'")
