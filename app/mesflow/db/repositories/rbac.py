from mesflow.db.connection import transaction, fetch_all

# Canonical RBAC seed data -- the UNION of every rbac_roles/rbac_permissions/
# rbac_role_permissions row ever inserted by migrations 0025_rbac_permissions,
# 0028_kiosk_ota_rollout_control, 0029_kiosk_ota_fleet_safety,
# 0037_v72_audit_operations_separation and 0043_super_admin_role, captured
# here as of 2026-09-02 (frozen against a real, verified-healthy backup taken
# that morning -- see reports/MESFLOW_STABILITY_AUDIT_20260902.md's RBAC
# section for the forensic trail).
#
# Real incident this exists to make self-healing: local DEV's rbac_permissions/
# rbac_role_permissions were found completely empty on 2026-09-02 (every user,
# including admin, silently got permissions:[] -- no page would open).
# Alembic migrations only ever run their INSERTs ONCE (the moment each
# revision is first applied); once recorded as applied, `alembic upgrade
# head` on every future boot skips them even if their DATA is later lost by
# some out-of-band event -- unlike users (seed-admin/seed-default-users/
# seed-super-admin, which DO idempotently re-verify on every boot). RBACRepository.seed()
# closes that gap the same way: pure `ON CONFLICT DO NOTHING` inserts, safe
# to call unconditionally on every boot, can only ADD missing rows, never
# overwrites or deletes an existing one.
SEED_ROLES = (
    # code, name, description, sort_order
    ('super_admin', 'Super Admin / IT', 'Bao tri he thong MESFlow: suc khoe, loi he thong, nhat ky, chan doan, dieu khien dich vu, audit ky thuat', 5),
    ('admin', 'Quản trị viên', 'Toàn quyền hệ thống', 10),
    ('manager', 'Quản lý', 'Điều hành sản xuất và cấu hình nghiệp vụ', 20),
    ('supervisor', 'Quản đốc', 'Điều hành ca, session và dữ liệu xưởng', 30),
    ('operator', 'Vận hành', 'Thao tác sản xuất và kiosk', 40),
    ('viewer', 'Chỉ xem', 'Chỉ xem các màn hình được cấp', 50),
)
SEED_PERMISSIONS = (
    # code, module, name, page, action, sort_order
    ('overview.view', 'Tổng quan', 'Xem tổng quan sản xuất', 'overview', 'view', 10),
    ('dashboard.view', 'Dashboard', 'Xem dashboard theo ngày', 'dashboard', 'view', 20),
    ('po.view', 'Production Order', 'Xem Production Order', 'production-orders', 'view', 30),
    ('po.edit', 'Production Order', 'Tạo/sửa/start Production Order', 'production-orders', 'edit', 31),
    ('template.view', 'Template', 'Xem Template', 'templates', 'view', 40),
    ('template.edit', 'Template', 'Tạo/sửa Template', 'templates', 'edit', 41),
    ('session.view', 'Session', 'Xem Session', 'session-management', 'view', 50),
    ('session.edit', 'Session', 'Chỉnh sửa Session', 'session-management', 'edit', 51),
    ('exceptions.view', 'Session bất thường', 'Xem ngoại lệ Session', 'session-exceptions', 'view', 60),
    ('exceptions.resolve', 'Session bất thường', 'Xử lý ngoại lệ Session', 'session-exceptions', 'edit', 61),
    ('material_flow.view', 'Gantt & Material Flow', 'Xem dòng vật tư', 'production-schedule', 'view', 70),
    ('material_flow.edit', 'Gantt & Material Flow', 'Cấu hình/điều chỉnh dòng vật tư', 'production-schedule', 'edit', 71),
    ('kiosk.view', 'Trạm kiosk', 'Xem trạm kiosk', 'kiosk-management', 'view', 80),
    ('kiosk.manage', 'Trạm kiosk', 'Quản lý trạm kiosk', 'kiosk-management', 'edit', 81),
    ('ota.view', 'ESP Kiosk OTA', 'Xem thiết bị, firmware và lịch sử OTA', 'esp-ota', 'view', 82),
    ('ota.firmware.manage', 'ESP Kiosk OTA', 'Upload, activate và disable firmware', 'esp-ota', 'edit', 83),
    ('ota.deploy', 'ESP Kiosk OTA', 'Tạo và bắt đầu deployment OTA', 'esp-ota', 'deploy', 84),
    ('ota.control', 'ESP Kiosk OTA', 'Pause, resume, cancel và retry OTA', 'esp-ota', 'control', 85),
    ('ota.approve_stage', 'ESP Kiosk OTA', 'Phê duyệt stage tiếp theo', 'esp-ota', 'approve', 86),
    ('ota.emergency_stop', 'ESP Kiosk OTA', 'Emergency stop rollout', 'esp-ota', 'emergency', 87),
    ('ota.manage_policy', 'ESP Kiosk OTA', 'Quản lý policy/hold/known-good', 'esp-ota', 'policy', 88),
    ('ota.manage_global_switch', 'ESP Kiosk OTA', 'Quản lý global OTA switch', 'esp-ota', 'global', 89),
    ('logs.view', 'Nhật ký hệ thống', 'Xem action/error logs', 'system-logs', 'view', 90),
    ('logs.manage', 'Nhật ký hệ thống', 'Đánh dấu/xử lý log lỗi', 'system-logs', 'edit', 91),
    ('employees.view', 'Nhân viên', 'Xem nhân viên', 'employees', 'view', 100),
    ('employees.edit', 'Nhân viên', 'Tạo/sửa nhân viên', 'employees', 'edit', 101),
    ('qr.view', 'QR Code', 'Xem/in QR', 'qr-print', 'view', 110),
    ('equipment.view', 'Thiết bị', 'Xem thiết bị', 'equipment', 'view', 120),
    ('equipment.edit', 'Thiết bị', 'Tạo/sửa thiết bị', 'equipment', 'edit', 121),
    ('users.view', 'Người dùng', 'Xem tài khoản', 'users', 'view', 130),
    ('users.manage', 'Người dùng', 'Tạo/sửa/reset tài khoản', 'users', 'edit', 131),
    ('roles.manage', 'Phân quyền', 'Cấu hình vai trò và quyền', 'users', 'admin', 132),
    ('calendar.view', 'Lịch làm việc', 'Xem lịch làm việc', 'working-calendar', 'view', 140),
    ('calendar.edit', 'Lịch làm việc', 'Cấu hình ca/ngày nghỉ', 'working-calendar', 'edit', 141),
    ('business_audit.view', 'Nhật ký nghiệp vụ', 'Xem nhật ký nghiệp vụ (audit trail)', 'business-audit', 'view', 150),
    ('operations.view', 'Operations Center', 'Xem Operations Center (Deploy Agent)', 'operations-center', 'view', 151),
    ('system_logs.view', 'Nhật ký hệ thống', 'Xem nhật ký kỹ thuật hệ thống (Deploy Agent)', 'operations-center', 'view', 152),
    ('diagnostics.run', 'Chẩn đoán', 'Chạy chẩn đoán kỹ thuật (Deploy Agent)', 'operations-center', 'edit', 153),
    ('deploy.view', 'Deploy', 'Xem lịch sử/trạng thái deploy (Deploy Agent)', 'operations-center', 'view', 154),
    ('deploy.execute', 'Deploy', 'Thực hiện deploy/promote (Deploy Agent)', 'operations-center', 'admin', 155),
)
# (role_code, permission_code) grants -- every row that survived the forensic
# restore, i.e. the exact live-verified 102-row grant matrix, not a
# re-derivation from BASE/ROLES dicts (those only ever covered 0025's
# original 5 roles x subset of permissions; OTA/audit/super_admin grants
# were added by later migrations directly as SELECT ... CROSS JOIN, never
# captured as a single Python literal anywhere in this codebase until now).
SEED_ROLE_PERMISSIONS = tuple(sorted({
    ('admin', 'calendar.edit'),
    ('admin', 'calendar.view'),
    ('admin', 'dashboard.view'),
    ('admin', 'employees.edit'),
    ('admin', 'employees.view'),
    ('admin', 'equipment.edit'),
    ('admin', 'equipment.view'),
    ('admin', 'exceptions.resolve'),
    ('admin', 'exceptions.view'),
    ('admin', 'kiosk.manage'),
    ('admin', 'kiosk.view'),
    ('admin', 'logs.manage'),
    ('admin', 'logs.view'),
    ('admin', 'material_flow.edit'),
    ('admin', 'material_flow.view'),
    ('admin', 'ota.approve_stage'),
    ('admin', 'ota.control'),
    ('admin', 'ota.deploy'),
    ('admin', 'ota.emergency_stop'),
    ('admin', 'ota.firmware.manage'),
    ('admin', 'ota.manage_global_switch'),
    ('admin', 'ota.manage_policy'),
    ('admin', 'ota.view'),
    ('admin', 'overview.view'),
    ('admin', 'po.edit'),
    ('admin', 'po.view'),
    ('admin', 'qr.view'),
    ('admin', 'roles.manage'),
    ('admin', 'session.edit'),
    ('admin', 'session.view'),
    ('admin', 'template.edit'),
    ('admin', 'template.view'),
    ('admin', 'users.manage'),
    ('admin', 'users.view'),
    ('manager', 'business_audit.view'),
    ('manager', 'calendar.edit'),
    ('manager', 'calendar.view'),
    ('manager', 'dashboard.view'),
    ('manager', 'deploy.view'),
    ('manager', 'employees.edit'),
    ('manager', 'employees.view'),
    ('manager', 'equipment.edit'),
    ('manager', 'equipment.view'),
    ('manager', 'exceptions.resolve'),
    ('manager', 'exceptions.view'),
    ('manager', 'kiosk.manage'),
    ('manager', 'kiosk.view'),
    ('manager', 'logs.view'),
    ('manager', 'material_flow.edit'),
    ('manager', 'material_flow.view'),
    ('manager', 'operations.view'),
    ('manager', 'ota.approve_stage'),
    ('manager', 'ota.control'),
    ('manager', 'ota.deploy'),
    ('manager', 'ota.firmware.manage'),
    ('manager', 'ota.manage_policy'),
    ('manager', 'ota.view'),
    ('manager', 'overview.view'),
    ('manager', 'po.edit'),
    ('manager', 'po.view'),
    ('manager', 'qr.view'),
    ('manager', 'session.edit'),
    ('manager', 'session.view'),
    ('manager', 'system_logs.view'),
    ('manager', 'template.edit'),
    ('manager', 'template.view'),
    ('operator', 'dashboard.view'),
    ('operator', 'employees.view'),
    ('operator', 'kiosk.view'),
    ('operator', 'material_flow.view'),
    ('operator', 'overview.view'),
    ('operator', 'po.view'),
    ('operator', 'qr.view'),
    ('operator', 'session.view'),
    ('supervisor', 'business_audit.view'),
    ('supervisor', 'calendar.view'),
    ('supervisor', 'dashboard.view'),
    ('supervisor', 'employees.view'),
    ('supervisor', 'equipment.view'),
    ('supervisor', 'exceptions.resolve'),
    ('supervisor', 'exceptions.view'),
    ('supervisor', 'kiosk.manage'),
    ('supervisor', 'kiosk.view'),
    ('supervisor', 'material_flow.edit'),
    ('supervisor', 'material_flow.view'),
    ('supervisor', 'ota.view'),
    ('supervisor', 'overview.view'),
    ('supervisor', 'po.view'),
    ('supervisor', 'qr.view'),
    ('supervisor', 'session.edit'),
    ('supervisor', 'session.view'),
    ('viewer', 'calendar.view'),
    ('viewer', 'dashboard.view'),
    ('viewer', 'employees.view'),
    ('viewer', 'equipment.view'),
    ('viewer', 'exceptions.view'),
    ('viewer', 'material_flow.view'),
    ('viewer', 'overview.view'),
    ('viewer', 'po.view'),
    ('viewer', 'qr.view'),
    ('viewer', 'session.view'),
    ('viewer', 'template.view'),
}))


