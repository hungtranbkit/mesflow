"""Phase 3 Predictive / AI: orchestrates forecast/anomaly/recurrence into
the compact "Predictive Insights" list Health Center shows, with an
ACTIVE/CLEARED lifecycle (section 43) so a resolved risk does not linger
as a stale warning -- same fingerprint-upsert pattern as Phase 2's
health_alerts (mesflow.services.system_health_service.sync_alerts)."""
from __future__ import annotations
import json
from mesflow.core.config import settings
from mesflow.db.connection import fetch_all,transaction
from mesflow.domain.predictive import Confidence,RiskLevel
from mesflow.services.anomaly_service import AnomalyService
from mesflow.services.forecast_service import ForecastService,risk_for_days
from mesflow.services.recurrence_service import RecurrenceService


def _fmt_days(d):
 if d is None:return None
 if d<1:return 'less than 1 day'
 return f'~{round(d)} days' if d>=2 else 'about 1 day'


class PredictiveService:
 def __init__(self):
  self.forecast=ForecastService();self.anomaly=AnomalyService();self.recurrence=RecurrenceService()

 def compute_conditions(self):
  """Returns [(fingerprint, category, risk, title, message, confidence, evidence), ...]
  -- only conditions that clear the bar for a real insight (section 53:
  prefer fewer, useful warnings; INSUFFICIENT_DATA never becomes an
  insight, it is just absent)."""
  out=[]

  disk=self.forecast.disk_forecast()
  if disk.available and disk.growth_per_day and disk.growth_per_day>0:
   days=disk.days_to_critical if disk.days_to_critical is not None else disk.days_to_warning
   risk=risk_for_days(days)
   if risk!=RiskLevel.INFO or (disk.days_to_critical is not None):
    target='90%' if disk.days_to_critical is not None else '80%'
    out.append((f'DISK_FORECAST:{disk.component}','CAPACITY',risk.value,
      f'Disk may reach {target} in {_fmt_days(days)}',
      f'Current {disk.current_value:.0f}%, growing ~{disk.growth_per_day:.2f}%/day.',
      disk.confidence.value,{'current':disk.current_value,'growth_per_day':disk.growth_per_day,
        'days_to_warning':disk.days_to_warning,'days_to_critical':disk.days_to_critical,
        'r_squared':disk.r_squared,'sample_count':disk.sample_count}))

  db=self.forecast.db_growth_forecast()
  if db.available and db.growth_per_day and db.growth_per_day>0:
   gb_day=db.growth_per_day/(1024**3)
   if gb_day>=0.05:  # ignore noise-level growth
    out.append((f'DB_GROWTH:{db.component}','CAPACITY','LOW',
      f'PostgreSQL storage growing ~{gb_day:.2f} GB/day',
      f'Current {db.current_value/(1024**3):.1f} GB.',
      db.confidence.value,{'growth_per_day_bytes':db.growth_per_day,'current_bytes':db.current_value,
        'r_squared':db.r_squared,'sample_count':db.sample_count}))

  db_anomaly=self.anomaly.db_growth_anomaly()
  if db_anomaly.detected:
   out.append(('DB_GROWTH_ANOMALY:primary','ANOMALY',
     'HIGH' if (db_anomaly.deviation or 0)>=5 else 'MEDIUM',
     'Unusual PostgreSQL growth detected',
     f'Recent growth {db_anomaly.actual/(1024**2):.0f} MB vs expected up to {db_anomaly.expected_high/(1024**2):.0f} MB.',
     db_anomaly.confidence.value,{'actual':db_anomaly.actual,'expected_high':db_anomaly.expected_high,'deviation':db_anomaly.deviation}))

  for metric,label in (('CPU_PERCENT','Host CPU'),('DB_LATENCY_MS','PostgreSQL latency')):
   a=self.anomaly.detect_point(metric)
   if a.detected:
    out.append((f'ANOMALY:{metric}','ANOMALY','MEDIUM',f'{label} anomaly detected',
      f'Current {a.actual:.1f}, expected {a.expected_low:.1f}–{a.expected_high:.1f}.',
      a.confidence.value,{'actual':a.actual,'expected_low':a.expected_low,'expected_high':a.expected_high,'deviation':a.deviation}))

  for rec in self.recurrence.detect():
   title=f"Recurring: {rec['title']}"
   msg=f"{rec['count']} incidents / {rec['window_days']} days"+(f" — {rec['time_pattern']}" if rec['time_pattern'] else '')
   out.append((f"RECURRING:{rec['fingerprint']}",'RECURRENCE',rec['risk'],title,msg,
     'HIGH' if rec['count']>=10 else 'MEDIUM',rec))

  return out

 def sync(self,correlation_id=''):
  conditions=self.compute_conditions()
  fingerprints=[c[0] for c in conditions]
  with transaction() as conn:
   with conn.cursor() as cur:
    for fp,category,risk,title,message,confidence,evidence in conditions:
     cur.execute("""INSERT INTO predictive_insights(fingerprint,category,risk,title,message,confidence,evidence_json,correlation_id)
       VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
       ON CONFLICT(fingerprint) WHERE status='ACTIVE' DO UPDATE SET
         risk=EXCLUDED.risk,title=EXCLUDED.title,message=EXCLUDED.message,confidence=EXCLUDED.confidence,
         evidence_json=EXCLUDED.evidence_json,last_seen_at=CURRENT_TIMESTAMP""",
       (fp,category,risk,title,message,confidence,json.dumps(evidence,default=str),correlation_id))
    if fingerprints:
     cur.execute("UPDATE predictive_insights SET status='CLEARED',cleared_at=CURRENT_TIMESTAMP WHERE status='ACTIVE' AND NOT(fingerprint=ANY(%s))",(fingerprints,))
    else:
     cur.execute("UPDATE predictive_insights SET status='CLEARED',cleared_at=CURRENT_TIMESTAMP WHERE status='ACTIVE'")
  return self.active()

 def active(self,limit=20):
  return fetch_all("""SELECT * FROM predictive_insights WHERE status='ACTIVE'
    ORDER BY CASE risk WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END,opened_at LIMIT %s""",(limit,))
