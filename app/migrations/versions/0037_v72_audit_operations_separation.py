"""Separate MESFlow business audit from Deploy Agent system/infrastructure
operations (reports/SYSTEM_LOG_AUDIT_SEPARATION.md). Additive only:

- new RBAC permissions for the split (business_audit.view, operations.view,
  system_logs.view, diagnostics.run, deploy.view, deploy.execute), granted
  to the roles that already had the closest existing permission so nobody
  loses access they had (section 13: "do not weaken existing authorization")
- an index to make the new Business Audit Trail's filters (time range,
  employee) fast without a new table -- audit_logs and its V66 columns
  already carry everything this page needs
"""
from alembic import op
import sqlalchemy as sa

revision="0037_v72_audit_operations_separation"
down_revision="0036_v69f_predictive"
branch_labels=None
depends_on=None

PERMISSIONS = [
    ("business_audit.view","Nhật ký nghiệp vụ","Xem nhật ký nghiệp vụ (audit trail)","business-audit","view",150),
    ("operations.view","Operations Center","Xem Operations Center (Deploy Agent)","operations-center","view",151),
    ("system_logs.view","Nhật ký hệ thống","Xem nhật ký kỹ thuật hệ thống (Deploy Agent)","operations-center","view",152),
    ("diagnostics.run","Chẩn đoán","Chạy chẩn đoán kỹ thuật (Deploy Agent)","operations-center","edit",153),
    ("deploy.view","Deploy","Xem lịch sử/trạng thái deploy (Deploy Agent)","operations-center","view",154),
    ("deploy.execute","Deploy","Thực hiện deploy/promote (Deploy Agent)","operations-center","admin",155),
]

# manager already had logs.view (the old, now-ambiguous "system logs"
# permission that actually gates MESFlow's own action_logs page) -- that
# grant is untouched; these are the NEW, more specific grants for the
# roles closest to today's real usage.
GRANTS = {
    "manager": ["business_audit.view","operations.view","system_logs.view","deploy.view"],
    "supervisor": ["business_audit.view"],
}

def upgrade():
    for code,module,name,page,action,sort_order in PERMISSIONS:
        op.execute(sa.text(
            "INSERT INTO rbac_permissions(code,module,name,page,action,sort_order) VALUES (:c,:m,:n,:p,:a,:s) ON CONFLICT(code) DO NOTHING"
        ).bindparams(c=code,m=module,n=name,p=page,a=action,s=sort_order))
    for role,codes in GRANTS.items():
        for code in codes:
            op.execute(sa.text(
                "INSERT INTO rbac_role_permissions(role_code,permission_code) VALUES (:r,:c) ON CONFLICT DO NOTHING"
            ).bindparams(r=role,c=code))
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_employee ON audit_logs(employee_id,created_at DESC) WHERE employee_id IS NOT NULL")
    op.execute("UPDATE system_meta SET value='72.0.0.0',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_audit_logs_created_employee")
    for code,_,_,_,_,_ in PERMISSIONS:
        op.execute(sa.text("DELETE FROM rbac_role_permissions WHERE permission_code=:c").bindparams(c=code))
        op.execute(sa.text("DELETE FROM rbac_permissions WHERE code=:c").bindparams(c=code))
