"""Add role-based access control without rewriting existing user rows.

Safe migration:
- adds only new RBAC tables;
- preserves users/passwords/sessions/production data;
- seeds role/permission metadata idempotently;
- existing users keep their current role strings.
"""
from alembic import op
import sqlalchemy as sa

revision = "0025_rbac_permissions"
down_revision = "0024_repair_cycle_time"
branch_labels = None
depends_on = None

ROLES = [
    ("admin", "Quản trị viên", "Toàn quyền hệ thống", 10),
    ("manager", "Quản lý", "Điều hành sản xuất và cấu hình nghiệp vụ", 20),
    ("supervisor", "Quản đốc", "Điều hành ca, session và dữ liệu xưởng", 30),
    ("operator", "Vận hành", "Thao tác sản xuất và kiosk", 40),
    ("viewer", "Chỉ xem", "Chỉ xem các màn hình được cấp", 50),
]

PERMISSIONS = [
    ("overview.view","Tổng quan","Xem tổng quan sản xuất","overview","view",10),
    ("dashboard.view","Dashboard","Xem dashboard theo ngày","dashboard","view",20),
    ("po.view","Production Order","Xem Production Order","production-orders","view",30),
    ("po.edit","Production Order","Tạo/sửa/start Production Order","production-orders","edit",31),
    ("template.view","Template","Xem Template","templates","view",40),
    ("template.edit","Template","Tạo/sửa Template","templates","edit",41),
    ("session.view","Session","Xem Session","session-management","view",50),
    ("session.edit","Session","Chỉnh sửa Session","session-management","edit",51),
    ("exceptions.view","Session bất thường","Xem ngoại lệ Session","session-exceptions","view",60),
    ("exceptions.resolve","Session bất thường","Xử lý ngoại lệ Session","session-exceptions","edit",61),
    ("material_flow.view","Gantt & Material Flow","Xem dòng vật tư","production-schedule","view",70),
    ("material_flow.edit","Gantt & Material Flow","Cấu hình/điều chỉnh dòng vật tư","production-schedule","edit",71),
    ("kiosk.view","Trạm kiosk","Xem trạm kiosk","kiosk-management","view",80),
    ("kiosk.manage","Trạm kiosk","Quản lý trạm kiosk","kiosk-management","edit",81),
    ("logs.view","Nhật ký hệ thống","Xem action/error logs","system-logs","view",90),
    ("logs.manage","Nhật ký hệ thống","Đánh dấu/xử lý log lỗi","system-logs","edit",91),
    ("employees.view","Nhân viên","Xem nhân viên","employees","view",100),
    ("employees.edit","Nhân viên","Tạo/sửa nhân viên","employees","edit",101),
    ("qr.view","QR Code","Xem/in QR","qr-print","view",110),
    ("equipment.view","Thiết bị","Xem thiết bị","equipment","view",120),
    ("equipment.edit","Thiết bị","Tạo/sửa thiết bị","equipment","edit",121),
    ("users.view","Người dùng","Xem tài khoản","users","view",130),
    ("users.manage","Người dùng","Tạo/sửa/reset tài khoản","users","edit",131),
    ("roles.manage","Phân quyền","Cấu hình vai trò và quyền","users","admin",132),
    ("calendar.view","Lịch làm việc","Xem lịch làm việc","working-calendar","view",140),
    ("calendar.edit","Lịch làm việc","Cấu hình ca/ngày nghỉ","working-calendar","edit",141),
]

BASE = {
    "viewer": {"overview.view","dashboard.view","po.view","template.view","session.view","exceptions.view","material_flow.view","employees.view","qr.view","equipment.view","calendar.view"},
    "operator": {"overview.view","dashboard.view","po.view","session.view","material_flow.view","kiosk.view","employees.view","qr.view"},
    "supervisor": {"overview.view","dashboard.view","po.view","session.view","session.edit","exceptions.view","exceptions.resolve","material_flow.view","material_flow.edit","kiosk.view","kiosk.manage","employees.view","qr.view","equipment.view","calendar.view"},
    "manager": {"overview.view","dashboard.view","po.view","po.edit","template.view","template.edit","session.view","session.edit","exceptions.view","exceptions.resolve","material_flow.view","material_flow.edit","kiosk.view","kiosk.manage","logs.view","employees.view","employees.edit","qr.view","equipment.view","equipment.edit","calendar.view","calendar.edit"},
}

def upgrade():
    op.create_table("rbac_roles",
        sa.Column("code",sa.Text(),primary_key=True),
        sa.Column("name",sa.Text(),nullable=False),
        sa.Column("description",sa.Text(),nullable=False,server_default=""),
        sa.Column("system_role",sa.Boolean(),nullable=False,server_default=sa.text("true")),
        sa.Column("sort_order",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_table("rbac_permissions",
        sa.Column("code",sa.Text(),primary_key=True),
        sa.Column("module",sa.Text(),nullable=False),
        sa.Column("name",sa.Text(),nullable=False),
        sa.Column("page",sa.Text(),nullable=False,server_default=""),
        sa.Column("action",sa.Text(),nullable=False,server_default="view"),
        sa.Column("sort_order",sa.Integer(),nullable=False,server_default="0"))
    op.create_table("rbac_role_permissions",
        sa.Column("role_code",sa.Text(),sa.ForeignKey("rbac_roles.code",ondelete="CASCADE"),primary_key=True),
        sa.Column("permission_code",sa.Text(),sa.ForeignKey("rbac_permissions.code",ondelete="CASCADE"),primary_key=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")))
    for code,name,description,sort_order in ROLES:
        op.execute(sa.text("INSERT INTO rbac_roles(code,name,description,system_role,sort_order) VALUES (:c,:n,:d,true,:s) ON CONFLICT(code) DO NOTHING").bindparams(c=code,n=name,d=description,s=sort_order))
    for code,module,name,page,action,sort_order in PERMISSIONS:
        op.execute(sa.text("INSERT INTO rbac_permissions(code,module,name,page,action,sort_order) VALUES (:c,:m,:n,:p,:a,:s) ON CONFLICT(code) DO NOTHING").bindparams(c=code,m=module,n=name,p=page,a=action,s=sort_order))
    all_codes=[p[0] for p in PERMISSIONS]
    for role in [r[0] for r in ROLES]:
        codes=all_codes if role=="admin" else sorted(BASE.get(role,set()))
        for perm in codes:
            op.execute(sa.text("INSERT INTO rbac_role_permissions(role_code,permission_code) VALUES (:r,:p) ON CONFLICT DO NOTHING").bindparams(r=role,p=perm))
    op.execute("UPDATE system_meta SET value='65.8.44.32',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")

def downgrade():
    # Intentionally leaves users and all production data untouched.
    op.drop_table("rbac_role_permissions")
    op.drop_table("rbac_permissions")
    op.drop_table("rbac_roles")
    op.execute("UPDATE system_meta SET value='65.8.44.2',updated_at=CURRENT_TIMESTAMP WHERE key='schema_version'")
