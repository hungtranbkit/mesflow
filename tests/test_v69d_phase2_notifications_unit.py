"""Phase 2 Notification + Diagnosis: pure unit tests (no PostgreSQL)."""
import dataclasses
import os
os.environ.setdefault('MESFLOW_SECRET_KEY','test')
from mesflow.services.notification_service import _meets_min
from mesflow.services.diagnostic_service import sanitize_log_text,LOG_SOURCES,LogService


def _patch_settings(monkeypatch,module,**overrides):
 # `settings` is a frozen dataclass singleton -- replace the module's
 # `settings` name with a modified copy rather than mutating fields in place.
 monkeypatch.setattr(module,'settings',dataclasses.replace(module.settings,**overrides))


def test_severity_routing_meets_min():
 assert _meets_min('CRITICAL','HIGH') is True
 assert _meets_min('HIGH','HIGH') is True
 assert _meets_min('MEDIUM','HIGH') is False
 assert _meets_min('LOW','HIGH') is False


def test_email_channel_not_configured_by_default(monkeypatch):
 from mesflow.services import notification_service as svc
 _patch_settings(monkeypatch,svc,smtp_host='')
 assert svc.EmailChannel().configured() is False


def test_telegram_channel_not_configured_by_default(monkeypatch):
 from mesflow.services import notification_service as svc
 _patch_settings(monkeypatch,svc,telegram_bot_token='')
 assert svc.TelegramChannel().configured() is False


def test_email_channel_configured_when_all_fields_set(monkeypatch):
 from mesflow.services import notification_service as svc
 _patch_settings(monkeypatch,svc,smtp_host='smtp.example.com',smtp_from='alerts@example.com',smtp_to='ops@example.com')
 assert svc.EmailChannel().configured() is True


def test_web_channel_always_configured():
 from mesflow.services.notification_service import WebChannel
 assert WebChannel().configured() is True


def test_log_source_allowlist_rejects_unknown():
 assert LogService().fetch('/etc/passwd')=={'ok':False,'error':'UNKNOWN_SOURCE'}
 assert LogService().fetch('../../etc/shadow')=={'ok':False,'error':'UNKNOWN_SOURCE'}
 assert set(LOG_SOURCES)=={'mesflow','postgres','qa','agent'}


def test_sanitize_log_text_redacts_secrets():
 raw="INFO ok\nAuthorization: Bearer abc123\npassword=hunter2\nplain line"
 out=sanitize_log_text(raw)
 assert 'hunter2' not in out and 'abc123' not in out
 assert 'plain line' in out
 assert 'password=***' in out


def test_notification_dispatcher_plan_includes_web_always(monkeypatch):
 from mesflow.services import notification_service as svc
 _patch_settings(monkeypatch,svc,notify_email_min_severity='HIGH',notify_telegram_min_severity='HIGH')
 d=svc.NotificationDispatcher()
 assert d._plan('LOW')==['WEB']
 assert d._plan('CRITICAL')==['WEB','EMAIL','TELEGRAM']
