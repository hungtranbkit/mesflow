"""Phase 2 Health Center: notification dispatch.

WEB reuses the existing `mesflow.db.repositories.analytics.notifications`
table and its UNIQUE(source_type,source_id) constraint for dedup -- no new
storage for that channel. EMAIL/TELEGRAM are new, optional (NOT_CONFIGURED
when unset, never DOWN), and every attempt -- including WEB -- is recorded
in `notification_deliveries` for the audit trail (section 34).

Failure policy: a channel that fails to send never raises out of
`dispatch()` -- the original health alert/incident must survive even if
every notification channel is broken (section 32).
"""
from __future__ import annotations
import json,smtplib,time,urllib.request
from datetime import datetime,timezone
from email.mime.text import MIMEText
from mesflow.core.config import settings
from mesflow.db.connection import transaction

SEVERITY_RANK={'CRITICAL':0,'HIGH':1,'MEDIUM':2,'LOW':3}
def _meets_min(severity,min_severity):return SEVERITY_RANK.get(severity,9)<=SEVERITY_RANK.get(min_severity,0)
def now():return datetime.now(timezone.utc)


class WebChannel:
 name='WEB'
 def configured(self):return True
 def send(self,alert,event_type):
  # Recovery gets its own source_id (distinct notification), the original
  # OPENED notification is untouched -- section 11 "a recovery should not
  # erase the original detection".
  source_id=alert['fingerprint'] if event_type in ('OPENED','TEST') else f"{alert['fingerprint']}#resolved"
  title=alert['title'] if event_type=='OPENED' else (f"RECOVERED — {alert['title']}" if event_type=='RESOLVED' else alert['title'])
  with transaction() as conn:
   with conn.cursor() as cur:
    cur.execute("""INSERT INTO notifications(source_type,source_id,severity,title,message,target_role)
      VALUES('HEALTH_ALERT',%s,%s,%s,%s,'admin') ON CONFLICT(source_type,source_id) DO NOTHING RETURNING id""",
      (source_id,alert['severity'],title,alert.get('message','')))
    row=cur.fetchone()
  return ('SENT' if row else 'SKIPPED'),('' if row else 'ALREADY_NOTIFIED')


class EmailChannel:
 name='EMAIL'
 def configured(self):return bool(settings.smtp_host and settings.smtp_from and settings.smtp_to)
 def send(self,alert,event_type):
  subject=(f"[{alert['severity']}] MESFlow — {alert['title']}" if event_type=='OPENED'
           else f"[RECOVERED] MESFlow — {alert['title']}" if event_type=='RESOLVED'
           else "MESFlow notification test")
  body=(alert.get('message') or '')+(f"\n\nHealth Center alert: {alert['fingerprint']}" if alert.get('fingerprint') else '')
  msg=MIMEText(body);msg['Subject']=subject;msg['From']=settings.smtp_from;msg['To']=settings.smtp_to
  try:
   with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=settings.notification_timeout_seconds) as s:
    if settings.smtp_use_tls:s.starttls()
    if settings.smtp_user:s.login(settings.smtp_user,settings.smtp_password)
    s.sendmail(settings.smtp_from,[x.strip() for x in settings.smtp_to.split(',') if x.strip()],msg.as_string())
   return 'SENT',''
  except Exception as e:return 'FAILED',type(e).__name__


class TelegramChannel:
 name='TELEGRAM'
 def configured(self):return bool(settings.telegram_bot_token and settings.telegram_chat_id)
 def send(self,alert,event_type):
  text=(f"[{alert['severity']}] MESFlow — {alert['title']}\n{alert.get('message') or ''}" if event_type=='OPENED'
        else f"[RECOVERED] MESFlow — {alert['title']}" if event_type=='RESOLVED'
        else "MESFlow notification test")
  url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
  req=urllib.request.Request(url,data=json.dumps({'chat_id':settings.telegram_chat_id,'text':text[:4000]}).encode(),
                              headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=settings.notification_timeout_seconds) as r:
    ok=bool(json.loads(r.read()).get('ok'))
   return ('SENT' if ok else 'FAILED'),('' if ok else 'TELEGRAM_NOT_OK')
  except Exception as e:return 'FAILED',type(e).__name__


class NotificationDispatcher:
 def __init__(self):self.channels={'WEB':WebChannel(),'EMAIL':EmailChannel(),'TELEGRAM':TelegramChannel()}

 def _plan(self,severity):
  plan=['WEB']
  if _meets_min(severity,settings.notify_email_min_severity):plan.append('EMAIL')
  if _meets_min(severity,settings.notify_telegram_min_severity):plan.append('TELEGRAM')
  return plan

 def _attempt(self,channel,alert,event_type,max_attempts):
  if not channel.configured():return 'SKIPPED','NOT_CONFIGURED',0
  status,error='FAILED','';attempts=0
  while attempts<max_attempts:
   attempts+=1
   status,error=channel.send(alert,event_type)
   if status in ('SENT','SKIPPED'):break
   if attempts<max_attempts:time.sleep(min(attempts,3))
  return status,error,attempts

 def dispatch(self,alert,event_type,correlation_id=''):
  """alert: a dict-like health_alerts row. event_type: OPENED|RESOLVED.
  Idempotent per (fingerprint,event_type,channel): if a SENT/SKIPPED
  delivery already exists for this exact transition, do not re-notify
  (protects against sync_alerts() being invoked twice for the same
  transition, e.g. a retried request)."""
  if not settings.legacy_health_writer_enabled:return []  # monitoring ownership cutover: no new notification_deliveries rows
  from mesflow.db.connection import fetch_one
  results=[]
  for name in self._plan(alert['severity']):
   existing=fetch_one("SELECT id FROM notification_deliveries WHERE alert_fingerprint=%s AND event_type=%s AND channel=%s AND status IN ('SENT','SKIPPED') LIMIT 1",
                       (alert['fingerprint'],event_type,name))
   if existing:continue
   channel=self.channels[name]
   max_attempts=settings.notification_retry_attempts if name!='WEB' else 1
   status,error,attempts=self._attempt(channel,alert,event_type,max_attempts)
   with transaction() as conn:
    with conn.cursor() as cur:
     cur.execute("""INSERT INTO notification_deliveries(alert_fingerprint,event_type,channel,status,delivered_at,error,correlation_id)
       VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
       (alert['fingerprint'],event_type,name,status,now() if status=='SENT' else None,error,correlation_id))
     results.append(cur.fetchone())
  return results

 def test(self,channel_name):
  """section 44-46: explicit test send, clearly labelled, never a
  fabricated real incident, recorded separately (event_type='TEST')."""
  channel=self.channels.get(channel_name)
  if not channel:return {'ok':False,'error':'UNKNOWN_CHANNEL'}
  if not settings.legacy_health_writer_enabled:return {'ok':False,'status':'DISABLED','error':'LEGACY_WRITER_DISABLED'}
  fake={'fingerprint':f'TEST:{channel_name}:{int(time.time())}','severity':'LOW','title':'MESFlow notification test','message':'Đây là tin nhắn kiểm tra kênh thông báo MESFlow.'}
  status,error,attempts=self._attempt(channel,fake,'TEST',settings.notification_retry_attempts if channel_name!='WEB' else 1)
  with transaction() as conn:
   with conn.cursor() as cur:
    cur.execute("INSERT INTO notification_deliveries(alert_fingerprint,event_type,channel,status,delivered_at,error) VALUES(%s,'TEST',%s,%s,%s,%s)",
      (fake['fingerprint'],channel_name,status,now() if status=='SENT' else None,error))
  return {'ok':status=='SENT','status':status,'error':error}
