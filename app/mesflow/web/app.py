from pathlib import Path
import json
import os
from flask import Flask, jsonify, request, session, render_template, redirect, url_for, send_from_directory, abort, g
from werkzeug.security import check_password_hash
from werkzeug.exceptions import HTTPException
from flask.sessions import SecureCookieSessionInterface
from mesflow import __version__
from mesflow.core import session_policy
from mesflow.core.config import settings
from mesflow.db.repositories.system_repository import SystemRepository
from mesflow.db.repositories.user_repository import UserRepository
from mesflow.db.repositories.rbac import RBACRepository
from mesflow.db.repositories.analytics import AuditRepository
from mesflow.web.master_data import bp as master_data_bp
from mesflow.web.execution import bp as execution_bp
from mesflow.web.analytics import bp as analytics_bp
from mesflow.web.exceptions import bp as exceptions_bp
from mesflow.web.trace import bp as production_trace_bp
from mesflow.web.system_health import bp as system_health_bp
from mesflow.web.excel_io import bp as excel_io_bp, template_excel_bp
from mesflow.web.kiosk import bp as kiosk_bp
from mesflow.web.kiosk_v2 import bp as kiosk_v2_bp
from mesflow.web.internal_ota import bp as internal_ota_bp
from mesflow.web.users import bp as users_bp
from mesflow.web.action_logging import bp as action_logging_bp, begin_request, finish_request, unhandled_error
from mesflow.web.auth import admin_required
from mesflow.domain.events import event_bus
from mesflow.domain.event_handlers import register_default_handlers

def _is_direct_local_request():
    """Direct localhost diagnostics only; requests forwarded by nginx are excluded."""
    host=(request.host or "").rsplit(":",1)[0].strip("[]").lower()
    forwarded_proto=(request.headers.get("X-Forwarded-Proto") or "").strip()
    return host in {"127.0.0.1","localhost","::1"} and not forwarded_proto


def _is_direct_internal_qa_request():
    """Direct same-Docker-network QA access only."""
    host=(request.host or "").rsplit(":",1)[0].strip("[]").lower()
    forwarded_proto=(request.headers.get("X-Forwarded-Proto") or "").strip()
    # mesflow-demo-app is the disposable DB-backed LOCAL demo runtime. It has
    # the same internal-network trust boundary as mesflow-app; public/proxied
    # requests remain excluded by X-Forwarded-Proto and Secure cookies.
    return host in {"mesflow-app","mesflow","mesflow-demo-app"} and not forwarded_proto


# AUTOLOGIN task (2026-09-04): the 5 real, non-super_admin RBAC roles this
# app actually has -- see RBACRepository / MEMORY "MESFlow RBAC has 6 real
# roles". super_admin is deliberately excluded from quick persona-switching:
# it is the IT System Console's own separate, higher-privilege role and
# quick-switching into it is out of scope for "test RBAC nhanh" of the
# ordinary 5-role matrix.
_AUTOLOGIN_PERSONAS=('admin','manager','supervisor','operator','viewer')


def _auto_login_allowed():
    """Whether /api/auth/test-auto-login may act at all, independent of
    settings.test_auto_login itself (callers still check that separately).

    Non-production is always allowed. A MESFLOW_ENV=production deployment
    (compose.yml hardcodes this on every tier that shares it, prodtest and
    demo included) additionally requires the explicit
    settings.test_auto_login_allow_production opt-in -- see its own
    docstring in core/config.py. This function must never consult
    settings.server_role (see that field's own docstring: security-gated
    behavior is keyed off MESFLOW_ENV only, never inferred from the
    human-facing server_role label)."""
    return settings.environment!="production" or settings.test_auto_login_allow_production


class LocalhostAwareSessionInterface(SecureCookieSessionInterface):
    def get_cookie_secure(self, app):
        # Production public traffic remains Secure. Password-authenticated QA
        # traffic on the trusted mesflow-edge network may use plain internal HTTP.
        if settings.internal_http_session and _is_direct_internal_qa_request():
            return False
        if settings.environment != "production" and settings.local_auto_login and _is_direct_local_request():
            return False
        return super().get_cookie_secure(app)


