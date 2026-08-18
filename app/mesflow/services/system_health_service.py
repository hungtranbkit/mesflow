from __future__ import annotations
import functools,hashlib,json,re,time,urllib.request
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
from mesflow import __version__
from mesflow.core.config import settings
from mesflow.db.connection import fetch_all,fetch_one,transaction
from mesflow.domain.health import HealthCheckResult,HealthStatus,overall
def now():return datetime.now(timezone.utc)

@functools.lru_cache(maxsize=1)
def _latest_migration_revision():
 """Derived from the migrations directory instead of a hand-maintained
 literal -- a hardcoded expected-revision string here has already gone
 stale twice in one week (V69b, V69c) the moment a later migration was
 added without remembering to bump it. Memoized: migration files don't
 change at runtime, only at deploy time (new container image)."""
 versions_dir=Path(__file__).resolve().parents[2]/'migrations'/'versions'
 best_num=-1;best_rev=''
 for f in versions_dir.glob('*.py'):
  m=re.match(r'(\d+)_',f.name)
  if not m:continue
  num=int(m.group(1))
  if num>best_num:
   text=f.read_text(encoding='utf-8')
   rev=re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]",text,re.MULTILINE)
   if rev:best_num=num;best_rev=rev.group(1)
 return best_rev
class Provider:
 component='';critical=False
 def r(self,status,message='',latency=None,details=None,configured=True):return HealthCheckResult(self.component,status,now(),latency,message,details or {},self.critical,configured)
class MESFlowProvider(Provider):
 component='MESFLOW';critical=True
 def check(self):
  n=fetch_one("SELECT COUNT(*) n FROM error_traces WHERE NOT resolved AND created_at>CURRENT_TIMESTAMP-INTERVAL '1 hour'")['n'];return self.r(HealthStatus.DEGRADED if n else HealthStatus.HEALTHY,f'{n} lỗi chưa xử lý' if n else 'Ứng dụng sẵn sàng',details={'version':__version__,'recent_errors':n})
class PostgreSQLProvider(Provider):
 component='POSTGRESQL';critical=True
 def check(self):
  t=time.perf_counter()
  try:
   x=fetch_one("SELECT version() database_version,(SELECT COUNT(*) FROM pg_stat_activity) connections,(SELECT setting::int FROM pg_settings WHERE name='max_connections') max_connections,(SELECT version_num FROM alembic_version) migration_revision")
   ms=int((time.perf_counter()-t)*1000);x['expected_revision']=_latest_migration_revision();bad=x['migration_revision']!=x['expected_revision']
   return self.r(HealthStatus.DEGRADED if bad or ms>settings.health_db_latency_warning_ms else HealthStatus.HEALTHY,'Migration không khớp' if bad else 'Cơ sở dữ liệu phản hồi',ms,x)
  except Exception as e:return self.r(HealthStatus.DOWN,'Không kết nối được cơ sở dữ liệu',int((time.perf_counter()-t)*1000),{'error':type(e).__name__})
class HTTPProvider(Provider):
 def __init__(self,name,url):self.component=name;self.url=url
 def check(self):
  if not self.url:return self.r(HealthStatus.UNKNOWN,'Chưa cấu hình',details={'state':'NOT_CONFIGURED'},configured=False)
  t=time.perf_counter()
  try:
   with urllib.request.urlopen(self.url+'/api/status',timeout=settings.health_external_timeout_seconds) as r:x=json.loads(r.read(256000))
   latest=x.get('latest') or x.get('last_run') or {};failed=str(latest.get('status') or '').upper() in ('FAILED','FAIL','COMPLETED_WITH_ERRORS');return self.r(HealthStatus.DEGRADED if failed else HealthStatus.HEALTHY,'Lần chạy gần nhất thất bại' if failed else 'Dịch vụ phản hồi',int((time.perf_counter()-t)*1000),{'version':x.get('version'),'latest':latest,'active':x.get('active')})
  except Exception as e:return self.r(HealthStatus.DOWN,'Không thể kết nối',int((time.perf_counter()-t)*1000),{'error':type(e).__name__})
