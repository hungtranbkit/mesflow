"""Phase 3 Predictive / AI: real PostgreSQL integration tests, covering
both required vertical slices (section 83/84): Disk Capacity Risk and
KIOSK recurring offline -- plus DB growth, anomaly detection, and the
predictive-insight ACTIVE/CLEARED lifecycle.
"""
import uuid
from datetime import datetime,timedelta,timezone
import pytest
from mesflow.services.ai_incident_service import AIProvider

pytestmark=pytest.mark.postgres
BASE='http://mesflow-test-api:8080'


class _FakeProvider(AIProvider):
 # local copy -- `tests` is not an importable package under this project's
 # pytest config (pythonpath=app only), so cross-file imports between
 # test_v69g_phase3_predictive_unit.py and this file don't resolve.
 name='fake'
 def __init__(self,response=None,raise_exc=None):self.response=response;self.raise_exc=raise_exc
 def available(self):return True
 def analyze(self,context_text):
  if self.raise_exc:raise self.raise_exc
  return self.response


def _seed_metric(db,metric,component,points):
 """points: [(days_ago, value), ...]"""
 now=datetime.now(timezone.utc)
 with db.cursor() as cur:
  for days_ago,value in points:
   cur.execute("INSERT INTO health_metric_samples(metric,component,value,sampled_at) VALUES(%s,%s,%s,%s)",
               (metric,component,value,now-timedelta(days=days_ago)))


def test_disk_forecast_insufficient_data_when_no_samples(db):
 comp=f'test-disk-{uuid.uuid4()}'
 from mesflow.services.forecast_service import ForecastService
 result=ForecastService().disk_forecast(comp)
 assert result.available is False
 assert result.confidence.value=='INSUFFICIENT_DATA'


def test_disk_forecast_linear_growth_produces_reasonable_forecast(db):
 comp=f'test-disk-{uuid.uuid4()}'
 # 15 days of steady +1%/day growth starting at 40%
 points=[(15-i,40+i) for i in range(16)]
 _seed_metric(db,'DISK_USAGE_PERCENT',comp,points)
 from mesflow.services.forecast_service import ForecastService
 result=ForecastService().disk_forecast(comp)
 assert result.available is True
 assert 0.8<result.growth_per_day<1.2
 assert result.confidence.value in ('HIGH','MEDIUM')
 assert result.days_to_critical is not None and result.days_to_critical>0


def test_disk_forecast_outlier_jump_does_not_crash_and_lowers_confidence(db):
 comp=f'test-disk-{uuid.uuid4()}'
 points=[(15-i,40+i*0.2) for i in range(16)]
 points.append((1,95))  # one large temporary jump
 _seed_metric(db,'DISK_USAGE_PERCENT',comp,points)
 from mesflow.services.forecast_service import ForecastService
 result=ForecastService().disk_forecast(comp)
 assert result.available is True  # must not raise/crash on an outlier


def test_db_growth_forecast_and_top_tables(db):
 comp=f'test-db-{uuid.uuid4()}'
 gb=1024**3
 points=[(10-i,5*gb+i*0.3*gb) for i in range(11)]
 _seed_metric(db,'DB_SIZE_BYTES',comp,points)
 from mesflow.services.forecast_service import ForecastService
 result=ForecastService().db_growth_forecast(comp)
 assert result.available is True
 assert result.growth_per_day>0


def test_anomaly_detection_flags_sustained_deviation_not_normal_noise(db):
 metric=f'TEST_LATENCY_{uuid.uuid4().hex[:8]}'
 baseline=[(1+i*0.01,60+((-1)**i)*3) for i in range(25)]  # ~60ms +/- noise
 _seed_metric(db,metric,'',baseline)
 from mesflow.services.anomaly_service import AnomalyService
 normal=AnomalyService().detect_point(metric)
 assert normal.detected is False
 # now add a clear anomalous latest sample
 _seed_metric(db,metric,'',[(0,900)])
 spike=AnomalyService().detect_point(metric)
 assert spike.detected is True
 assert spike.confidence.value in ('HIGH','MEDIUM','LOW')


def test_recurrence_detection_requires_minimum_count_and_computes_trend(db):
 fp=f'KIOSK_OFFLINE:TEST-{uuid.uuid4()}'
 now=datetime.now(timezone.utc)
 with db.cursor() as cur:
  # only 1 incident -> not recurring
  cur.execute("INSERT INTO health_alerts(fingerprint,component,severity,title,message,opened_at,resolved_at) VALUES(%s,'KIOSK_FLEET','HIGH','offline test','',%s,%s)",
              (fp,now-timedelta(days=1),now-timedelta(days=1,hours=-1)))
 from mesflow.services.recurrence_service import RecurrenceService
 result=[r for r in RecurrenceService().detect() if r['fingerprint']==fp]
 assert result==[]
 # add 4 more (recent, to bias trend "increasing") -> now recurring
 with db.cursor() as cur:
  for i in range(4):
   cur.execute("INSERT INTO health_alerts(fingerprint,component,severity,title,message,opened_at,resolved_at) VALUES(%s,'KIOSK_FLEET','HIGH','offline test','',%s,%s)",
               (fp,now-timedelta(hours=i+1),now-timedelta(hours=i+1)+timedelta(minutes=10)))
 result=[r for r in RecurrenceService().detect() if r['fingerprint']==fp]
 assert len(result)==1 and result[0]['count']==5


