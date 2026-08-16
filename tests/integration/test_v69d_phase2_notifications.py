"""Phase 2 Health Center vertical slice (spec section 61): a stale kiosk
heartbeat crosses the OFFLINE threshold -> exactly one deduplicated
health_alerts row opens -> a WEB notification is created (existing
`notifications` table, reused) -> a diagnostic snapshot is captured ->
the same condition on a second poll does NOT duplicate anything -> a fresh
heartbeat recovers the kiosk -> the alert resolves -> a recovery WEB
notification fires -> Incident History preserves both events.
"""
import uuid
from datetime import datetime,timedelta,timezone
import pytest

pytestmark=pytest.mark.postgres
BASE='http://mesflow-test-api:8080'


def _seed_offline_kiosk(db,age_seconds=600):
 device=f'V69D-{uuid.uuid4()}'
 with db.cursor() as cur:
  cur.execute("INSERT INTO kiosk_identities(device_uuid,device_name,status,firmware_version) VALUES(%s,%s,'ACTIVE','1.8.4')",(device,device))
  cur.execute("INSERT INTO kiosk_status(device_uuid,health_state,queue_size,last_heartbeat_at) VALUES(%s,'OK',0,%s)",
              (device,datetime.now(timezone.utc)-timedelta(seconds=age_seconds)))
 return device


def test_kiosk_offline_vertical_slice_open_dedup_diagnose_recover(db,api):
 device=_seed_offline_kiosk(db,age_seconds=900)
 fp=f'KIOSK_OFFLINE:{device}'

 # 1) first poll: threshold crossed -> exactly one alert opens
 r1=api.get(f'{BASE}/api/system-health',timeout=15);assert r1.status_code==200,r1.text
 alert=db.execute("SELECT * FROM health_alerts WHERE fingerprint=%s AND resolved_at IS NULL",(fp,)).fetchone()
 assert alert is not None and alert['severity']=='HIGH'

 # 2) exactly one WEB notification was created for this OPENED transition
 notif=db.execute("SELECT * FROM notifications WHERE source_type='HEALTH_ALERT' AND source_id=%s",(fp,)).fetchone()
 assert notif is not None
 assert device in notif['title']
 delivery=db.execute("SELECT * FROM notification_deliveries WHERE alert_fingerprint=%s AND event_type='OPENED' AND channel='WEB'",(fp,)).fetchall()
 assert len(delivery)==1 and delivery[0]['status']=='SENT'

 # 3) a diagnostic snapshot was captured automatically on open
 snap=db.execute("SELECT * FROM health_diagnostics_snapshots WHERE alert_fingerprint=%s",(fp,)).fetchall()
 assert len(snap)>=1 and snap[0]['level']=='SUMMARY'

 # 4) second poll, same condition still true -> NO duplicate alert row, NO duplicate WEB delivery
 r2=api.get(f'{BASE}/api/system-health',timeout=15);assert r2.status_code==200
 open_rows=db.execute("SELECT COUNT(*) n FROM health_alerts WHERE fingerprint=%s AND resolved_at IS NULL",(fp,)).fetchone()
 assert open_rows['n']==1
 deliveries_after_second_poll=db.execute("SELECT COUNT(*) n FROM notification_deliveries WHERE alert_fingerprint=%s AND event_type='OPENED' AND channel='WEB'",(fp,)).fetchone()
 assert deliveries_after_second_poll['n']==1

 # 5) via the API: diagnostics + notifications for this alert are retrievable
 alert_id=alert['id']
 diag=api.get(f'{BASE}/api/system-health/alerts/{alert_id}/diagnostics',timeout=10)
 assert diag.status_code==200 and diag.json()['items']
 notifs=api.get(f'{BASE}/api/system-health/alerts/{alert_id}/notifications',timeout=10)
 assert notifs.status_code==200 and any(x['channel']=='WEB' for x in notifs.json()['items'])

 # 6) recovery: fresh heartbeat -> alert resolves, recovery WEB notification fires
 with db.cursor() as cur:
  cur.execute("UPDATE kiosk_status SET last_heartbeat_at=CURRENT_TIMESTAMP WHERE device_uuid=%s",(device,))
 r3=api.get(f'{BASE}/api/system-health',timeout=15);assert r3.status_code==200
 resolved=db.execute("SELECT * FROM health_alerts WHERE fingerprint=%s AND resolved_at IS NOT NULL ORDER BY id DESC LIMIT 1",(fp,)).fetchone()
 assert resolved is not None
 recovery_notif=db.execute("SELECT * FROM notifications WHERE source_type='HEALTH_ALERT' AND source_id=%s",(f'{fp}#resolved',)).fetchone()
 assert recovery_notif is not None and 'RECOVERED' in recovery_notif['title']
 recovery_delivery=db.execute("SELECT COUNT(*) n FROM notification_deliveries WHERE alert_fingerprint=%s AND event_type='RESOLVED' AND channel='WEB'",(fp,)).fetchone()
 assert recovery_delivery['n']==1

 # 7) Incident History preserves both the open and the recovery
 hist=api.get(f'{BASE}/api/system-health/history?limit=500',timeout=10).json()['items']
 kinds=[h['kind'] for h in hist if h.get('component')=='KIOSK_FLEET' and h.get('title')==alert['title']]
 assert 'ALERT_OPENED' in kinds and 'ALERT_RESOLVED' in kinds


def test_notification_channels_report_not_configured_by_default(api):
 r=api.get(f'{BASE}/api/system-health/notification-channels',timeout=10);assert r.status_code==200,r.text
 body=r.json()['channels']
 assert body['WEB']['configured'] is True
 assert body['EMAIL']['configured'] is False
 assert body['TELEGRAM']['configured'] is False


def test_test_notification_email_not_configured_returns_skipped(api):
 r=api.post(f'{BASE}/api/system-health/notification-channels/email/test',timeout=10)
 assert r.status_code==200,r.text
 body=r.json()
 assert body['ok'] is False and body['status']=='SKIPPED' and body['error']=='NOT_CONFIGURED'


def test_logs_endpoint_rejects_unknown_source_and_requires_admin(api,db):
 bad=api.get(f'{BASE}/api/system-health/logs?source=../../etc/passwd',timeout=10)
 assert bad.status_code in (400,403)


def test_logs_endpoint_forbidden_for_non_admin(db):
 import requests
 from werkzeug.security import generate_password_hash
 u=f'v69d-worker-{uuid.uuid4()}';p='Test@123456'
 with db.cursor() as cur:
  cur.execute("INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,'worker',%s,'manager',TRUE,FALSE) RETURNING id",(u,generate_password_hash(p)))
  uid=cur.fetchone()['id']
 try:
  s=requests.Session()
  assert s.post(f'{BASE}/api/auth/login',json={'username':u,'password':p}).status_code==200
  r=s.get(f'{BASE}/api/system-health/logs?source=mesflow')
  assert r.status_code==403
 finally:
  with db.cursor() as cur:cur.execute('DELETE FROM users WHERE id=%s',(uid,))
