"""Phase 3 Predictive / AI: AI incident summary + suggested remediation.

Layering (section 2): everything numeric (forecast, anomaly, recurrence)
is already computed deterministically by forecast_service/anomaly_service/
recurrence_service. This module only asks AI to *explain and correlate*
already-computed evidence -- never to do arithmetic itself.

Safety (section 28/29/33/34/82): AI is fully optional (DISABLED by default,
core Health Center never depends on it); its response is validated against
a fixed structured schema and used only to *render text* -- there is no
code path anywhere in this module (or called by it) that executes a
command, calls Deploy Agent's mutation endpoints, or touches
infrastructure. `suggested_checks[].risk` is clamped to the
SAFE_CHECK/LOW_RISK_ACTION/HIGH_RISK_ACTION enum server-side regardless of
what the model returns, and even a HIGH_RISK_ACTION suggestion is still
just a text label -- never a button wired to execution.
"""
from __future__ import annotations
import hashlib,json,time,urllib.request
from datetime import datetime,timezone
from mesflow.core.config import settings
from mesflow.db.connection import fetch_one,transaction
from mesflow.services.diagnostic_service import sanitize_log_text

ALLOWED_RISK={'SAFE_CHECK','LOW_RISK_ACTION','HIGH_RISK_ACTION'}
REQUIRED_FIELDS=('summary','evidence','likely_causes','uncertainties','suggested_checks')


def now():return datetime.now(timezone.utc)


class AIProvider:
 name='disabled'
 def available(self):return False
 def analyze(self,context_text):raise NotImplementedError


class DisabledAIProvider(AIProvider):
 name='disabled'
 def available(self):return False
 def analyze(self,context_text):raise RuntimeError('AI_DISABLED')


class AnthropicAIProvider(AIProvider):
 """Generic Anthropic Messages API client. No SDK dependency -- a single
 bounded HTTPS POST, matching the same urllib pattern already used
 throughout this codebase's HTTP integrations (Deploy Agent, QA Center)."""
 name='anthropic'
 def __init__(self):self.api_key=settings.ai_api_key;self.model=settings.ai_model
 def available(self):return bool(self.api_key)
 def analyze(self,context_text):
  if not self.available():raise RuntimeError('AI_NOT_CONFIGURED')
  prompt=(
   "You are assisting an operations engineer reading a MESFlow system health incident. "
   "You are given ALREADY-COMPUTED deterministic evidence (metrics, forecasts, diagnostics). "
   "Do not invent numbers. Respond with ONLY a JSON object with exactly these keys: "
   '"summary" (string, 2-4 sentences), "evidence" (array of strings, only facts present in the '
   'input), "likely_causes" (array of strings, clearly hypotheses), "uncertainties" (array of '
   'strings), "suggested_checks" (array of objects with keys action, risk '
   '[SAFE_CHECK|LOW_RISK_ACTION|HIGH_RISK_ACTION], reason). Never suggest running a destructive '
   "or infrastructure-mutating command as if it were safe.\n\nIncident context:\n"+context_text)
  body=json.dumps({'model':self.model,'max_tokens':1024,'messages':[{'role':'user','content':prompt}]}).encode()
  req=urllib.request.Request('https://api.anthropic.com/v1/messages',data=body,headers={
   'Content-Type':'application/json','x-api-key':self.api_key,'anthropic-version':'2023-06-01'})
  with urllib.request.urlopen(req,timeout=settings.ai_timeout_seconds) as r:
   payload=json.loads(r.read())
  text=''.join(b.get('text','') for b in payload.get('content',[]) if b.get('type')=='text')
  return text


def _provider():
 if not settings.ai_enabled:return DisabledAIProvider()
 if settings.ai_provider=='anthropic':return AnthropicAIProvider()
 return DisabledAIProvider()