class DeployAgentFetch:
 """One shared fetch against the Deploy Agent, reused by
 DeployAgentProvider/ServerProvider/DockerProvider so a single System
 Health refresh makes at most two bounded HTTP calls to the Agent, not six.
 `/health` is public (no credentials); `/api/ops/summary` requires either a
 browser session on the Agent (N/A here) or the shared
 MESFLOW_INTERNAL_API_TOKEN header -- same secret MESFlow's own
 internal_ota routes already validate in the reverse direction."""
 def __init__(self):self.health=None;self.ops=None;self.health_error=None;self.ops_error=None
 def fetch(self):
  if not settings.health_deploy_agent_url:return self
  t=time.perf_counter()
  try:
   with urllib.request.urlopen(settings.health_deploy_agent_url+'/health',timeout=settings.health_external_timeout_seconds) as r:self.health=json.loads(r.read(65536))
   self.health_latency_ms=int((time.perf_counter()-t)*1000)
  except Exception as e:self.health_error=type(e).__name__;return self
  try:
   headers={'X-MESFlow-Internal-Token':settings.internal_api_token} if settings.internal_api_token else {}
   req=urllib.request.Request(settings.health_deploy_agent_url+'/api/ops/summary',headers=headers)
   with urllib.request.urlopen(req,timeout=settings.health_external_timeout_seconds) as r:self.ops=json.loads(r.read(131072))
  except Exception as e:self.ops_error=type(e).__name__
  return self
class DeployAgentProvider(Provider):
 component='DEPLOY_AGENT';critical=False
 def __init__(self,fetch):self.fetch=fetch
 def check(self):
  if not settings.health_deploy_agent_url:return self.r(HealthStatus.UNKNOWN,'Chưa cấu hình',details={'state':'NOT_CONFIGURED'},configured=False)
  if self.fetch.health_error:return self.r(HealthStatus.DOWN,'Không thể kết nối Deploy Agent',details={'error':self.fetch.health_error})
  h=self.fetch.health or {}
  return self.r(HealthStatus.HEALTHY,'Agent phản hồi',getattr(self.fetch,'health_latency_ms',None),{'version':h.get('agent_version'),'server_role':h.get('server_role'),'build_enabled':h.get('build_enabled'),'deploy_enabled':h.get('deploy_enabled')})
class ServerProvider(Provider):
 # "Server offline" is one of the explicit DOWN conditions -- critical=True.
 component='SERVER';critical=True
 def __init__(self,fetch):self.fetch=fetch
 def check(self):
  if not settings.health_deploy_agent_url:return self.r(HealthStatus.UNKNOWN,'Chưa cấu hình',details={'state':'NOT_CONFIGURED'},configured=False)
  if self.fetch.health_error:return self.r(HealthStatus.DOWN,'Không có tín hiệu từ server (Agent không phản hồi)',details={'error':self.fetch.health_error})
  ops=self.fetch.ops
  if not ops:return self.r(HealthStatus.UNKNOWN,'Không lấy được số liệu server',details={'error':self.fetch.ops_error or 'OPS_UNAVAILABLE'})
  cpu=ops.get('cpu_percent') or 0;ram=(ops.get('ram') or {}).get('percent') or 0;disk=(ops.get('disk') or {}).get('percent') or 0
  warn=cpu>=settings.health_cpu_warning_percent or ram>=settings.health_ram_warning_percent or disk>=settings.health_disk_warning_percent
  return self.r(HealthStatus.DEGRADED if warn else HealthStatus.HEALTHY,'Online',details={'hostname':ops.get('hostname'),'os':ops.get('os'),'uptime_seconds':ops.get('uptime_seconds'),'cpu_percent':cpu,'ram':ops.get('ram'),'disk':ops.get('disk'),'load':ops.get('load')})
class DockerProvider(Provider):
 component='DOCKER';critical=False
 def __init__(self,fetch):self.fetch=fetch
 def check(self):
  if not settings.health_deploy_agent_url:return self.r(HealthStatus.UNKNOWN,'Chưa cấu hình',details={'state':'NOT_CONFIGURED'},configured=False)
  if self.fetch.health_error:return self.r(HealthStatus.UNKNOWN,'Không lấy được số liệu Docker',details={'error':self.fetch.health_error})
  ops=self.fetch.ops
  if not ops:return self.r(HealthStatus.UNKNOWN,'Không lấy được số liệu Docker',details={'error':self.fetch.ops_error or 'OPS_UNAVAILABLE'})
  unhealthy=ops.get('docker_unhealthy') or 0
  return self.r(HealthStatus.DEGRADED if unhealthy else HealthStatus.HEALTHY,f'{unhealthy} container unhealthy' if unhealthy else 'Docker daemon hoạt động',details={'running':ops.get('docker_running'),'unhealthy':unhealthy})
