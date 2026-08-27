from flask import Blueprint,g,jsonify,request,session
from mesflow.core.config import settings
from mesflow.db.connection import fetch_all,fetch_one
from mesflow.services import system_audit_service
from mesflow.services.system_health_service import SystemHealthService
from mesflow.services.system_operations_service import SERVICE_ALLOWLIST,SystemOperationsService
from mesflow.services.diagnostic_service import DiagnosticService,LogService
from mesflow.services.notification_service import NotificationDispatcher
from mesflow.services.predictive_service import PredictiveService
from mesflow.services.recurrence_service import RecurrenceService
from mesflow.services.ai_incident_service import IncidentAIService
from mesflow.web.auth import login_required,super_admin_required
bp=Blueprint('system_health',__name__,url_prefix='/api/system-health')
# SUPER_ADMIN / IT System Console (task spec): this whole blueprint is
# technical/infrastructure surface -- health, logs, diagnostics, incident
# AI analysis, and (below) service control + system audit. It previously
# allowed admin/manager/supervisor; the spec's explicit objective is that
# ordinary business roles (including plain ADMIN) must no longer see any
# of this, so both helpers now require the literal super_admin role. No
# existing frontend page consumed this blueprint before this change (grep
# confirmed no static/pages/*.js reference), so this re-gate is not a
# regression to any working screen.
def ok():return str(session.get('role') or '').lower()=='super_admin'
def admin_only():return ok()
def _alert_or_404(alert_id):
 return fetch_one('SELECT * FROM health_alerts WHERE id=%s',(alert_id,))
@bp.get('')
@login_required
def summary():
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 from mesflow import __version__
 # System Overview identity fields (spec section 6/7): environment/server_role
 # are MESFlow's existing source of truth (mesflow.core.config.settings --
 # the same fields kiosk_v2/health providers already key behavior off of),
 # not re-derived or guessed from hostname styling.
 return jsonify(ok=True,application_version=__version__,environment=settings.environment,
                server_role=settings.server_role,**SystemHealthService().summary(getattr(g,'trace_id','')))
@bp.get('/kiosks')
@login_required
def kiosks():
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 c=next(x for x in SystemHealthService().summary()['components'] if x['component']=='KIOSK_FLEET');return jsonify(ok=True,**c['details'])
@bp.get('/kiosks/<device_uuid>')
@login_required
def kiosk(device_uuid):
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 items=next(x for x in SystemHealthService().summary()['components'] if x['component']=='KIOSK_FLEET')['details']['items'];x=next((x for x in items if x['device_uuid']==device_uuid),None);return (jsonify(ok=True,item=x) if x else (jsonify(ok=False,error='NOT_FOUND'),404))
@bp.get('/history')
@login_required
def history():return (jsonify(ok=False,error='FORBIDDEN'),403) if not ok() else jsonify(ok=True,items=SystemHealthService().history(int(request.args.get('limit',200))))

# --- Phase 2: Notification + Diagnosis -----------------------------------

@bp.get('/alerts/<int:alert_id>/diagnostics')
@login_required
def alert_diagnostics(alert_id):
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 alert=_alert_or_404(alert_id)
 if not alert:return jsonify(ok=False,error='NOT_FOUND'),404
 rows=fetch_all('SELECT * FROM health_diagnostics_snapshots WHERE alert_fingerprint=%s ORDER BY id DESC LIMIT 5',(alert['fingerprint'],))
 if not rows:
  # No auto-captured SUMMARY snapshot yet (alert predates this feature, or
  # capture failed silently) -- take one now rather than showing nothing.
  rows=[DiagnosticService().snapshot(alert['component'],'SUMMARY',alert_fingerprint=alert['fingerprint'],correlation_id=str(getattr(g,'trace_id','') or ''))]
 return jsonify(ok=True,items=rows)

@bp.post('/alerts/<int:alert_id>/diagnostics')
@login_required
def alert_diagnostics_refresh(alert_id):
 # Section 37: "Run diagnostics again" -- admin-only, DETAIL level,
 # read-only, does not resolve the incident.
 if not admin_only():return jsonify(ok=False,error='FORBIDDEN'),403
 alert=_alert_or_404(alert_id)
 if not alert:return jsonify(ok=False,error='NOT_FOUND'),404
 snap=DiagnosticService().snapshot(alert['component'],'DETAIL',alert_fingerprint=alert['fingerprint'],
   correlation_id=str(getattr(g,'trace_id','') or ''),requested_by_user_id=session.get('user_id'))
 return jsonify(ok=True,item=snap)

