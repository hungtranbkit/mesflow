from mesflow.db.connection import transaction, fetch_all

class RBACRepository:
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