def _validate_structured(raw_text):
 try:
  data=json.loads(raw_text)
 except Exception:
  # tolerate a fenced ```json ... ``` wrapper
  stripped=raw_text.strip()
  if stripped.startswith('```'):
   stripped=stripped.strip('`');stripped=stripped[4:] if stripped.lower().startswith('json') else stripped
   try:data=json.loads(stripped)
   except Exception:return None,'INVALID_OUTPUT'
  else:return None,'INVALID_OUTPUT'
 if not isinstance(data,dict) or not all(k in data for k in REQUIRED_FIELDS):return None,'INVALID_OUTPUT'
 if not isinstance(data['summary'],str):return None,'INVALID_OUTPUT'
 for key in ('evidence','likely_causes','uncertainties'):
  if not isinstance(data[key],list):return None,'INVALID_OUTPUT'
 checks=data.get('suggested_checks')
 if not isinstance(checks,list):return None,'INVALID_OUTPUT'
 clean_checks=[]
 for c in checks:
  if not isinstance(c,dict) or 'action' not in c:continue
  risk=str(c.get('risk') or 'SAFE_CHECK').upper()
  if risk not in ALLOWED_RISK:risk='SAFE_CHECK'  # never trust an unrecognized/invented risk label
  clean_checks.append({'action':str(c['action'])[:300],'risk':risk,'reason':str(c.get('reason',''))[:500]})
 data['suggested_checks']=clean_checks
 return data,None


def build_context(alert,diagnostics_snapshot,recent_incidents,max_chars=None):
 """Bounded, sanitized context (section 26/27) -- never raw multi-GB logs,
 never secrets."""
 max_chars=max_chars or settings.ai_max_context_chars
 parts=[
  f"Alert: {alert.get('title')} (severity {alert.get('severity')}, component {alert.get('component')})",
  f"Message: {alert.get('message','')}",
  f"Opened at: {alert.get('opened_at')}",
 ]
 if diagnostics_snapshot:
  parts.append("Diagnostics: "+json.dumps(diagnostics_snapshot,default=str)[:3000])
 if recent_incidents:
  parts.append(f"Similar past incidents ({len(recent_incidents)}): "+json.dumps(
   [{'opened_at':str(i.get('opened_at')),'resolved_at':str(i.get('resolved_at'))} for i in recent_incidents[:10]],default=str))
 text=sanitize_log_text('\n'.join(parts))
 return text[:max_chars]


class IncidentAIService:
 def __init__(self,provider=None):self.provider=provider or _provider()

 def context_hash(self,context_text):return hashlib.sha256(context_text.encode()).hexdigest()

 def analyze(self,alert,stage,diagnostics_snapshot=None,recent_incidents=None,requested_by_user_id=None,force=False):
  context_text=build_context(alert,diagnostics_snapshot,recent_incidents)
  chash=self.context_hash(context_text)
  if not force:
   cached=fetch_one("SELECT * FROM ai_incident_analyses WHERE alert_fingerprint=%s AND incident_stage=%s AND context_hash=%s ORDER BY id DESC LIMIT 1",
                     (alert['fingerprint'],stage,chash))
   if cached:return cached

  if not self.provider.available():
   return self._record(alert['fingerprint'],stage,chash,'DISABLED','',{},'',requested_by_user_id)

  t=time.time()
  try:
   raw=self.provider.analyze(context_text)
  except TimeoutError:
   return self._record(alert['fingerprint'],stage,chash,'TIMEOUT','',{},'timeout',requested_by_user_id)
  except Exception as e:
   status='TIMEOUT' if time.time()-t>=settings.ai_timeout_seconds else 'FAILED'
   return self._record(alert['fingerprint'],stage,chash,status,'',{},type(e).__name__,requested_by_user_id)

  data,err=_validate_structured(raw)
  if err:
   return self._record(alert['fingerprint'],stage,chash,'INVALID_OUTPUT','',{},err,requested_by_user_id)
  return self._record(alert['fingerprint'],stage,chash,'SUCCESS',self.provider.model if hasattr(self.provider,'model') else '',data,'',requested_by_user_id)

 def _record(self,fingerprint,stage,context_hash,status,model,result,error,requested_by_user_id):
  if not settings.legacy_health_writer_enabled:
   # Monitoring ownership cutover: no new ai_incident_analyses rows.
   # Cached rows (checked before this is ever called) stay readable.
   return {'alert_fingerprint':fingerprint,'incident_stage':stage,'context_hash':context_hash,
           'provider':self.provider.name,'model':model,'status':'DISABLED','result_json':result,
           'error':error or 'LEGACY_WRITER_DISABLED','requested_by_user_id':requested_by_user_id}
  with transaction() as conn:
   with conn.cursor() as cur:
    cur.execute("""INSERT INTO ai_incident_analyses(alert_fingerprint,incident_stage,context_hash,provider,model,status,result_json,error,requested_by_user_id)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
      (fingerprint,stage,context_hash,self.provider.name,model,status,json.dumps(result,default=str),error,requested_by_user_id))
    return cur.fetchone()
