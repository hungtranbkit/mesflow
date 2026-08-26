from pathlib import Path
import ast,json
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/'VERSION.txt').read_text().strip()

def test_release_sync():
    assert (ROOT/'VERSION.txt').read_text().strip()==EXPECTED
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((ROOT/'release.json').read_text())['version']==EXPECTED
    assert f'mesflow-app:{EXPECTED}' in (ROOT/'compose.yml').read_text()

def test_migration_is_additive_and_chained():
    t=(ROOT/'app/migrations/versions/0025_rbac_permissions.py').read_text()
    ast.parse(t)
    assert 'down_revision = "0024_repair_cycle_time"' in t
    assert 'op.create_table("rbac_roles"' in t
    assert 'op.create_table("rbac_permissions"' in t
    assert 'op.create_table("rbac_role_permissions"' in t
    assert 'op.drop_table("users")' not in t
    assert 'UPDATE users' not in t
    assert "value='65.8.44.32'" in t

def test_admin_full_and_roles_seeded():
    t=(ROOT/'app/migrations/versions/0025_rbac_permissions.py').read_text()
    for r in ['admin','manager','supervisor','operator','viewer']: assert f'("{r}"' in t
    assert 'all_codes if role=="admin"' in t

def test_backend_has_permission_enforcement():
    t=(ROOT/'app/mesflow/web/auth.py').read_text()
    ast.parse(t)
    assert 'def permission_required(permission)' in t
    assert 'RBACRepository().has_permission' in t

def test_frontend_filters_tabs_and_has_matrix():
    t=(ROOT/'app/mesflow/web/static/app.js').read_text()
    assert 'PAGE_PERMISSION=' in t
    assert 'canOpenPage' in t
    assert 'renderRolePermissions' in t
    assert 'Vai trò & phân quyền' in t

def test_default_users_are_opt_in_no_hardcoded_password():
    t=(ROOT/'app/mesflow/cli.py').read_text()
    assert "MESFLOW_SEED_DEFAULT_USERS','0'" in t
    for bad in ['Admin@123456','Manager@123456','Supervisor@123456','Operator@123456','Viewer@123456']:
        assert bad not in t
