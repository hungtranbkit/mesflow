"""Phase 3 Predictive / AI: explainable statistical anomaly detection
(section 20 -- rolling mean/stdev/MAD, no black-box ML). Applied only to
signals where anomalies are operationally useful (section 19): CPU, DB
latency, and DB growth rate. Every result carries the actual value, the
expected range, and the deviation -- never a bare "AI thinks this looks
strange" (section 22)."""
from __future__ import annotations
from datetime import timedelta
from mesflow.core.config import settings
from mesflow.domain.predictive import AnomalyResult,Confidence,mad,mean,stdev
from mesflow.services.metrics_service import now,samples_for


class AnomalyService:
 def detect_point(self,metric,component=''):
  """Compare the latest sample against a robust baseline built from the
  rest of the window (section 20/22)."""
  rows=samples_for(metric,component,settings.predictive_forecast_window_days)
  if len(rows)<settings.predictive_anomaly_min_samples:
   return AnomalyResult(metric,component,False,sample_count=len(rows),
     reason='Not enough samples yet (%d, need %d).'%(len(rows),settings.predictive_anomaly_min_samples))
  *baseline_rows,latest=rows
  values=[r['value'] for r in baseline_rows]
  m=mean(values);sd=stdev(values);robust=mad(values)
  spread=robust if robust>0 else sd
  actual=latest['value']
  if spread==0:
   detected=abs(actual-m)>1e-9
   deviation=0.0 if not detected else float('inf')
  else:
   deviation=(actual-m)/spread
   detected=abs(deviation)>=settings.predictive_anomaly_zscore_threshold
  confidence=Confidence.HIGH if len(values)>=40 else Confidence.MEDIUM if len(values)>=20 else Confidence.LOW
  return AnomalyResult(metric,component,detected,actual=actual,
    expected_low=m-settings.predictive_anomaly_zscore_threshold*spread,
    expected_high=m+settings.predictive_anomaly_zscore_threshold*spread,
    deviation=deviation,confidence=confidence,sample_count=len(rows))

 def db_growth_anomaly(self,component='primary',recent_hours=2):
  """section 12: compare recent short-window growth against the typical
  daily rate scaled to the same window -- catches a sudden burst that a
  point-in-time z-score on DB_SIZE_BYTES itself would smear out."""
  rows=samples_for('DB_SIZE_BYTES',component,settings.predictive_forecast_window_days)
  if len(rows)<settings.predictive_forecast_min_samples:
   return AnomalyResult('DB_GROWTH_RATE',component,False,sample_count=len(rows),reason='Not enough DB size samples yet.')
  cutoff=now()-timedelta(hours=recent_hours)
  recent=[r for r in rows if r['sampled_at']>=cutoff]
  if len(recent)<2:
   return AnomalyResult('DB_GROWTH_RATE',component,False,sample_count=len(rows),reason='No samples in the recent window yet.')
  recent_growth=recent[-1]['value']-recent[0]['value']
  span_days=(rows[-1]['sampled_at']-rows[0]['sampled_at']).total_seconds()/86400.0
  if span_days<=0:
   return AnomalyResult('DB_GROWTH_RATE',component,False,sample_count=len(rows),reason='Insufficient time span for a baseline.')
  daily_rate=(rows[-1]['value']-rows[0]['value'])/span_days
  expected_recent=daily_rate*(recent_hours/24.0)
  # A one-time expected event (e.g. a known migration/import) is not
  # something this service can identify on its own (section 12) -- it is
  # surfaced as an anomaly for a human/AI to classify, not suppressed.
  threshold=max(abs(expected_recent)*3,50*1024*1024)  # at least 50MB slack
  detected=recent_growth>expected_recent+threshold
  deviation=(recent_growth/expected_recent) if expected_recent>0 else (float('inf') if recent_growth>0 else 0.0)
  return AnomalyResult('DB_GROWTH_RATE',component,detected,actual=recent_growth,
    expected_low=0,expected_high=expected_recent+threshold,deviation=deviation,
    confidence=Confidence.MEDIUM if span_days>=7 else Confidence.LOW,sample_count=len(rows))
