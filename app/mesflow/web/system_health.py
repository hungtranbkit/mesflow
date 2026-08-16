from flask import Blueprint,g,jsonify,request,session
from mesflow.db.connection import fetch_all,fetch_one
from mesflow.services.system_health_service import SystemHealthService
from mesflow.services.diagnostic_service import DiagnosticService,LogService
from mesflow.services.notification_service import NotificationDispatcher
from mesflow.services.predictive_service import PredictiveService
from mesflow.services.recurrence_service import RecurrenceService
from mesflow.services.ai_incident_service import IncidentAIService
from mesflow.web.auth import login_required
bp=Blueprint('system_health',__name__,url_prefix='/api/system-health')
def ok():return str(session.get('role') or '').lower() in ('admin','manager','supervisor')
def admin_only():
 # Section 30/47: technical diagnostics, logs, and channel testing are
 # admin-only -- supervisors get alerts/basic context but not this.
 return str(session.get('role') or '').lower()=='admin'
def _alert_or_404(alert_id):
 return fetch_one('SELECT * FROM health_alerts WHERE id=%s',(alert_id,))
@bp.get('')
@login_required
def summary():return (jsonify(ok=False,error='FORBIDDEN'),403) if not ok() else jsonify(ok=True,**SystemHealthService().summary(getattr(g,'trace_id','')))
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