@bp.get('/alerts/<int:alert_id>/notifications')
@login_required
def alert_notifications(alert_id):
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 alert=_alert_or_404(alert_id)
 if not alert:return jsonify(ok=False,error='NOT_FOUND'),404
 items=fetch_all('SELECT * FROM notification_deliveries WHERE alert_fingerprint=%s ORDER BY id DESC LIMIT 50',(alert['fingerprint'],))
 return jsonify(ok=True,items=items)

@bp.get('/logs')
@login_required
def logs():
 # Section 17-21: bounded, allowlisted, admin-only -- never an arbitrary
 # path/command from the browser.
 if not admin_only():return jsonify(ok=False,error='FORBIDDEN'),403
 result=LogService().fetch(request.args.get('source',''),request.args.get('lines',200))
 # `result` already carries its own "ok" key -- do not also pass ok=...
 # as a keyword (jsonify(ok=..., **result) raised a duplicate-keyword
 # TypeError -> 500 for every unknown-source request, caught live here).
 return (jsonify(**result),400) if result.get('error')=='UNKNOWN_SOURCE' else jsonify(**result)

@bp.get('/notification-channels')
@login_required
def notification_channels():
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 d=NotificationDispatcher()
 return jsonify(ok=True,channels={name:{'configured':ch.configured()} for name,ch in d.channels.items()})

@bp.post('/notification-channels/<channel>/test')
@login_required
def notification_channel_test(channel):
 # Section 44-46: explicit test send only, admin-only.
 if not admin_only():return jsonify(ok=False,error='FORBIDDEN'),403
 if channel.upper() not in ('EMAIL','TELEGRAM','WEB'):return jsonify(ok=False,error='UNKNOWN_CHANNEL'),400
 return jsonify(NotificationDispatcher().test(channel.upper()))

# --- Phase 3: Predictive / AI --------------------------------------------

@bp.get('/predictions')
@login_required
def predictions():
 # section 39/57: predictive warnings are visible to supervisor+; the
 # underlying evidence detail (drawer) stays admin-gated per component.
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 return jsonify(ok=True,items=PredictiveService().active())

@bp.get('/recurring-incidents')
@login_required
def recurring_incidents():
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 return jsonify(ok=True,items=RecurrenceService().detect())

@bp.get('/metrics/<metric>/trend')
@login_required
def metric_trend(metric):
 # Technical trend data -- admin-only (section 57).
 if not admin_only():return jsonify(ok=False,error='FORBIDDEN'),403
 from mesflow.services.metrics_service import samples_for
 component=request.args.get('component','')
 days=min(max(int(request.args.get('days',30)),1),90)
 rows=samples_for(metric,component,days)
 return jsonify(ok=True,metric=metric,component=component,items=[{'value':r['value'],'sampled_at':r['sampled_at']} for r in rows])

@bp.get('/alerts/<int:alert_id>/ai-analysis')
@login_required
def alert_ai_analysis(alert_id):
 if not ok():return jsonify(ok=False,error='FORBIDDEN'),403
 alert=_alert_or_404(alert_id)
 if not alert:return jsonify(ok=False,error='NOT_FOUND'),404
 stage='RECOVERED' if alert.get('resolved_at') else 'OPEN'
 diag=fetch_one('SELECT data_json FROM health_diagnostics_snapshots WHERE alert_fingerprint=%s ORDER BY id DESC LIMIT 1',(alert['fingerprint'],))
 similar=fetch_all("SELECT opened_at,resolved_at FROM health_alerts WHERE fingerprint=%s AND id<>%s ORDER BY opened_at DESC LIMIT 10",(alert['fingerprint'],alert_id))
 result=IncidentAIService().analyze(alert,stage,diagnostics_snapshot=(diag or {}).get('data_json'),recent_incidents=similar)
 return jsonify(ok=True,item=result,similar_incidents=similar)

@bp.post('/alerts/<int:alert_id>/ai-analysis/regenerate')
@login_required
def alert_ai_analysis_regenerate(alert_id):
 # section 30: explicit user-requested regenerate, admin-only, recorded with actor.
 if not admin_only():return jsonify(ok=False,error='FORBIDDEN'),403
 alert=_alert_or_404(alert_id)
 if not alert:return jsonify(ok=False,error='NOT_FOUND'),404
 stage='RECOVERED' if alert.get('resolved_at') else 'OPEN'
 diag=fetch_one('SELECT data_json FROM health_diagnostics_snapshots WHERE alert_fingerprint=%s ORDER BY id DESC LIMIT 1',(alert['fingerprint'],))
 similar=fetch_all("SELECT opened_at,resolved_at FROM health_alerts WHERE fingerprint=%s AND id<>%s ORDER BY opened_at DESC LIMIT 10",(alert['fingerprint'],alert_id))
 result=IncidentAIService().analyze(alert,stage,diagnostics_snapshot=(diag or {}).get('data_json'),recent_incidents=similar,
   requested_by_user_id=session.get('user_id'),force=True)
 return jsonify(ok=True,item=result)

