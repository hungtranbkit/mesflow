import uuid,requests
from datetime import datetime,timezone,timedelta
import pytest
from werkzeug.security import generate_password_hash
pytestmark=pytest.mark.postgres
BASE='http://mesflow-test-api:8080'
def test_summary_postgres_and_missing_optional_components(api):
 r=api.get(f'{BASE}/api/system-health',timeout=10);assert r.status_code==200,r.text;b=r.json();by={x['component']:x for x in b['components']}
 # migration_revision is now derived dynamically from the migrations
 # directory (system_health_service._latest_migration_revision) rather
 # than a hand-maintained literal here -- it must simply match itself,
 # not a version string that goes stale every time a migration is added.
 assert by['POSTGRESQL']['status']=='HEALTHY'
 assert by['POSTGRESQL']['details']['migration_revision']==by['POSTGRESQL']['details']['expected_revision']
 # SERVER_AGENT (a separate, unrelated project) was replaced by SERVER/
 # DOCKER/DEPLOY_AGENT, all backed by Deploy Agent -- unconfigured in this
 # test environment (no MESFLOW_DEPLOY_AGENT_URL), so all three read UNKNOWN.
 for component in ('SERVER','DOCKER','DEPLOY_AGENT'):
  assert by[component]['configured'] is False and by[component]['status']=='UNKNOWN'
 assert by['QA_CENTER']['configured'] is False and b['overall_status'] in ('HEALTHY','DEGRADED','UNKNOWN')
def test_kiosk_online_degraded_offline_and_fleet_counts(db,api):
 now=datetime.now(timezone.utc)
 with db.cursor() as cur:
  for n,age,queue in [('ON',20,0),('DEG',180,3),('OFF',600,0)]:
   device=f'V69-{n}-{uuid.uuid4()}';cur.execute("INSERT INTO kiosk_identities(device_uuid,device_name,status,firmware_version) VALUES(%s,%s,'ACTIVE','1.8.4')",(device,device));cur.execute("INSERT INTO kiosk_status(device_uuid,health_state,queue_size,last_heartbeat_at) VALUES(%s,'OK',%s,%s)",(device,queue,now-timedelta(seconds=age)))
 r=api.get(f'{BASE}/api/system-health/kiosks',timeout=10).json();items=[x for x in r['items'] if x['device_uuid'].startswith('V69-')];assert {x['normalized_status'] for x in items}=={'ONLINE','DEGRADED','OFFLINE'}
def test_job_failed_missed_disabled(db,api):
 with db.cursor() as cur:
  cur.execute("INSERT INTO scheduled_job_health(job_name,display_name,enabled,last_status,next_expected_at,grace_seconds) VALUES ('v69-fail','Fail',TRUE,'FAILED',CURRENT_TIMESTAMP,60),('v69-missed','Missed',TRUE,'SUCCESS',CURRENT_TIMESTAMP-INTERVAL '10 minutes',60),('v69-disabled','Disabled',FALSE,'UNKNOWN',NULL,60) ON CONFLICT(job_name) DO UPDATE SET last_status=EXCLUDED.last_status,next_expected_at=EXCLUDED.next_expected_at")
 b=api.get(f'{BASE}/api/system-health',timeout=10).json();jobs=next(x for x in b['components'] if x['component']=='JOBS');states={x['normalized_status'] for x in jobs['details']['items'] if x['job_name'].startswith('v69-')};assert states=={'FAILED','MISSED','DISABLED'} and jobs['status']=='DEGRADED'
def test_error_fingerprinting_groups_repeats(db,api):
 message=f'database timeout {uuid.uuid4()}'
 with db.cursor() as cur:
  for i in range(3):cur.execute("INSERT INTO action_logs(trace_id,method,path,outcome,error_type,error_message,http_status) VALUES(%s,'GET','/v69','ERROR','TimeoutError',%s,500)",(str(uuid.uuid4()),message))
 errors=api.get(f'{BASE}/api/system-health',timeout=10).json()['recent_errors'];row=next(x for x in errors if x['message']==message);assert row['occurrences']==3
def test_recovery_transition_is_recorded(db,api,monkeypatch):
 api.get(f'{BASE}/api/system-health',timeout=10)
 with db.cursor() as cur:cur.execute("UPDATE component_health_state SET status='DOWN' WHERE component='KIOSK_FLEET'")
 api.get(f'{BASE}/api/system-health',timeout=10)
 with db.cursor() as cur:cur.execute("SELECT old_status,new_status FROM component_health_history WHERE component='KIOSK_FLEET' ORDER BY id DESC LIMIT 1");x=cur.fetchone();assert x['old_status']=='DOWN' and x['new_status'] in ('HEALTHY','DEGRADED','UNKNOWN')
def test_worker_forbidden(db,api):
 u=f'v69-worker-{uuid.uuid4()}';p='Test@123456'
 with db.cursor() as cur:cur.execute("INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,'worker',%s,'worker',TRUE,FALSE) RETURNING id",(u,generate_password_hash(p)));uid=cur.fetchone()['id']
 try:s=requests.Session();assert s.post(f'{BASE}/api/auth/login',json={'username':u,'password':p}).status_code==200;assert s.get(f'{BASE}/api/system-health').status_code==403
 finally:
  with db.cursor() as cur:cur.execute('DELETE FROM users WHERE id=%s',(uid,))
