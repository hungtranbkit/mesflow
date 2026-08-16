"""Phase 3 Predictive / AI: deterministic capacity forecasting (section 2 --
"disk growth mathematics" must be code, not an LLM). Linear trend over
recent samples, explicit confidence, explicit INSUFFICIENT_DATA when the
history is too short/noisy to say anything useful (section 7/54)."""
from __future__ import annotations
from datetime import datetime,timezone
from mesflow.core.config import settings
from mesflow.domain.predictive import Confidence,ForecastResult,RiskLevel,linear_regression,mean,stdev
from mesflow.services.metrics_service import samples_for


def _to_points(rows):
 if not rows:return []
 t0=rows[0]['sampled_at']
 return [((r['sampled_at']-t0).total_seconds()/86400.0,r['value']) for r in rows]


def risk_for_days(days_to_critical):
 """section 71: configurable day-band -> risk level. None (never reaches
 critical at current trend, or trend is flat/negative) -> INFO."""
 if days_to_critical is None or days_to_critical<0:return RiskLevel.INFO
 if days_to_critical<settings.predictive_risk_high_days:return RiskLevel.HIGH
 if days_to_critical<settings.predictive_risk_medium_days:return RiskLevel.MEDIUM
 if days_to_critical<settings.predictive_risk_low_days:return RiskLevel.LOW
 return RiskLevel.INFO


class ForecastService:
 def _linear_forecast(self,metric,component,window_days=None):
  rows=samples_for(metric,component,window_days or settings.predictive_forecast_window_days)
  n=len(rows)
  if n<settings.predictive_forecast_min_samples:
   return None,n,0.0,'Not enough samples yet (%d, need %d).'%(n,settings.predictive_forecast_min_samples)
  span_hours=(rows[-1]['sampled_at']-rows[0]['sampled_at']).total_seconds()/3600.0
  if span_hours<settings.predictive_forecast_min_span_hours:
   return None,n,span_hours,'Observation window too short (%.1fh, need %.1fh).'%(span_hours,settings.predictive_forecast_min_span_hours)
  points=_to_points(rows)
  slope,intercept,r2=linear_regression(points)
  return (slope,intercept,r2),n,span_hours,''

 def _confidence(self,n,r2):
  if r2>=0.7 and n>=20:return Confidence.HIGH
  if r2>=0.4:return Confidence.MEDIUM
  return Confidence.LOW

 def disk_forecast(self,component=None):
  component=component or settings.predictive_disk_component
  fit,n,span_hours,reason=self._linear_forecast('DISK_USAGE_PERCENT',component)
  if fit is None:
   return ForecastResult('DISK_USAGE_PERCENT',component,False,Confidence.INSUFFICIENT_DATA,sample_count=n,span_hours=span_hours,reason=reason)
  slope,intercept,r2=fit  # slope = %/day
  rows=samples_for('DISK_USAGE_PERCENT',component,settings.predictive_forecast_window_days)
  current=rows[-1]['value']
  days_to_warn=days_to_crit=None
  if slope>0.0001:
   warn_pct=settings.health_disk_warning_percent;crit_pct=settings.health_disk_critical_percent
   if current<warn_pct:days_to_warn=(warn_pct-current)/slope
   if current<crit_pct:days_to_crit=(crit_pct-current)/slope
  return ForecastResult('DISK_USAGE_PERCENT',component,True,self._confidence(n,r2),
    current_value=current,growth_per_day=slope,days_to_warning=days_to_warn,days_to_critical=days_to_crit,
    r_squared=r2,sample_count=n,span_hours=span_hours)

 def db_growth_forecast(self,component='primary'):
  fit,n,span_hours,reason=self._linear_forecast('DB_SIZE_BYTES',component)
  if fit is None:
   return ForecastResult('DB_SIZE_BYTES',component,False,Confidence.INSUFFICIENT_DATA,sample_count=n,span_hours=span_hours,reason=reason)
  slope,intercept,r2=fit  # bytes/day
  rows=samples_for('DB_SIZE_BYTES',component,settings.predictive_forecast_window_days)
  current=rows[-1]['value']
  return ForecastResult('DB_SIZE_BYTES',component,True,self._confidence(n,r2),
    current_value=current,growth_per_day=slope,r_squared=r2,sample_count=n,span_hours=span_hours)

 def db_top_tables(self,component='primary'):
  """Most recent top-tables snapshot (cheap, collected periodically --
  section 11/41, never a live scan on drawer open)."""
  rows=samples_for('DB_TOP_TABLES',component,settings.predictive_forecast_window_days)
  return (rows[-1]['metadata_json'] or {}).get('tables',[]) if rows else []