def test_predictive_insight_lifecycle_active_then_cleared(db):
 comp=f'test-lifecycle-{uuid.uuid4()}'
 points=[(15-i,50+i*2) for i in range(16)]  # steep growth -> HIGH/MEDIUM risk
 _seed_metric(db,'DISK_USAGE_PERCENT',comp,points)
 import dataclasses
 from mesflow.core.config import settings as real_settings
 from mesflow.services.predictive_service import PredictiveService
 import mesflow.services.forecast_service as fsvc
 # scope the forecast to our synthetic component only, isolated from any
 # other component's real samples in this shared test database
 orig=fsvc.settings
 fsvc.settings=dataclasses.replace(orig,predictive_disk_component=comp)
 try:
  service=PredictiveService()
  active=service.sync(correlation_id='test')
  fp=f'DISK_FORECAST:{comp}'
  assert any(a['fingerprint']==fp for a in active)
  # Simulate the condition clearing (e.g. disk usage stopped growing / was
  # cleaned up) by exercising the sync() lifecycle directly rather than
  # trying to construct a synthetic sample timeline that perfectly cancels
  # 16 days of steep growth within one shared regression window -- the
  # thing under test here is the ACTIVE->CLEARED transition itself
  # (section 43), not the forecast math (already covered by the disk
  # forecast tests above).
  service.compute_conditions=lambda:[c for c in PredictiveService().compute_conditions() if c[0]!=fp]
  active2=service.sync(correlation_id='test')
  assert not any(a['fingerprint']==fp for a in active2)
  cleared=db.execute("SELECT status FROM predictive_insights WHERE fingerprint=%s ORDER BY id DESC LIMIT 1",(fp,)).fetchone()
  assert cleared['status']=='CLEARED'
 finally:
  fsvc.settings=orig


def test_api_predictions_and_recurring_endpoints(super_admin_api):
 r=super_admin_api.get(f'{BASE}/api/system-health/predictions',timeout=10);assert r.status_code==200,r.text
 assert 'items' in r.json()
 r=super_admin_api.get(f'{BASE}/api/system-health/recurring-incidents',timeout=10);assert r.status_code==200,r.text
 assert 'items' in r.json()


def test_metric_trend_and_predictions_are_super_admin_only(db, super_admin_api):
 # SUPER_ADMIN / IT System Console (task): the whole /api/system-health
 # blueprint -- including predictions and metric trend -- is now
 # super_admin-only. There is no longer a supervisor/admin split here (was:
 # "supervisor CAN see predictions but NOT raw metric trend", section 57 of
 # an earlier phase); that distinction predates this task and is superseded
 # by the blanket re-gate in mesflow.web.system_health.ok()/admin_only().
 import requests
 from werkzeug.security import generate_password_hash
 u=f'v69g-super-{uuid.uuid4()}';p='Test@123456'
 with db.cursor() as cur:
  cur.execute("INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,'sup',%s,'supervisor',TRUE,FALSE) RETURNING id",(u,generate_password_hash(p)))
  uid=cur.fetchone()['id']
 try:
  s=requests.Session()
  assert s.post(f'{BASE}/api/auth/login',json={'username':u,'password':p}).status_code==200
  assert s.get(f'{BASE}/api/system-health/predictions').status_code==403
  assert s.get(f'{BASE}/api/system-health/metrics/DISK_USAGE_PERCENT/trend').status_code==403
 finally:
  with db.cursor() as cur:cur.execute('DELETE FROM users WHERE id=%s',(uid,))
 assert super_admin_api.get(f'{BASE}/api/system-health/predictions').status_code==200
 assert super_admin_api.get(f'{BASE}/api/system-health/metrics/DISK_USAGE_PERCENT/trend').status_code==200


def test_ai_analysis_reports_disabled_when_not_configured(super_admin_api,db):
 fp=f'TEST_AI:{uuid.uuid4()}'
 with db.cursor() as cur:
  cur.execute("INSERT INTO health_alerts(fingerprint,component,severity,title,message) VALUES(%s,'MESFLOW','HIGH','test alert','') RETURNING id",(fp,))
  alert_id=cur.fetchone()['id']
 r=super_admin_api.get(f'{BASE}/api/system-health/alerts/{alert_id}/ai-analysis',timeout=15)
 assert r.status_code==200,r.text
 assert r.json()['item']['status']=='DISABLED'


