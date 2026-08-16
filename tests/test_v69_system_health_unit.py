from datetime import datetime,timezone
from pathlib import Path
from mesflow.domain.health import HealthCheckResult,HealthStatus,overall
ROOT=Path(__file__).parents[1]
def r(name,status,critical=False,configured=True):return HealthCheckResult(name,status,datetime.now(timezone.utc),critical=critical,configured=configured)
def test_overall_policy():
 assert overall([r('MES',HealthStatus.DOWN,True),r('QA',HealthStatus.HEALTHY)])==HealthStatus.DOWN
 assert overall([r('MES',HealthStatus.HEALTHY,True),r('QA',HealthStatus.DOWN)])==HealthStatus.DEGRADED
 assert overall([r('MES',HealthStatus.HEALTHY,True),r('AGENT',HealthStatus.UNKNOWN,configured=False)])==HealthStatus.HEALTHY
def test_thresholds_are_centralized():
 s=(ROOT/'app/mesflow/core/config.py').read_text()
 for x in ('health_kiosk_degraded_seconds','health_kiosk_offline_seconds','health_db_latency_warning_ms','health_qa_stale_hours',
           'health_cpu_warning_percent','health_ram_warning_percent','health_disk_warning_percent','health_disk_critical_percent',
           'health_deploy_agent_url','health_deploy_agent_stale_seconds'):
  assert x in s
def test_migration_transition_not_heartbeat_history():
 s=(ROOT/'app/migrations/versions/0033_v69_system_health.py').read_text();assert "down_revision='0032_v68_production_trace'" in s
 assert 'component_health_history' in s and 'scheduled_job_health' in s and 'idx_health_history_component_time' in s
def test_health_alerts_migration_additive_and_chained():
 s=(ROOT/'app/migrations/versions/0034_v69b_health_alerts.py').read_text()
 assert "down_revision='0033_v69_system_health'" in s
 assert 'health_alerts' in s and 'uq_health_alerts_open_fingerprint' in s and 'resolved_at' in s

# --- Server/Docker/DeployAgent providers (Phase 1 Health Center additions) ---

class FakeFetch:
 def __init__(self,health=None,ops=None,health_error=None,ops_error=None):
  self.health=health;self.ops=ops;self.health_error=health_error;self.ops_error=ops_error;self.health_latency_ms=5

def _providers():
 import importlib,os
 os.environ.setdefault('MESFLOW_SECRET_KEY','test')
 return importlib.import_module('mesflow.services.system_health_service')

def _patch_settings(monkeypatch,module,**overrides):
 # `settings` is a frozen dataclass singleton (mesflow.core.config.Settings)
 # -- monkeypatch.setattr(settings, field, value) raises FrozenInstanceError.
 # Replace the module's `settings` *name* with a modified copy instead.
 import dataclasses
 monkeypatch.setattr(module,'settings',dataclasses.replace(module.settings,**overrides))

def test_deploy_agent_provider_not_configured(monkeypatch):
 svc=_providers()
 _patch_settings(monkeypatch,svc,health_deploy_agent_url='')
 p=svc.DeployAgentProvider(FakeFetch());res=p.check()
 assert res.configured is False and res.status==svc.HealthStatus.UNKNOWN

def test_deploy_agent_provider_unreachable(monkeypatch):
 svc=_providers()
 _patch_settings(monkeypatch,svc,health_deploy_agent_url='http://agent.local:8090')
 p=svc.DeployAgentProvider(FakeFetch(health_error='URLError'));res=p.check()
 assert res.status==svc.HealthStatus.DOWN and res.configured is True

def test_deploy_agent_provider_healthy(monkeypatch):
 svc=_providers()
 _patch_settings(monkeypatch,svc,health_deploy_agent_url='http://agent.local:8090')
 p=svc.DeployAgentProvider(FakeFetch(health={'agent_version':'2.19.1'}));res=p.check()
 assert res.status==svc.HealthStatus.HEALTHY and res.details['version']=='2.19.1'

def test_server_provider_thresholds(monkeypatch):
 svc=_providers()
 _patch_settings(monkeypatch,svc,health_deploy_agent_url='http://agent.local:8090',health_cpu_warning_percent=75,health_ram_warning_percent=80,health_disk_warning_percent=80)
 ok=svc.ServerProvider(FakeFetch(health={},ops={'cpu_percent':18,'ram':{'percent':42},'disk':{'percent':51}})).check()
 assert ok.status==svc.HealthStatus.HEALTHY
 warn=svc.ServerProvider(FakeFetch(health={},ops={'cpu_percent':18,'ram':{'percent':42},'disk':{'percent':86}})).check()
 assert warn.status==svc.HealthStatus.DEGRADED