class KioskProvider(Provider):
 component='KIOSK_FLEET'
 def check(self):
  rows=fetch_all("""SELECT i.device_uuid,i.device_name,i.firmware_version,s.code station_code,s.name station_name,k.last_heartbeat_at,k.health_state,k.ui_state,k.queue_size,k.wifi_rssi,k.last_error,EXTRACT(EPOCH FROM(CURRENT_TIMESTAMP-k.last_heartbeat_at))::int age_seconds,(SELECT COUNT(*) FROM kiosk_client_events e WHERE e.kiosk_id=i.device_uuid AND e.status NOT IN ('APPLIED','REJECTED')) queued_events,(SELECT MAX(server_session_id) FROM kiosk_client_events e WHERE e.kiosk_id=i.device_uuid) last_session_id FROM kiosk_identities i LEFT JOIN kiosk_status k ON k.device_uuid=i.device_uuid LEFT JOIN stations s ON s.id=COALESCE(k.station_id,i.station_id) ORDER BY i.device_uuid""")
  counts={x:0 for x in ('ONLINE','DEGRADED','OFFLINE','UNKNOWN')};versions={}
  for x in rows:
   age=x.get('age_seconds');queue=int(x.get('queued_events') or x.get('queue_size') or 0);state='UNKNOWN' if age is None else ('OFFLINE' if age>settings.health_kiosk_offline_seconds else ('DEGRADED' if age>settings.health_kiosk_degraded_seconds or queue or str(x.get('health_state')).upper() in ('ERROR','DEGRADED') else 'ONLINE'));x['normalized_status']=state;counts[state]+=1;v=x.get('firmware_version') or 'unknown';versions[v]=versions.get(v,0)+1
  return self.r(HealthStatus.DEGRADED if counts['OFFLINE'] or counts['DEGRADED'] else (HealthStatus.HEALTHY if rows else HealthStatus.UNKNOWN),f"{counts['ONLINE']}/{len(rows)} online",details={'total':len(rows),'online':counts['ONLINE'],'offline':counts['OFFLINE'],'counts':counts,'versions':versions,'items':rows})
class JobProvider(Provider):
 component='JOBS'
 def check(self):
  rows=fetch_all("SELECT *,CASE WHEN NOT enabled THEN 'DISABLED' WHEN next_expected_at IS NOT NULL AND CURRENT_TIMESTAMP>next_expected_at+(grace_seconds||' seconds')::interval THEN 'MISSED' ELSE last_status END normalized_status FROM scheduled_job_health ORDER BY display_name");bad=sum(x['normalized_status'] in ('FAILED','MISSED') for x in rows);return self.r(HealthStatus.DEGRADED if bad else (HealthStatus.HEALTHY if rows else HealthStatus.UNKNOWN),f'{bad} job cần chú ý',details={'items':rows})