class RBACRepository:
    def seed(self):
        """Idempotently (re)apply the canonical seed data above. Roles and
        permissions themselves (pure catalog/definition rows, not
        per-installation state) use plain ON CONFLICT DO NOTHING -- safe
        to reassert unconditionally.

        rbac_role_permissions is handled differently, on purpose (a real
        design bug caught by this method's own test suite before it
        shipped, not by inspection): a role's *grant set* is real,
        editable state (Users & Roles -> RBACRepository.set_role_permissions,
        e.g. an admin deliberately narrowing what 'viewer' can see). A
        naive per-row ON CONFLICT DO NOTHING would silently RESTORE every
        permission an admin had just removed on the very next boot,
        because a removed grant leaves no row behind to conflict with --
        that would be worse than the incident this exists to fix. So the
        grant set is seeded ONE ROLE AT A TIME, and only for a role that
        currently has ZERO rows in rbac_role_permissions -- indistinguishable
        from "never configured" (a brand-new role, or this exact incident:
        data wiped down to nothing) and therefore safe to (re)populate in
        full; any role with at least one grant already recorded, however
        it originally got there, is left completely alone.
        """
        with transaction() as conn:
            with conn.cursor() as cur:
                for code, name, description, sort_order in SEED_ROLES:
                    cur.execute(
                        "INSERT INTO rbac_roles(code,name,description,system_role,sort_order) VALUES(%s,%s,%s,true,%s) ON CONFLICT(code) DO NOTHING",
                        (code, name, description, sort_order))
                for code, module, name, page, action, sort_order in SEED_PERMISSIONS:
                    cur.execute(
                        "INSERT INTO rbac_permissions(code,module,name,page,action,sort_order) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(code) DO NOTHING",
                        (code, module, name, page, action, sort_order))
                by_role: dict[str, list[str]] = {}
                for role_code, permission_code in SEED_ROLE_PERMISSIONS:
                    by_role.setdefault(role_code, []).append(permission_code)
                for role_code, permission_codes in by_role.items():
                    cur.execute("SELECT 1 AS ok FROM rbac_role_permissions WHERE role_code=%s LIMIT 1", (role_code,))
                    if cur.fetchone():
                        continue  # already has grants (from an earlier seed, or a real admin edit) -- never touch
                    for permission_code in permission_codes:
                        cur.execute(
                            "INSERT INTO rbac_role_permissions(role_code,permission_code) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                            (role_code, permission_code))

    def roles(self):
        return fetch_all("SELECT code,name,description,system_role,sort_order FROM rbac_roles ORDER BY sort_order,code")

    def permissions(self):
        return fetch_all("SELECT code,module,name,page,action,sort_order FROM rbac_permissions ORDER BY sort_order,code")

    def permissions_for_role(self, role):
        rows=fetch_all("SELECT permission_code FROM rbac_role_permissions WHERE role_code=%s ORDER BY permission_code",(str(role).lower(),))
        return [r['permission_code'] for r in rows]

    def has_permission(self, role, permission):
        if str(role).lower()=='admin':
            return True
        rows=fetch_all("SELECT 1 AS ok FROM rbac_role_permissions WHERE role_code=%s AND permission_code=%s LIMIT 1",(str(role).lower(),permission))
        return bool(rows)

    def matrix(self):
        roles=self.roles(); perms=self.permissions()
        grants=fetch_all("SELECT role_code,permission_code FROM rbac_role_permissions")
        by_role={r['code']:[] for r in roles}
        for g in grants: by_role.setdefault(g['role_code'],[]).append(g['permission_code'])
        return {'roles':roles,'permissions':perms,'grants':by_role}

    def set_role_permissions(self, role_code, permission_codes):
        role_code=str(role_code).strip().lower()
        if role_code=='admin':
            permission_codes=[p['code'] for p in self.permissions()]
        known={p['code'] for p in self.permissions()}
        requested={str(x).strip() for x in permission_codes if str(x).strip()}
        unknown=sorted(requested-known)
        if unknown: raise ValueError('Unknown permissions: '+', '.join(unknown))
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code FROM rbac_roles WHERE code=%s FOR UPDATE",(role_code,))
                if not cur.fetchone(): raise KeyError(role_code)
                cur.execute("DELETE FROM rbac_role_permissions WHERE role_code=%s",(role_code,))
                for code in sorted(requested):
                    cur.execute("INSERT INTO rbac_role_permissions(role_code,permission_code) VALUES(%s,%s)",(role_code,code))
        return sorted(requested)
