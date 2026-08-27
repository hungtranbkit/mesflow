import re
from functools import wraps
from flask import jsonify, request, session

from mesflow.core.session_policy import validate_and_touch


def _require_valid_session():
    """The single place every decorator
    below validates idle/absolute expiry before trusting session['user_id'].
    Returns None if valid (session['last_activity_at'] already refreshed as
    a side effect); returns a ready-to-return (body, status) tuple otherwise.
    Not applied to production_client_required's kiosk-token branch -- token
    auth has no browser session to expire in the first place."""
    reason = validate_and_touch()
    if reason is None:
        return None
    if reason == 'NOT_LOGGED_IN':
        return jsonify(ok=False, error='AUTH_REQUIRED'), 401
    return jsonify(ok=False, error='SESSION_EXPIRED', reason=reason,
                   message='Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'), 401


def _has_permission(permission):
    if not session.get('user_id'): return False
    role=str(session.get('role') or '').strip().lower()
    # SUPER_ADMIN keeps every ordinary Admin capability (task spec section 2:
    # "SUPER_ADMIN may use normal Admin functionality plus technical System
    # Console functionality") -- but this bypass only ever covers ordinary
    # business permission codes. It grants nothing extra for the System
    # Console itself: those routes use super_admin_required() below, which
    # checks the literal role and is never satisfied by 'admin'.
    if role in ('admin','super_admin'): return True
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
            expired=_require_valid_session()
            if expired is not None: return expired
            if not _has_permission(permission):
                return jsonify(ok=False,error='FORBIDDEN',permission=permission,message='Bạn không có quyền thực hiện thao tác này'),403
            return fn(*args,**kwargs)
        return wrapped
    return decorate

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        expired=_require_valid_session()
        if expired is not None: return expired
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    return permission_required('roles.manage')(fn)

def super_admin_required(fn):
    """Gates the SUPER_ADMIN System Console (task spec section 3/5): every
    page/API/service action/diagnostic/log/system-error-detail under it.
    Deliberately does NOT go through _has_permission()/permission_required --
    those give 'admin' a blanket bypass, which must never apply here. This
    checks the literal session role only, so an ordinary ADMIN session (or
    any other role) always gets 403, never a silent pass."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        expired=_require_valid_session()
        if expired is not None: return expired
        if str(session.get('role') or '').strip().lower()!='super_admin':
            return jsonify(ok=False,error='FORBIDDEN',message='Chỉ Super Admin mới có quyền truy cập khu vực Hệ thống'),403
        return fn(*args, **kwargs)
    return wrapped

# Compatibility layer: existing decorators become permission-aware. If a route
# is not mapped yet, the legacy role allow-list remains the safety fallback.
def _permission_for_request():
    path=request.path
    method=request.method.upper()
    edit=method not in {'GET','HEAD','OPTIONS'}
    # Real confirmed bugs (2026-08-26, Gate 18 permission-matrix audit --
    # this is now the SECOND pass; the first found and fixed the
    # /force case below in isolation, then a corrected structural sweep of
    # every @roles_required route against this function's own prefix rules
    # found three more of the exact same class): a handful of routes are
    # deliberately narrower (or, in one case, deliberately WIDER for a role
    # that should have it) than the generic path-prefix permission this
    # function would otherwise compute for them -- and roles_required()'s
    # permission branch returns immediately without ever consulting its own
    # literal allow-list once a permission match is found, so the generic
    # rule always wins silently unless carved out here first. Each entry
    # below is a route where that silent override produced a real,
    # confirmed effective-access mismatch against the route's own explicit
    # decorator:
    #   DELETE .../force            -- 'po.edit' widened admin-only to +manager
    #                                  (verified live: manager force-deleted a
    #                                  real PO end to end, HTTP 200)
    #   POST .../production-orders/<id>/start
    #                               -- 'po.edit' narrowed admin/manager/
    #                                  supervisor to admin/manager only --
    #                                  supervisors got 403 starting production
    #                                  despite the route's own decorator
    #                                  explicitly listing them
    #   POST /templates/demo/seed,
    #   DELETE /templates/demo      -- 'template.edit' widened admin-only to
    #                                  +manager for demo-data seed/wipe
    #   GET .../export-workbook     -- 'template.view' widened admin/manager
    #                                  to +viewer (read-only, low risk, but
    #                                  still not what the code says)
    # Each is excluded here so it falls through to its own literal
    # roles_required(...) list instead of the generic prefix rule.
    if path.startswith('/api/production-orders/') and path.endswith('/force'):
        return ''
    if re.fullmatch(r'/api/production-orders/\d+/start', path):
        return ''
    if path in ('/api/templates/demo/seed', '/api/templates/demo'):
        return ''
    if re.fullmatch(r'/api/templates/\d+/export-workbook', path):
        return ''
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
            expired=_require_valid_session()
            if expired is not None: return expired
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
            # Session-or-token: an EXPIRED session must not hard-fail here --
            # fall through to the kiosk-token check below rather than the
            # generic SESSION_EXPIRED 401 _require_valid_session() would
            # give, since a valid token alone is still sufficient auth for
            # this decorator. validate_and_touch() clears the expired
            # session as a side effect either way.
            if validate_and_touch() is None:
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
