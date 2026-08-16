"""Phase 3 Predictive / AI: recurring failure detection. Deterministic
fingerprint grouping first (section 15) -- reuses Phase 2's own
health_alerts fingerprints, no semantic AI grouping. Time-pattern and
trend are both plain arithmetic over already-collected incident timestamps."""
from __future__ import annotations
from collections import Counter
from datetime import timedelta
from mesflow.core.config import settings
from mesflow.db.connection import fetch_all
from mesflow.services.metrics_service import now


class RecurrenceService:
 def detect(self,window_days=None):
  window_days=window_days or settings.predictive_recurrence_window_days
  cutoff=now()-timedelta(days=window_days)
  rows=fetch_all("""SELECT fingerprint,component,severity,title,opened_at,resolved_at,
      EXTRACT(EPOCH FROM(COALESCE(resolved_at,CURRENT_TIMESTAMP)-opened_at)) duration_seconds
    FROM health_alerts WHERE opened_at>=%s ORDER BY fingerprint,opened_at""",(cutoff,))
  by_fp={}
  for r in rows:by_fp.setdefault(r['fingerprint'],[]).append(r)
  out=[]
  for fp,incidents in by_fp.items():
   if len(incidents)<settings.predictive_recurrence_min_count:continue
   out.append(self._summarize(fp,incidents,window_days))
  out.sort(key=lambda x:(-{'HIGH':3,'MEDIUM':2,'LOW':1}.get(x['risk'],0),-x['count']))
  return out

 def _summarize(self,fingerprint,incidents,window_days):
  count=len(incidents)
  durations=[i['duration_seconds'] for i in incidents if i['duration_seconds'] is not None]
  avg_duration=sum(durations)/len(durations) if durations else 0
  mid=incidents[len(incidents)//2]['opened_at']
  first_half=sum(1 for i in incidents if i['opened_at']<mid)
  second_half=count-first_half
  trend='increasing' if second_half>first_half*1.3 else ('decreasing' if second_half<first_half*0.7 else 'stable')
  hours=Counter(i['opened_at'].hour for i in incidents)
  dominant=hours.most_common(1)[0] if hours else None
  pattern=None
  if dominant and dominant[1]/count>=0.5:
   h=dominant[0];pattern=f'Most failures occur between {h:02d}:00–{(h+1)%24:02d}:00.'
  risk='HIGH' if count>=10 or (trend=='increasing' and count>=settings.predictive_recurrence_min_count*2) else ('MEDIUM' if count>=5 else 'LOW')
  return {
   'fingerprint':fingerprint,'component':incidents[-1]['component'],'title':incidents[-1]['title'],
   'severity':incidents[-1]['severity'],'count':count,'window_days':window_days,
   'avg_duration_seconds':avg_duration,'trend':trend,'time_pattern':pattern,'risk':risk,
   'first_seen':incidents[0]['opened_at'],'last_seen':incidents[-1]['opened_at'],
  }
