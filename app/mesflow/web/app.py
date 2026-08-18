from pathlib import Path
import json
import os
from flask import Flask, jsonify, request, session, render_template, redirect, url_for, send_from_directory, abort, g
from werkzeug.security import check_password_hash
from werkzeug.exceptions import HTTPException
from flask.sessions import SecureCookieSessionInterface
from mesflow import __version__
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
    return host in {"mesflow-app","mesflow"} and not forwarded_proto


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
    app.register_blueprint(master_data_bp)
    app.register_blueprint(execution_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(exceptions_bp)
    app.register_blueprint(production_trace_bp)
    app.register_blueprint(system_health_bp)
    app.register_blueprint(excel_io_bp)
    app.register_blueprint(template_excel_bp)
    app.register_blueprint(kiosk_bp)
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
        if not session.get('user_id'):
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
            repo=SystemRepository()
            check=repo.readiness()
            return jsonify(ok=True,status='ready',checked_at=check['checked_at'],schema_version=repo.schema_version(),migration_head=repo.migration_head(),version=__version__)
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
        return redirect(url_for('app_page') if session.get('user_id') else url_for('login_page'))

    @app.get('/login')
    def login_page():
        if session.get('user_id'):
            return redirect(url_for('app_page'))
        return render_template(
            'login.html',
            version=__version__,
            next_url=request.args.get('next') or '/app',
            test_auto_login=(
                settings.environment != "production"
                and settings.test_auto_login
            ),
        )

    @app.get('/app')
    def app_page():
        if not session.get('user_id'):
            return redirect(url_for('login_page'))
        permissions=RBACRepository().permissions_for_role(session.get('role'))
        return render_template('app.html', version=__version__, username=session.get('username'), role=session.get('role'), session_user_id=session.get('user_id'), permissions=permissions)

    @app.get('/api/tutorials')
    def tutorial_manifest():
        if not session.get('user_id'):
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
        if not session.get('user_id'):
            return jsonify(ok=False,error='AUTH_REQUIRED'),401
        tutorial_root=Path(os.environ.get('MESFLOW_TUTORIAL_DIR','/data/tutorials')).resolve()
        candidate=(tutorial_root/filename).resolve()
        try:
            candidate.relative_to(tutorial_root)
        except ValueError:
            abort(404)
        if not candidate.is_file():
            abort(404)
        return send_from_directory(tutorial_root,filename,conditional=True)

    @app.get('/api/esp-kiosk-tutorial')
    def esp_kiosk_tutorial_manifest():
        if not session.get('user_id'):
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
        if not session.get('user_id'): return jsonify(ok=False,error='AUTH_REQUIRED'),401
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
        if not session.get('user_id'):
            return redirect(url_for('login_page', next=request.path))
        return redirect(url_for('app_page'))

    @app.get('/api/auth/me')
    def auth_me():
        if not session.get('user_id'):
            return jsonify(ok=False,error='AUTH_REQUIRED'),401
        user=UserRepository().get_by_id(session.get('user_id'))
        return jsonify(ok=True,user={'id':session.get('user_id'),'username':session.get('username'),'role':session.get('role'),'display_name':user['display_name'] if user else session.get('username'),'must_change_password':bool(user and user['must_change_password']),'permissions':RBACRepository().permissions_for_role(session.get('role'))})

    @app.post('/api/auth/test-auto-login')
    def test_auto_login():
        if settings.environment == "production":
            return jsonify(ok=False,error='AUTO_LOGIN_DISABLED_PRODUCTION'),403
        if not settings.test_auto_login:
            return jsonify(ok=False,error='AUTO_LOGIN_DISABLED'),403
        u=UserRepository().get_by_username(settings.test_auto_login_username)
        if not u or not u['active']:
            return jsonify(ok=False,error='AUTO_LOGIN_USER_NOT_FOUND',message='Không tìm thấy tài khoản auto-login đang hoạt động.'),503
        session['user_id']=u['id']; session['username']=u['username']; session['role']=u['role']
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
        session['user_id']=u['id']; session['username']=u['username']; session['role']=u['role']
        try: AuditRepository().log(u['username'],'LOGIN_SUCCESS','user',str(u['id']),{})
        except Exception: pass
        return jsonify(ok=True,user={'id':u['id'],'username':u['username'],'role':u['role'],'must_change_password':u['must_change_password'],'permissions':RBACRepository().permissions_for_role(u['role'])})

    @app.post('/api/auth/logout')
    def logout():
        session.clear(); return jsonify(ok=True)
    return app
