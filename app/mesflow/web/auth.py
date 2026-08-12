from functools import wraps
from flask import jsonify, request, session


def _has_permission(permission):
    if not session.get('user_id'): return False
    role=str(session.get('role') or '').strip().lower()
    if role=='admin': return True
    try:
        from mesflow.db.repositories.rbac import RBACRepository
        return RBACRepository().has_permission(role,permission)
    except Exception:
        # Fail closed if RBAC metadata is unavailable.
        return False

def permission_required(permission):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if not session.get('user_id'):
                return jsonify(ok=False,error='AUTH_REQUIRED'),401
            if not _has_permission(permission):
                return jsonify(ok=False,error='FORBIDDEN',permission=permission,message='Bạn không có quyền thực hiện thao tác này'),403
            return fn(*args,**kwargs)
        return wrapped
    return decorate

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify(ok=False, error='AUTH_REQUIRED'), 401
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    return permission_required('roles.manage')(fn)

# Compatibility layer: existing decorators become permission-aware. If a route
# is not mapped yet, the legacy role allow-list remains the safety fallback.
def _permission_for_request():
    path=request.path
    method=request.method.upper()
    edit=method not in {'GET','HEAD','OPTIONS'}
    rules=[
      ('/api/users','users.manage' if edit else 'users.view'),
      ('/api/roles','roles.manage'),
      ('/api/action-logs','logs.manage' if edit else 'logs.view'),
      ('/api/error-traces','logs.manage' if edit else 'logs.view'),
      ('/api/employees','employees.edit' if edit else 'employees.view'),
      ('/api/equipment','equipment.edit' if edit else 'equipment.view'),
      ('/api/templates','template.edit' if edit else 'template.view'),
      ('/api/production-orders','po.edit' if edit else 'po.view'),
      ('/api/session-management','session.edit' if edit else 'session.view'),
      ('/api/supervisor/sessions','session.edit'),
      ('/api/session-exceptions','exceptions.resolve' if edit else 'exceptions.view'),
      ('/api/material-flow','material_flow.edit' if edit else 'material_flow.view'),
      ('/api/kiosks','kiosk.manage' if edit else 'kiosk.view'),
      ('/api/settings/work-shifts','calendar.edit' if edit else 'calendar.view'),
    ]
    for prefix,permission in rules:
        if path.startswith(prefix): return permission
    return ''

def roles_required(*allowed_roles):
    allowed={str(role).strip().lower() for role in allowed_roles}
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get('user_id'):
                return jsonify(ok=False,error='AUTH_REQUIRED',message='Authentication required'),401
            permission=_permission_for_request()
            if permission:
                if not _has_permission(permission):
                    return jsonify(ok=False,error='FORBIDDEN',permission=permission,message='Bạn không có quyền thực hiện thao tác này'),403
                return fn(*args,**kwargs)
            if str(session.get('role') or '').strip().lower() not in allowed:
                return jsonify(ok=False,error='FORBIDDEN',message='Bạn không có quyền thực hiện thao tác này'),403
            return fn(*args, **kwargs)
        return wrapped
    return decorate

def production_client_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if session.get('user_id'):
            return fn(*args, **kwargs)
        token=str(request.headers.get('X-Kiosk-Token') or '').strip()
        if not token:
            return jsonify(ok=False,error='AUTH_REQUIRED',message='Authentication or kiosk token required'),401
        try:
            from mesflow.db.repositories.execution import KioskRepository
            KioskRepository().verify_token_any(token)
        except Exception:
            return jsonify(ok=False,error='FORBIDDEN',message='Kiosk token is invalid or disabled'),403
        return fn(*args, **kwargs)
    return wrapped
