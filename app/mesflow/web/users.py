import json
from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash
from mesflow.db.connection import transaction
from mesflow.db.repositories.user_repository import UserRepository
from mesflow.db.repositories.rbac import RBACRepository
from mesflow.web.auth import login_required, admin_required, permission_required

bp = Blueprint('users', __name__, url_prefix='/api')
ROLES = {'admin', 'manager', 'supervisor', 'operator', 'viewer'}


def _audit(action, entity_id, details):
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                INSERT INTO audit_logs(
                    actor_username, action, entity_type, entity_id, details_json
                ) VALUES(%s,%s,'user',%s,%s)
            ''', (
                session.get('username', ''), action, str(entity_id),
                json.dumps(details, ensure_ascii=False),
            ))


def _password_error(password):
    if len(password) < 8:
        return 'Mật khẩu phải có ít nhất 8 ký tự'
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return 'Mật khẩu phải có cả chữ và số'
    return None


@bp.get('/users')
@permission_required('users.view')
def list_users():
    return jsonify(ok=True, items=UserRepository().list_all(), roles=[r['code'] for r in RBACRepository().roles()])


@bp.post('/users')
@permission_required('users.manage')
def create_user():
    b = request.get_json(silent=True) or {}
    username = str(b.get('username', '')).strip().lower()
    display_name = str(b.get('display_name', '')).strip()
    role = str(b.get('role', 'viewer')).strip().lower()
    password = str(b.get('password', ''))
    if not username or not display_name:
        return jsonify(ok=False, message='Tên đăng nhập và tên hiển thị là bắt buộc'), 400
    if role not in ROLES:
        return jsonify(ok=False, message='Vai trò không hợp lệ'), 400
    err = _password_error(password)
    if err:
        return jsonify(ok=False, message=err), 400
    try:
        user_id = UserRepository().create(
            username, display_name, password, role,
            bool(b.get('must_change_password', True)),
        )
    except Exception as e:
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            return jsonify(ok=False, message='Tên đăng nhập đã tồn tại'), 409
        raise
    _audit('USER_CREATED', user_id, {'username': username, 'role': role})
    return jsonify(ok=True, id=user_id), 201


@bp.patch('/users/<int:user_id>')
@permission_required('users.manage')
def update_user(user_id):
    b = request.get_json(silent=True) or {}
    user = UserRepository().get_by_id(user_id)
    if not user:
        return jsonify(ok=False, message='Không tìm thấy tài khoản'), 404
    role = str(b.get('role', user['role'])).strip().lower()
    active = bool(b.get('active', user['active']))
    display_name = str(b.get('display_name', user['display_name'])).strip()
    if role not in ROLES:
        return jsonify(ok=False, message='Vai trò không hợp lệ'), 400
    if user_id == session.get('user_id') and (not active or role != 'admin'):
        return jsonify(ok=False, message='Admin không thể tự khóa hoặc tự hạ quyền tài khoản đang đăng nhập'), 409
    UserRepository().update_profile(user_id, display_name, role, active)
    _audit('USER_UPDATED', user_id, {'role': role, 'active': active})
    return jsonify(ok=True)


@bp.post('/users/<int:user_id>/reset-password')
@permission_required('users.manage')
def reset_user_password(user_id):
    b = request.get_json(silent=True) or {}
    password = str(b.get('password', ''))
    err = _password_error(password)
    if err:
        return jsonify(ok=False, message=err), 400
    user = UserRepository().get_by_id(user_id)
    if not user:
        return jsonify(ok=False, message='Không tìm thấy tài khoản'), 404
    must_change = bool(b.get('must_change_password', True))
    UserRepository().set_password(user_id, password, must_change)
    _audit('USER_PASSWORD_RESET', user_id, {'must_change_password': must_change})
    return jsonify(ok=True)


@bp.post('/auth/change-password')
@login_required
def change_own_password():
    b = request.get_json(silent=True) or {}
    current = str(b.get('current_password', ''))
    password = str(b.get('new_password', ''))
    user = UserRepository().get_by_id(session['user_id'])
    if not user or not check_password_hash(user['password_hash'], current):
        return jsonify(ok=False, message='Mật khẩu hiện tại không đúng'), 400
    err = _password_error(password)
    if err:
        return jsonify(ok=False, message=err), 400
    if check_password_hash(user['password_hash'], password):
        return jsonify(ok=False, message='Mật khẩu mới phải khác mật khẩu hiện tại'), 400
    UserRepository().set_password(user['id'], password, False)
    _audit('USER_PASSWORD_CHANGED', user['id'], {})
    return jsonify(ok=True)


@bp.get('/roles')
@permission_required('users.view')
def list_roles_permissions():
    return jsonify(ok=True, **RBACRepository().matrix())

@bp.put('/roles/<role_code>/permissions')
@permission_required('roles.manage')
def update_role_permissions(role_code):
    b=request.get_json(silent=True) or {}
    if str(role_code).lower()=='admin':
        return jsonify(ok=False,message='Quyền Admin là cố định toàn quyền và không thể hạ'),409
    try:
        permissions=RBACRepository().set_role_permissions(role_code,b.get('permissions') or [])
    except KeyError:
        return jsonify(ok=False,message='Vai trò không tồn tại'),404
    except ValueError as e:
        return jsonify(ok=False,message=str(e)),400
    _audit('ROLE_PERMISSIONS_UPDATED',role_code,{'permissions':permissions})
    return jsonify(ok=True,role=role_code,permissions=permissions)