SEVERITY_ORDER={'CRITICAL':0,'HIGH':1,'MEDIUM':2,'LOW':3}
LABELS={'MESFLOW':'MESFlow','POSTGRESQL':'Database','SERVER':'Server','DOCKER':'Docker','DEPLOY_AGENT':'Deploy Agent','QA_CENTER':'QA Center','KIOSK_FLEET':'Kiosk Fleet'}
class SystemHealthService:
 def providers(self):
  fetch=DeployAgentFetch().fetch()
  return [MESFlowProvider(),PostgreSQLProvider(),ServerProvider(fetch),DockerProvider(fetch),DeployAgentProvider(fetch),HTTPProvider('QA_CENTER',settings.health_qa_url),KioskProvider(),JobProvider()]
 def summary(self,correlation_id=''):
  results=[]
  for p in self.providers():
   try:results.append(p.check())
   except Exception as e:results.append(p.r(HealthStatus.UNKNOWN,'Provider lỗi',details={'error':type(e).__name__}))
  by={x.component:x for x in results}
  kiosk_items=(by.get('KIOSK_FLEET').details or {}).get('items',[]) if by.get('KIOSK_FLEET') else []
  if settings.legacy_health_writer_enabled:
   # Deploy Agent is now authoritative for infra monitoring (see
   # reports/SYSTEM_LOG_AUDIT_SEPARATION.md). Off by default in real
   # deployments -- no new component_health_state/history or health_alerts
   # rows. Existing rows stay fully readable (history()/alerts stay a plain
   # SELECT either way) -- this only gates the write side.
   self.persist(results,correlation_id)
   conditions=self._alert_conditions(by,kiosk_items)
   active_alerts=self.sync_alerts(conditions,correlation_id)
  else:
   active_alerts=fetch_all("SELECT * FROM health_alerts WHERE resolved_at IS NULL ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,opened_at")
  errors=self.errors();action=fetch_one("SELECT COUNT(*) n FROM exception_records WHERE status IN ('OPEN','ACKNOWLEDGED')")['n']
  # Phase 3: read the already-computed predictive insights (cheap SELECT on
  # predictive_insights) -- forecast/anomaly/recurrence recomputation is a
  # separate scheduled job (mesflow.cli run-predictive), never inline on a
  # health poll (section 48).
  try:
   from mesflow.services.predictive_service import PredictiveService
   predictions=PredictiveService().active(limit=5)
  except Exception:
   predictions=[]
  return {'overall_status':overall(results).value,'checked_at':now(),'components':[asdict(x) for x in results],
          'action_required_count':action,'recent_errors_count':len(errors),'recent_errors':errors,
          'active_alerts':active_alerts,'active_alerts_count':len(active_alerts),
          'predictions':predictions}
 def _alert_conditions(self,by,kiosk_items):
  """One row per condition that deserves an actionable alert -- not every
  health measurement (section 17: fleet counts are a signal, a specific
  offline kiosk is an alert)."""
  out=[]
  for c in ('MESFLOW','POSTGRESQL','SERVER'):
   r=by.get(c)
   if r and r.configured and r.status==HealthStatus.DOWN:out.append((f'COMPONENT_DOWN:{c}',c,'CRITICAL',f'{LABELS.get(c,c)} DOWN',r.message,{}))
  da=by.get('DEPLOY_AGENT')
  if da and da.configured and da.status==HealthStatus.DOWN:out.append(('COMPONENT_DOWN:DEPLOY_AGENT','DEPLOY_AGENT','HIGH','Deploy Agent không phản hồi',da.message,{}))
  qa=by.get('QA_CENTER')
  if qa and qa.configured and qa.status==HealthStatus.DEGRADED and (qa.details or {}).get('latest'):out.append(('QA_LATEST_FAILED','QA_CENTER','MEDIUM','QA Center: lần test gần nhất thất bại',qa.message,{'latest':qa.details.get('latest')}))
  srv=by.get('SERVER')
  disk=(srv.details or {}).get('disk') if srv and srv.configured else None
  if disk:
   pct=disk.get('percent') or 0
   if pct>=settings.health_disk_critical_percent:out.append(('DISK_USAGE_HIGH','SERVER','HIGH',f'Disk usage {pct:.0f}%',f'Dung lượng đĩa đạt {pct:.0f}%, cần dọn dẹp/mở rộng.',{'percent':pct}))
   elif pct>=settings.health_disk_warning_percent:out.append(('DISK_USAGE_HIGH','SERVER','MEDIUM',f'Disk usage {pct:.0f}%',f'Dung lượng đĩa đạt {pct:.0f}%.',{'percent':pct}))
  for k in kiosk_items:
   if k.get('normalized_status')=='OFFLINE':
    age=k.get('age_seconds') or 0
    out.append((f"KIOSK_OFFLINE:{k['device_uuid']}",'KIOSK_FLEET','HIGH',f"{k.get('device_name') or k['device_uuid']} offline",f'Offline {age//60} phút',{'device_uuid':k['device_uuid'],'age_seconds':age}))
  jobs=by.get('JOBS')
  if jobs and jobs.configured:
   for j in (jobs.details or {}).get('items',[]):
    if j.get('normalized_status') in ('FAILED','MISSED'):out.append((f"JOB_{j['normalized_status']}:{j['job_name']}",'JOBS','MEDIUM',f"Job {j.get('display_name')} {j['normalized_status'].lower()}",j.get('last_error') or '',{'job_name':j['job_name']}))
  return out
 def sync_alerts(self,conditions,correlation_id='',notify=True):
  """Fingerprint dedup + recovery, per section 16/20: a condition that
  persists across polls stays ONE open row (upsert, no new insert); a
  condition no longer present closes (resolved_at set) -- that closure IS
  the recovery record surfaced in Incident History.

  Phase 2: also detects the exact transition edges (newly opened / newly
  resolved this cycle, via `(xmax=0)` on the upsert and the UPDATE's
  RETURNING -- the same "was this row actually inserted" trick already used
  elsewhere in this codebase for kiosk_events ingest) and dispatches
  notifications + a diagnostic snapshot ONLY on those edges, never on every
  poll while a condition merely continues (section 6/30)."""
  fingerprints=[c[0] for c in conditions]
  newly_opened=[];newly_resolved=[]
  with transaction() as conn:
   with conn.cursor() as cur:
    for fp,component,severity,title,message,metadata in conditions:
     cur.execute("""INSERT INTO health_alerts(fingerprint,component,severity,title,message,metadata_json,correlation_id)
       VALUES(%s,%s,%s,%s,%s,%s,%s)
       ON CONFLICT(fingerprint) WHERE resolved_at IS NULL DO UPDATE SET
         last_seen_at=CURRENT_TIMESTAMP,severity=EXCLUDED.severity,title=EXCLUDED.title,message=EXCLUDED.message,metadata_json=EXCLUDED.metadata_json
       RETURNING *,(xmax=0) inserted""",
       (fp,component,severity,title,message,json.dumps(metadata,default=str),correlation_id))
     row=cur.fetchone()
     if row and row.get('inserted'):newly_opened.append(row)
    if fingerprints:cur.execute("UPDATE health_alerts SET resolved_at=CURRENT_TIMESTAMP WHERE resolved_at IS NULL AND NOT(fingerprint=ANY(%s)) RETURNING *",(fingerprints,))
    else:cur.execute("UPDATE health_alerts SET resolved_at=CURRENT_TIMESTAMP WHERE resolved_at IS NULL RETURNING *")
    newly_resolved=cur.fetchall()
  if notify:
   from mesflow.services.notification_service import NotificationDispatcher
   from mesflow.services.diagnostic_service import DiagnosticService
   dispatcher=NotificationDispatcher();diag=DiagnosticService()
   for alert in newly_opened:
    try:dispatcher.dispatch(alert,'OPENED',correlation_id)
    except Exception:pass  # notification failure must never break health evaluation (section 32)
    try:diag.snapshot(alert['component'],'SUMMARY',alert_fingerprint=alert['fingerprint'],correlation_id=correlation_id)
    except Exception:pass
   for alert in newly_resolved:
    try:dispatcher.dispatch(alert,'RESOLVED',correlation_id)
    except Exception:pass
  return fetch_all("SELECT * FROM health_alerts WHERE resolved_at IS NULL ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,opened_at")
 def persist(self,results,correlation_id):
  with transaction() as conn:
   with conn.cursor() as cur:
    for x in results:
     cur.execute('SELECT status FROM component_health_state WHERE component=%s FOR UPDATE',(x.component,));old=cur.fetchone();details=json.dumps(x.details,default=str)
     cur.execute("INSERT INTO component_health_state(component,status,message,details_json,checked_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(component) DO UPDATE SET status=EXCLUDED.status,message=EXCLUDED.message,details_json=EXCLUDED.details_json,checked_at=EXCLUDED.checked_at,updated_at=CURRENT_TIMESTAMP",(x.component,x.status.value,x.message,details,x.checked_at))
     if old and old['status']!=x.status.value:cur.execute("INSERT INTO component_health_history(component,old_status,new_status,reason,metadata_json,correlation_id) VALUES(%s,%s,%s,%s,%s,%s)",(x.component,old['status'],x.status.value,x.message,details,correlation_id))
 def errors(self,limit=50):
  return fetch_all("""SELECT component,severity,message,fingerprint,COUNT(*) occurrences,MIN(occurred_at) first_at,MAX(occurred_at) last_at,MAX(correlation_id) correlation_id,MAX(related_id) related_id FROM (SELECT 'MESFLOW' component,CASE WHEN http_status>=500 THEN 'HIGH' ELSE 'MEDIUM' END severity,error_message message,md5(COALESCE(error_type,'')||'|'||path||'|'||COALESCE(error_message,'')) fingerprint,created_at occurred_at,trace_id correlation_id,id::text related_id FROM action_logs WHERE outcome IN ('ERROR','FAILED') AND created_at>CURRENT_TIMESTAMP-(%s||' minutes')::interval UNION ALL SELECT 'KIOSK',CASE severity WHEN 'CRITICAL' THEN 'HIGH' ELSE 'MEDIUM' END,message,md5(event_type||'|'||message),occurred_at,event_uuid,id::text FROM kiosk_events WHERE severity IN ('ERROR','CRITICAL') AND occurred_at>CURRENT_TIMESTAMP-(%s||' minutes')::interval) q GROUP BY component,severity,message,fingerprint ORDER BY last_at DESC LIMIT %s""",(settings.health_error_window_minutes,settings.health_error_window_minutes,limit))
 def history(self,limit=200):
  """Incident History: component-level transitions AND alert open/resolve
  events, merged and sorted newest first. Never raw heartbeats (section 18)."""
  return fetch_all("""
   SELECT 'TRANSITION' kind,component,old_status,new_status,reason title,changed_at at,correlation_id FROM component_health_history
   UNION ALL
   SELECT 'ALERT_OPENED',component,NULL,severity,title,opened_at,correlation_id FROM health_alerts
   UNION ALL
   SELECT 'ALERT_RESOLVED',component,severity,'RESOLVED',title,resolved_at,correlation_id FROM health_alerts WHERE resolved_at IS NOT NULL
   ORDER BY at DESC LIMIT %s""",(limit,))