# --- SUPER_ADMIN System Console: System Errors (spec section 9) ---------

@bp.get('/errors')
@super_admin_required
def system_errors():
 # Reuses SystemHealthService.errors() exactly -- the same query that
 # already feeds summary()['recent_errors'] -- just with a caller-chosen
 # window/limit instead of the fixed rollup. Deliberately a DIFFERENT
 # table/query than product NG counts or Session Exceptions (spec section
 # 8): this only ever reads action_logs ERROR/FAILED rows and kiosk_events
 # ERROR/CRITICAL rows -- neither table has any notion of NG quantity or
 # session-exception state, so the three domains cannot leak into each
 # other here even accidentally.
 limit=min(max(int(request.args.get('limit',100)),1),500)
 return jsonify(ok=True,items=SystemHealthService().errors(limit))

# --- SUPER_ADMIN System Console: allow-listed Service Control -----------
# (spec section 11/12/22-26; SystemOperationsService proxies to Deploy
# Agent's existing RecoveryOrchestrator -- see that module's docstring)

@bp.get('/services')
@super_admin_required
def system_services():
 return jsonify(ok=True,items=SystemOperationsService().list_services())

@bp.post('/services/<service_id>/restart')
@super_admin_required
def system_service_restart(service_id):
 if service_id not in SERVICE_ALLOWLIST:
  return jsonify(ok=False,error='UNKNOWN_SERVICE',message='Dịch vụ không nằm trong danh sách cho phép'),404
 body=request.get_json(silent=True) or {}
 reason=str(body.get('reason','')).strip()
 if not reason:
  return jsonify(ok=False,error='REASON_REQUIRED',message='Vui lòng nhập lý do trước khi khởi động lại dịch vụ'),400
 is_production=str(settings.environment).strip().lower()=='production'
 confirmed=bool(body.get('confirm_production'))
 # Production safety (spec section 26): never infer/default production
 # approval -- the operator must have explicitly confirmed against the
 # server's own real environment identity, not a client-supplied guess.
 if is_production and not confirmed:
  return jsonify(ok=False,error='PRODUCTION_CONFIRMATION_REQUIRED',environment=settings.environment,
                message='Thao tác trên PRODUCTION yêu cầu xác nhận rõ ràng'),409
 correlation_id=str(getattr(g,'trace_id','') or '')
 result=SystemOperationsService().restart_service(
   service_id,actor=session.get('username',''),reason=reason,
   production_approved=is_production and confirmed,correlation_id=correlation_id)
 system_audit_service.record('RESTART_SERVICE',target=service_id,reason=reason,
   result=result.get('result','UNKNOWN'),correlation_id=correlation_id,detail=result)
 return jsonify(ok=result.get('ok',False),item=result)

# --- SUPER_ADMIN System Console: standalone Diagnostics (spec 14) -------
# (distinct from the existing alert-scoped /alerts/<id>/diagnostics above:
# this runs a named check on demand, with no alert required.)

DIAGNOSTIC_COMPONENTS={'MESFLOW':'Ứng dụng MESFlow','POSTGRESQL':'Cơ sở dữ liệu','SERVER':'Máy chủ / Docker',
 'DEPLOY_AGENT':'Deploy Agent','QA_CENTER':'QA Center','KIOSK_FLEET':'Trạm kiosk'}

@bp.get('/diagnostics')
@super_admin_required
def diagnostics_list():
 return jsonify(ok=True,items=[{'id':k,'label':v} for k,v in DIAGNOSTIC_COMPONENTS.items()])

@bp.post('/diagnostics/<component>')
@super_admin_required
def diagnostics_run(component):
 component=component.upper()
 if component not in DIAGNOSTIC_COMPONENTS:
  return jsonify(ok=False,error='UNKNOWN_DIAGNOSTIC',message='Không có mục chẩn đoán này'),404
 # Read-only by construction -- DiagnosticService._collect() only ever
 # SELECTs / makes GET calls to Deploy Agent (see that module's docstring:
 # "no diagnostic path may mutate infrastructure").
 snap=DiagnosticService().snapshot(component,'DETAIL',correlation_id=str(getattr(g,'trace_id','') or ''),
   requested_by_user_id=session.get('user_id'))
 return jsonify(ok=True,item=snap)

# --- SUPER_ADMIN System Console: System Audit (spec section 16) ---------

@bp.get('/audit')
@super_admin_required
def system_audit():
 limit=min(max(int(request.args.get('limit',200)),1),1000)
 return jsonify(ok=True,items=system_audit_service.list_recent(limit))