def test_server_provider_down_when_agent_unreachable(monkeypatch):
 svc=_providers()
 _patch_settings(monkeypatch,svc,health_deploy_agent_url='http://agent.local:8090')
 res=svc.ServerProvider(FakeFetch(health_error='TimeoutError')).check()
 assert res.status==svc.HealthStatus.DOWN and res.critical is True

def test_server_provider_unknown_when_ops_unavailable_but_agent_reachable(monkeypatch):
 svc=_providers()
 _patch_settings(monkeypatch,svc,health_deploy_agent_url='http://agent.local:8090')
 res=svc.ServerProvider(FakeFetch(health={'agent_version':'x'},ops=None,ops_error='HTTPError401')).check()
 assert res.status==svc.HealthStatus.UNKNOWN

def test_docker_provider_unhealthy_containers(monkeypatch):
 svc=_providers()
 _patch_settings(monkeypatch,svc,health_deploy_agent_url='http://agent.local:8090')
 res=svc.DockerProvider(FakeFetch(health={},ops={'docker_running':6,'docker_unhealthy':2})).check()
 assert res.status==svc.HealthStatus.DEGRADED and res.details['unhealthy']==2

# --- alert condition computation (dedup keyed by fingerprint) ---

def _svc():
 svc=_providers();return svc.SystemHealthService()

def test_alert_conditions_component_down_is_critical():
 svc_mod=_providers();service=_svc()
 by={'POSTGRESQL':HealthCheckResult('POSTGRESQL',svc_mod.HealthStatus.DOWN,datetime.now(timezone.utc),message='Không kết nối được',configured=True)}
 out=service._alert_conditions(by,[])
 assert out and out[0][0]=='COMPONENT_DOWN:POSTGRESQL' and out[0][2]=='CRITICAL'

def test_alert_conditions_kiosk_offline_fingerprint_is_per_device():
 service=_svc()
 items=[{'device_uuid':'K1','device_name':'K1','normalized_status':'OFFLINE','age_seconds':1500},
        {'device_uuid':'K2','device_name':'K2','normalized_status':'ONLINE','age_seconds':5}]
 out=service._alert_conditions({},items)
 assert [c[0] for c in out]==['KIOSK_OFFLINE:K1']

def test_alert_conditions_disk_severity_scales_with_threshold():
 svc_mod=_providers();service=_svc()
 srv=HealthCheckResult('SERVER',svc_mod.HealthStatus.DEGRADED,datetime.now(timezone.utc),details={'disk':{'percent':86}},configured=True)
 out=service._alert_conditions({'SERVER':srv},[])
 assert out[0][0]=='DISK_USAGE_HIGH' and out[0][2]=='MEDIUM'
 srv2=HealthCheckResult('SERVER',svc_mod.HealthStatus.DEGRADED,datetime.now(timezone.utc),details={'disk':{'percent':96}},configured=True)
 out2=service._alert_conditions({'SERVER':srv2},[])
 assert out2[0][2]=='HIGH'

def test_alert_conditions_no_alerts_when_all_healthy():
 svc_mod=_providers();service=_svc()
 by={'MESFLOW':HealthCheckResult('MESFLOW',svc_mod.HealthStatus.HEALTHY,datetime.now(timezone.utc),configured=True)}
 assert service._alert_conditions(by,[])==[]

def test_latest_migration_revision_matches_the_highest_numbered_file():
 # Deliberately does NOT hardcode a specific migration filename/prefix --
 # that exact literal-goes-stale-on-the-next-migration mistake is what
 # this dynamic derivation replaced (see system_health_service.py
 # _latest_migration_revision docstring). Instead: independently compute
 # the highest-numbered migrations/versions/*.py file's own `revision=`
 # value and assert the function returns exactly that.
 svc=_providers()
 versions_dir=Path(svc.__file__).resolve().parents[2]/'migrations'/'versions'
 import re
 best_num=-1;expected=''
 for f in versions_dir.glob('*.py'):
  m=re.match(r'(\d+)_',f.name)
  if not m:continue
  num=int(m.group(1))
  if num>best_num:
   rev_match=re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]",f.read_text(encoding='utf-8'),re.MULTILINE)
   if rev_match:best_num=num;expected=rev_match.group(1)
 assert svc._latest_migration_revision()==expected
