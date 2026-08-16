"""Phase 2 Health Center: read-only diagnostics + bounded, allowlisted log
access. Every provider here only reads -- no diagnostic path may mutate
infrastructure (section 13/16/48). SUMMARY is cheap enough to run
automatically when an alert opens; DETAIL is admin-requested only
(section 14/37).
"""
from __future__ import annotations
import json,time,urllib.request
from datetime import datetime,timezone
from mesflow import __version__
from mesflow.core.config import settings
from mesflow.db.connection import fetch_all,fetch_one,transaction

# Server-defined allowlist only -- the browser can never supply an arbitrary
# path/command (section 21/48). Mirrors the exact source names Deploy
# Agent's own /api/ops/logs already allowlists.
LOG_SOURCES={'mesflow':'MESFlow application (Docker)','postgres':'PostgreSQL (Docker)','qa':'QA Center (systemd)','agent':'Deploy Agent (systemd)'}
_SECRET_PATTERNS=('password','token','authorization','cookie','secret','api_key','apikey')


def sanitize_log_text(text):
 """Best-effort line-level redaction for anything that looks like a
 header/field carrying a secret (section 20). Bounded log viewer, not a
 log analytics tool -- a simple substring/regex approach is sufficient
 here; it never claims to catch every possible leak."""
 import re
 out=[]
 for line in (text or '').splitlines():
  low=line.lower()
  if any(p in low for p in _SECRET_PATTERNS):
   # Redact the rest of the line after the key, not just the first
   # whitespace-delimited token -- "Authorization: Bearer abc123" has two.
   line=re.sub(r'(?i)(password|token|authorization|cookie|secret|api[_-]?key)\s*[:=]\s*.*$',r'\1=***',line)
  out.append(line)
 return '\n'.join(out)


def _agent_get(path,timeout=None):
 if not settings.health_deploy_agent_url:return None,'NOT_CONFIGURED'
 headers={'X-MESFlow-Internal-Token':settings.internal_api_token} if settings.internal_api_token else {}
 req=urllib.request.Request(settings.health_deploy_agent_url+path,headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=timeout or settings.health_external_timeout_seconds) as r:
   return json.loads(r.read(500000)),None
 except Exception as e:return None,type(e).__name__


class DiagnosticService:
 def snapshot(self,component,level='SUMMARY',alert_fingerprint='',correlation_id='',requested_by_user_id=None):
  data=self._collect(component,level)
  if not settings.legacy_health_writer_enabled:
   # Monitoring ownership cutover: read-only elsewhere, no new legacy row.
   # Diagnostics run live (Deploy Agent's own Chẩn đoán tab), just not
   # persisted into this retired table.
   return {'component':component,'alert_fingerprint':alert_fingerprint,'level':level,'data_json':data,
           'correlation_id':correlation_id,'note':'LEGACY_WRITER_DISABLED_NOT_PERSISTED'}
  with transaction() as conn:
   with conn.cursor() as cur:
    cur.execute("""INSERT INTO health_diagnostics_snapshots(component,alert_fingerprint,level,requested_by_user_id,data_json,correlation_id)
      VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",
      (component,alert_fingerprint,level,requested_by_user_id,json.dumps(data,default=str),correlation_id))
    return cur.fetchone()

 def _collect(self,component,level):
  try:
   if component=='MESFLOW':return self._mesflow(level)
   if component=='POSTGRESQL':return self._postgresql(level)
   if component in ('SERVER','DOCKER','DEPLOY_AGENT'):return self._infra(level)
   if component=='QA_CENTER':return self._qa(level)
   if component=='KIOSK_FLEET':return self._kiosk_fleet(level)
   return {'error':'UNKNOWN_COMPONENT'}
  except Exception as e:
   # A broken diagnostic provider must not raise into the caller -- it is
   # explicitly a "partial data" result, not a 500 (section 22/58).
   return {'error':type(e).__name__,'partial':True}

 def _mesflow(self,level):
  recent=fetch_all("SELECT method,path,http_status,error_type,error_message,created_at FROM action_logs WHERE outcome IN ('ERROR','FAILED') ORDER BY id DESC LIMIT %s",(5 if level=='SUMMARY' else 30,))
  return {'version':__version__,'recent_errors':recent}

 def _postgresql(self,level):
  t=time.perf_counter()
  try:
   row=fetch_one("SELECT (SELECT COUNT(*) FROM pg_stat_activity) connections,(SELECT version_num FROM alembic_version) migration_revision")
   out={'connection':'OK','latency_ms':int((time.perf_counter()-t)*1000),**row}
   if level=='DETAIL':
    out['recent_locks']=fetch_all("SELECT pid,mode,granted FROM pg_locks WHERE NOT granted LIMIT 20")
  except Exception as e:out={'connection':'FAILED','error':type(e).__name__}
  return out

 def _infra(self,level):
  health,herr=_agent_get('/health')
  if herr:return {'agent_reachable':False,'error':herr,'note':'Unavailable because Deploy Agent is offline.'}
  ops,operr=_agent_get('/api/ops/summary')
  out={'agent_reachable':True,'health':health,'ops':ops,'ops_error':operr}
  if level=='DETAIL' and settings.health_deploy_agent_url:
   docker,derr=_agent_get('/api/ops/docker')
   out['docker_containers']=(docker or {}).get('items');out['docker_error']=derr
  return out

 def _qa(self,level):
  if not settings.health_qa_url:return {'state':'NOT_CONFIGURED'}
  data,err=_agent_get_url(settings.health_qa_url+'/api/status')
  if err:return {'reachable':False,'error':err}
  return {'reachable':True,'version':data.get('version'),'latest':data.get('latest') or data.get('last_run')}

 def _kiosk_fleet(self,level):
  rows=fetch_all("SELECT device_uuid,event_type,severity,message,occurred_at FROM kiosk_events WHERE severity IN ('ERROR','CRITICAL') ORDER BY id DESC LIMIT %s",(10 if level=='SUMMARY' else 50,))
  return {'recent_events':rows}


def _agent_get_url(url,timeout=None):
 try:
  with urllib.request.urlopen(url,timeout=timeout or settings.health_external_timeout_seconds) as r:
   return json.loads(r.read(256000)),None
 except Exception as e:return None,type(e).__name__


class LogService:
 """Bounded, allowlisted proxy to Deploy Agent's own already-allowlisted
 /api/ops/logs -- MESFlow re-validates the source name itself too (defense
 in depth: a broken/compromised frontend still cannot smuggle an arbitrary
 source through to the Agent)."""
 def fetch(self,source,lines=200):
  if source not in LOG_SOURCES:return {'ok':False,'error':'UNKNOWN_SOURCE'}
  lines=max(20,min(1000,int(lines or 200)))
  data,err=_agent_get(f'/api/ops/logs?source={source}&lines={lines}',timeout=8)
  if err:return {'ok':False,'error':err}
  text=sanitize_log_text((data or {}).get('stdout') or '')
  return {'ok':bool((data or {}).get('ok')),'source':source,'label':LOG_SOURCES[source],'lines':lines,'text':text[-200000:]}