def create_app():
    app=Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key=settings.secret_key
    app.session_interface=LocalhostAwareSessionInterface()
    app.config.update(
        SESSION_COOKIE_SECURE=settings.cookie_secure,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        MAX_CONTENT_LENGTH=settings.max_content_length,
        JSON_SORT_KEYS=False,
        TRAP_HTTP_EXCEPTIONS=False,
    )
    # AUTOLOGIN task (2026-09-04): loud, boot-time visibility into this
    # exact risk -- a per-request 403 is easy to miss in a log stream; a
    # startup warning is not. Fires only when settings.test_auto_login is
    # actually on and environment=="production" (the only combination
    # requirement #2 cares about); silent otherwise.
    if settings.test_auto_login and settings.environment=="production":
        if settings.test_auto_login_allow_production:
            app.logger.warning(
                "SECURITY: MESFLOW_TEST_AUTO_LOGIN is ACTIVE on a MESFLOW_ENV=production "
                "deployment because MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1 is explicitly "
                "set. Confirm this is NOT the real live-business mesflow.net production system."
            )
        else:
            app.logger.warning(
                "MESFLOW_TEST_AUTO_LOGIN=1 is set but MESFLOW_ENV=production and "
                "MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION is not -- auto-login stays "
                "force-disabled (fail-closed). If this is real production, unset "
                "MESFLOW_TEST_AUTO_LOGIN. If this is prodtest/demo intentionally running "
                "MESFLOW_ENV=production, set MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1 to "
                "actually enable it."
            )
    app.register_blueprint(master_data_bp)
    app.register_blueprint(execution_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(exceptions_bp)
    app.register_blueprint(production_trace_bp)
    app.register_blueprint(system_health_bp)
    app.register_blueprint(excel_io_bp)
    app.register_blueprint(template_excel_bp)
    app.register_blueprint(kiosk_bp)
    app.register_blueprint(kiosk_v2_bp)
    app.register_blueprint(internal_ota_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(action_logging_bp)
    app.before_request(begin_request)
    # V66 domain event foundation: register the built-in handlers exactly
    # once per process. create_app() itself is only called once at process
    # startup (see mesflow.cli / the WSGI entrypoint), so this is safe --
    # tests that call create_app() multiple times in one process should use
    # a fresh EventBus() instead of the module-level singleton.
    register_default_handlers(event_bus)

    @app.errorhandler(HTTPException)
    def handle_http_error(exc):
        # Routing/client errors such as 404 and 405 are expected HTTP responses,
        # not application failures. Do not capture or log a traceback.
        status=int(exc.code or 500)
        error={
            400:'BAD_REQUEST',
            401:'UNAUTHORIZED',
            403:'FORBIDDEN',
            404:'NOT_FOUND',
            405:'METHOD_NOT_ALLOWED',
        }.get(status,'HTTP_ERROR')
        message={
            404:'Đường dẫn không tồn tại.',
            405:'Phương thức HTTP không được hỗ trợ cho đường dẫn này.',
        }.get(status, str(exc.description or exc.name))
        return jsonify(
            ok=False,
            error=error,
            message=message,
            trace_id=getattr(g,'trace_id',''),
        ),status

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        return unhandled_error(exc)


    @app.get('/uploads/<path:filename>')
    def uploaded_file(filename):
        if session_policy.validate_and_touch() is not None:
            return redirect(url_for('login_page', next=request.path))
        upload_root='/data/uploads'
        return send_from_directory(upload_root, filename, as_attachment=True,mimetype='application/octet-stream')

    @app.get('/api/system/health')
    def health():
        try:
            info=SystemRepository().database_info(); schema=SystemRepository().schema_version()
            return jsonify(ok=True,status='healthy',version=__version__,database_backend='postgresql',database=info['database'],database_user=info['username'],postgres_version=info['server_version'],schema_version=schema,phase='production-ready',deployment_id=settings.deployment_id)
        except Exception as e:
            return jsonify(ok=False,status='unhealthy',version=__version__,error=f'{type(e).__name__}: {e}'),503


    @app.get('/api/system/ready')
    def ready():
        try:
            import os as _os
            repo=SystemRepository()
            check=repo.readiness()
            # Codex audit: expose the EFFECTIVE business timezone
            # explicitly, alongside the host/container OS timezone (TZ env
            # var) and PostgreSQL session timezone -- these can legitimately
            # differ (host is dev-machine-local, e.g. Asia/Bangkok; business
            # calendar logic is always Asia/Ho_Chi_Minh regardless) and
            # currently only appear equal by coincidence (both UTC+7) on
            # this deployment. business_timezone is the only one MESFlow's
            # own shift/session/reporting logic actually reads
            # (core.time_policy.site_zone()); the others are informational.
            timezone_info={'business_timezone':settings.timezone_name,'host_timezone':_os.environ.get('TZ') or None,'database_timezone':repo.db_timezone()}
            return jsonify(ok=True,status='ready',checked_at=check['checked_at'],schema_version=repo.schema_version(),migration_head=repo.migration_head(),version=__version__,server_role=settings.server_role or None,environment=settings.environment,commit=settings.build_commit,timezone=timezone_info)
        except Exception as e:
            return jsonify(ok=False,status='not-ready',error=f'{type(e).__name__}: {e}',version=__version__),503

    @app.get('/api/system/monitoring')
    @admin_required
    def monitoring():
        try:
            repo=SystemRepository()
            info=repo.database_info()
            return jsonify(ok=True,version=__version__,deployment_id=settings.deployment_id,database=info,connections=repo.connection_stats(),counts=repo.table_counts(),schema_version=repo.schema_version(),migration_head=repo.migration_head())
        except Exception as e:
            return jsonify(ok=False,error=f'{type(e).__name__}: {e}',version=__version__),503

    @app.after_request
    def security_headers(response):
        response=finish_request(response)
        response.headers.setdefault('X-Content-Type-Options','nosniff')
        response.headers.setdefault('X-Frame-Options','SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy','strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        response.headers.setdefault('Cache-Control','no-store' if request.path.startswith('/api/auth/') else 'no-cache')
        return response


    @app.get('/api/system/auth-health')
    @admin_required
    def auth_health():
        try:
            user=UserRepository().get_by_username(settings.admin_username)
            return jsonify(
                ok=True,
                backend='postgresql',
                admin_username=settings.admin_username,
                admin_exists=bool(user),
                admin_active=bool(user and user['active']),
                version=__version__,
            )
        except Exception as e:
            return jsonify(ok=False,error=f'{type(e).__name__}: {e}',version=__version__),503

    @app.get('/api/system/ui-routes')
    def ui_routes():
        routes=sorted(str(rule) for rule in app.url_map.iter_rules() if str(rule) in {'/','/login','/app','/admin','/admin/','/dashboard','/kiosk'})
        return jsonify(ok=True,routes=routes,version=__version__)

    @app.get('/api/system/version')
    def version():
        return jsonify(version=__version__,database_backend='postgresql',architecture='postgres-native',phase='production-ready',deployment_id=settings.deployment_id)

    @app.get('/')
    def home():
        return redirect(url_for('app_page') if session_policy.validate_and_touch() is None else url_for('login_page'))

    @app.get('/login')
    def login_page():
        if session_policy.validate_and_touch() is None:
            return redirect(url_for('app_page'))
        # AUTOLOGIN task (2026-09-04): ?noauto=1 is the explicit override
        # requirement #5 asks for -- without it, a deliberate logout
        # (app.js redirects to /login?noauto=1) would otherwise land back on
        # an auto-login page that instantly re-authenticates, making the
        # logged-out state and manual/different-persona login impossible to
        # actually reach while the flag is on.
        manual=request.args.get('noauto') in ('1','true')
        return render_template(
            'login.html',
            version=__version__,
            next_url=request.args.get('next') or '/app',
            test_auto_login=(
                not manual
                and settings.test_auto_login
                and _auto_login_allowed()
            ),
        )

    @app.get('/app')
    def app_page():
        if session_policy.validate_and_touch() is not None:
            return redirect(url_for('login_page'))
        permissions=RBACRepository().permissions_for_role(session.get('role'))
        return render_template('app.html', version=__version__, username=session.get('username'), role=session.get('role'), session_user_id=session.get('user_id'), permissions=permissions)

    @app.get('/api/tutorials')
    def tutorial_manifest():
        if session_policy.validate_and_touch() is not None:
            return jsonify(ok=False,error='AUTH_REQUIRED'),401
        tutorial_root=Path(os.environ.get('MESFLOW_TUTORIAL_DIR','/data/tutorials')).resolve()
        manifest_path=tutorial_root/'manifest.json'
        data={'version':1,'title':'Hướng dẫn sử dụng KIMEX','items':[]}
        if manifest_path.is_file():
            try:
                loaded=json.loads(manifest_path.read_text(encoding='utf-8'))
                if isinstance(loaded,dict):
                    data.update(loaded)
            except Exception:
                pass
        # Keep only files that physically exist and expose relative URLs only.
        safe=[]
        for item in list(data.get('items') or []):
            filename=str(item.get('file') or '').strip().replace('\\','/')
            if not filename or filename.startswith('/') or '..' in Path(filename).parts:
                continue
            target=(tutorial_root/filename).resolve()
            try:
                target.relative_to(tutorial_root)
            except ValueError:
                continue
            if not target.is_file():
                continue
            clean=dict(item)
            clean['file']=filename
            clean['url']='/tutorials/'+filename
            clean['size_bytes']=target.stat().st_size
            safe.append(clean)
        data['items']=safe
        return jsonify(ok=True,manifest=data)

    @app.get('/tutorials/<path:filename>')
    def tutorial_video(filename):
        if session_policy.validate_and_touch() is not None:
            return jsonify(ok=False,error='AUTH_REQUIRED'),401
        tutorial_root=Path(os.environ.get('MESFLOW_TUTORIAL_DIR','/data/tutorials')).resolve()
        candidate=(tutorial_root/filename).resolve()
        try:
            candidate.relative_to(tutorial_root)
        except ValueError:
            abort(404)
        if not candidate.is_file():
            abort(404)
        response=send_from_directory(tutorial_root,filename,conditional=True)
        response.headers['Cache-Control']='no-cache' if filename=='manifest.json' else 'public, max-age=86400'
        response.headers['Accept-Ranges']='bytes'
        return response

    @app.get('/api/esp-kiosk-tutorial')
    def esp_kiosk_tutorial_manifest():
        if session_policy.validate_and_touch() is not None:
            return jsonify(ok=False,error='AUTH_REQUIRED'),401
        root=Path(os.environ.get('MESFLOW_ESP_TUTORIAL_DIR','/data/tutorials/esp-kiosk')).resolve()
        manifest_path=root/'manifest.json'
        if not manifest_path.is_file():
            return jsonify(ok=True,manifest=None)
        try:
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError) as ex:
            return jsonify(ok=False,error='TUTORIAL_MANIFEST_INVALID',message=str(ex)),503
        if not isinstance(manifest,dict) or manifest.get('type')!='esp-kiosk-tutorial':
            return jsonify(ok=False,error='TUTORIAL_MANIFEST_INVALID'),503
        safe=[]
        for item in list(manifest.get('videos') or []):
            if not isinstance(item,dict): continue
            filename=str(item.get('filename') or '').strip()
            if not filename or Path(filename).name!=filename or not filename.lower().endswith('.mp4'): continue
            target=(root/'videos'/filename).resolve()
            try: target.relative_to(root/'videos')
            except ValueError: continue
            if not target.is_file(): continue
            version=str(manifest.get('tutorial_version') or '')
            clean=dict(item);clean.pop('file',None);clean['url']='/esp-kiosk-tutorial/videos/'+filename+'?v='+version;clean['size_bytes']=target.stat().st_size
            safe.append(clean)
        response=dict(manifest);response['videos']=sorted(safe,key=lambda item:int(item.get('order',999)))
        result=jsonify(ok=True,manifest=response)
        result.headers['Cache-Control']='no-cache, max-age=0, must-revalidate'
        return result

    @app.get('/esp-kiosk-tutorial/videos/<path:filename>')
    def esp_kiosk_tutorial_video(filename):
        if session_policy.validate_and_touch() is not None: return jsonify(ok=False,error='AUTH_REQUIRED'),401
        if Path(filename).name!=filename or not filename.lower().endswith('.mp4'): abort(404)
        root=Path(os.environ.get('MESFLOW_ESP_TUTORIAL_DIR','/data/tutorials/esp-kiosk')).resolve()
        manifest_path=root/'manifest.json'
        if not manifest_path.is_file(): abort(404)
        try: allowed={str(item.get('filename')) for item in json.loads(manifest_path.read_text(encoding='utf-8')).get('videos',[]) if isinstance(item,dict)}
        except (OSError,json.JSONDecodeError): abort(404)
        if filename not in allowed: abort(404)
        result=send_from_directory(root/'videos',filename,conditional=True)
        result.headers['Cache-Control']='public, max-age=31536000, immutable'
        return result

    @app.get('/dashboard')
    def dashboard_page():
        return redirect(url_for('app_page'))

    @app.get('/admin')
    @app.get('/admin/')
    def admin_page():
        if session_policy.validate_and_touch() is not None:
            return redirect(url_for('login_page', next=request.path))
        return redirect(url_for('app_page'))

    @app.get('/api/auth/me')
    def auth_me():
        expired_reason=session_policy.validate_and_touch()
        if expired_reason is not None:
            return jsonify(ok=False,error='AUTH_REQUIRED' if expired_reason=='NOT_LOGGED_IN' else 'SESSION_EXPIRED',reason=expired_reason),401
        user=UserRepository().get_by_id(session.get('user_id'))
        return jsonify(ok=True,user={'id':session.get('user_id'),'username':session.get('username'),'role':session.get('role'),'display_name':user['display_name'] if user else session.get('username'),'must_change_password':bool(user and user['must_change_password']),'permissions':RBACRepository().permissions_for_role(session.get('role'))})

    @app.post('/api/auth/test-auto-login')
    def test_auto_login():
        if not _auto_login_allowed():
            app.logger.warning(
                "Auto-login attempted on a MESFLOW_ENV=production deployment without "
                "MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1 -- refusing (fail-closed)."
            )
            return jsonify(ok=False,error='AUTO_LOGIN_DISABLED_PRODUCTION'),403
        if not settings.test_auto_login:
            return jsonify(ok=False,error='AUTO_LOGIN_DISABLED'),403
        # AUTOLOGIN task (2026-09-04): optional quick persona switch for RBAC
        # testing (requirement #4) -- non-production only (same guard as
        # above), fixed allowlist only (never an arbitrary username), still
        # goes through the exact same server-side session_policy.start_session
        # bootstrap as the default path below, no separate code path/bypass.
        persona=(request.get_json(silent=True) or {}).get('persona') or request.args.get('persona')
        if persona:
            persona=str(persona).strip().lower()
            if persona not in _AUTOLOGIN_PERSONAS:
                return jsonify(ok=False,error='AUTO_LOGIN_INVALID_PERSONA',allowed=list(_AUTOLOGIN_PERSONAS)),400
            username=persona
        else:
            username=settings.test_auto_login_username
        u=UserRepository().get_by_username(username)
        if not u or not u['active']:
            return jsonify(ok=False,error='AUTO_LOGIN_USER_NOT_FOUND',message='Không tìm thấy tài khoản auto-login đang hoạt động.'),503
        session_policy.start_session(u['id'],u['username'],u['role'])
        return jsonify(ok=True,user={'id':u['id'],'username':u['username'],'role':u['role'],'must_change_password':u['must_change_password'],'permissions':RBACRepository().permissions_for_role(u['role'])})

    @app.post('/api/auth/login')
    def login():
        # SECURITY_AUDIT (section 3): login attempts are business/account
        # events that belong with MESFlow, not buried only in the generic
        # technical action_logs trace. Never logs the submitted password.
        b=request.get_json(silent=True) or {}
        username=str(b.get('username','')).strip()
        u=UserRepository().get_by_username(username)
        if not u or not u['active'] or not check_password_hash(u['password_hash'],str(b.get('password',''))):
            try: AuditRepository().log(username,'LOGIN_FAILED','user','',{'reason':'inactive' if u and not u['active'] else 'invalid_credentials'})
            except Exception: pass
            return jsonify(ok=False,error='INVALID_CREDENTIALS'),401
        session_policy.start_session(u['id'],u['username'],u['role'],kiosk_mode=bool(b.get('kiosk_mode')))
        try: AuditRepository().log(u['username'],'LOGIN_SUCCESS','user',str(u['id']),{})
        except Exception: pass
        return jsonify(ok=True,user={'id':u['id'],'username':u['username'],'role':u['role'],'must_change_password':u['must_change_password'],'permissions':RBACRepository().permissions_for_role(u['role'])})

    @app.post('/api/auth/logout')
    def logout():
        session.clear(); return jsonify(ok=True)
    return app