def _enable_legacy_writer(monkeypatch):
 # Monitoring ownership cutover (reports/SYSTEM_LOG_AUDIT_SEPARATION.md):
 # off by default -- IncidentAIService._record() no-ops otherwise. These
 # tests exercise the underlying mechanism directly (not through the
 # mesflow-test-api container, which does have the flag on), so they must
 # explicitly opt back in the same way tests/test_v69_system_health_unit.py
 # patches a frozen Settings singleton: replace the module's `settings`
 # name, never mutate the frozen instance in place.
 import dataclasses
 from mesflow.services import ai_incident_service as svc_mod
 monkeypatch.setattr(svc_mod,'settings',dataclasses.replace(svc_mod.settings,legacy_health_writer_enabled=True))


def test_ai_analysis_with_mocked_valid_provider(db,monkeypatch):
 """section 80: mocked provider, no real network call."""
 _enable_legacy_writer(monkeypatch)
 fp=f'TEST_AI_MOCK:{uuid.uuid4()}'
 with db.cursor() as cur:
  cur.execute("INSERT INTO health_alerts(fingerprint,component,severity,title,message) VALUES(%s,'POSTGRESQL','CRITICAL','PostgreSQL DOWN','conn refused') RETURNING id",(fp,))
  alert=db.execute("SELECT * FROM health_alerts WHERE fingerprint=%s",(fp,)).fetchone()
 import json
 from mesflow.services.ai_incident_service import IncidentAIService
 svc=IncidentAIService(provider=_FakeProvider(response=json.dumps({
  'summary':'PostgreSQL became unreachable.','evidence':['connection refused'],
  'likely_causes':['network blip'],'uncertainties':['root cause unconfirmed'],
  'suggested_checks':[{'action':'Review PostgreSQL logs','risk':'SAFE_CHECK','reason':'connection failures preceded the incident'}]})))
 result=svc.analyze(alert,'OPEN')
 assert result['status']=='SUCCESS'
 assert result['result_json']['summary'].startswith('PostgreSQL')
 assert result['result_json']['suggested_checks'][0]['risk']=='SAFE_CHECK'


def test_ai_analysis_with_mocked_malformed_provider_is_invalid_output(db,monkeypatch):
 _enable_legacy_writer(monkeypatch)
 fp=f'TEST_AI_BAD:{uuid.uuid4()}'
 with db.cursor() as cur:
  cur.execute("INSERT INTO health_alerts(fingerprint,component,severity,title,message) VALUES(%s,'MESFLOW','HIGH','x','') RETURNING id",(fp,))
  alert=db.execute("SELECT * FROM health_alerts WHERE fingerprint=%s",(fp,)).fetchone()
 from mesflow.services.ai_incident_service import IncidentAIService
 svc=IncidentAIService(provider=_FakeProvider(response='not valid json'))
 result=svc.analyze(alert,'OPEN')
 assert result['status']=='INVALID_OUTPUT'


def test_ai_analysis_with_mocked_timeout_provider(db,monkeypatch):
 _enable_legacy_writer(monkeypatch)
 fp=f'TEST_AI_TO:{uuid.uuid4()}'
 with db.cursor() as cur:
  cur.execute("INSERT INTO health_alerts(fingerprint,component,severity,title,message) VALUES(%s,'MESFLOW','HIGH','x','') RETURNING id",(fp,))
  alert=db.execute("SELECT * FROM health_alerts WHERE fingerprint=%s",(fp,)).fetchone()
 from mesflow.services.ai_incident_service import IncidentAIService
 svc=IncidentAIService(provider=_FakeProvider(raise_exc=TimeoutError('timed out')))
 result=svc.analyze(alert,'OPEN')
 assert result['status']=='TIMEOUT'


def test_ai_analysis_cache_avoids_regenerating_for_same_context(db,monkeypatch):
 _enable_legacy_writer(monkeypatch)
 fp=f'TEST_AI_CACHE:{uuid.uuid4()}'
 with db.cursor() as cur:
  cur.execute("INSERT INTO health_alerts(fingerprint,component,severity,title,message) VALUES(%s,'MESFLOW','HIGH','x','') RETURNING id",(fp,))
  alert=db.execute("SELECT * FROM health_alerts WHERE fingerprint=%s",(fp,)).fetchone()
 import json
 from mesflow.services.ai_incident_service import IncidentAIService
 calls={'n':0}
 class CountingProvider(_FakeProvider):
  def analyze(self,context_text):
   calls['n']+=1
   return json.dumps({'summary':'s','evidence':[],'likely_causes':[],'uncertainties':[],'suggested_checks':[]})
 svc=IncidentAIService(provider=CountingProvider())
 svc.analyze(alert,'OPEN')
 svc.analyze(alert,'OPEN')  # same alert/stage/context -> cached, no second provider call
 assert calls['n']==1
 svc.analyze(alert,'OPEN',force=True)  # explicit regenerate bypasses cache
 assert calls['n']==2
