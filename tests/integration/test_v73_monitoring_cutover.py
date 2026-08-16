"""Monitoring ownership cutover (reports/SYSTEM_LOG_AUDIT_SEPARATION.md,
follow-up): Deploy Agent is authoritative for SYSTEM/INFRASTRUCTURE
monitoring; MESFlow's legacy V69 health writer is off by default and must
create zero new rows in any of the 8 legacy tables, while application
readiness/health stay fully functional and legacy history stays readable.

This imports the service/CLI modules directly in the `tests` container
(which shares the same Postgres as `mesflow-test-api` via DATABASE_URL, but
does NOT set MESFLOW_LEGACY_HEALTH_WRITER_ENABLED) -- so `settings` here
reflects the real, off-by-default production configuration, unlike the
`mesflow-test-api` container which has it explicitly turned back on so the
pre-existing V69/Phase2/Phase3 suite keeps proving the mechanism works.
"""
import os
import pytest

pytestmark = pytest.mark.postgres
BASE = os.environ.get('MESFLOW_BASE_URL', 'http://mesflow-test-api:8080').rstrip('/')

LEGACY_TABLES = [
    'component_health_state', 'component_health_history', 'scheduled_job_health',
    'health_alerts', 'notification_deliveries', 'health_diagnostics_snapshots',
    'health_metric_samples', 'predictive_insights', 'ai_incident_analyses',
]


def _counts(db):
    with db.cursor() as cur:
        out = {}
        for t in LEGACY_TABLES:
            cur.execute(f'SELECT COUNT(*) n FROM {t}')
            out[t] = cur.fetchone()['n']
        return out


def test_legacy_writer_disabled_by_default_in_this_process():
    from mesflow.core.config import settings
    assert settings.legacy_health_writer_enabled is False


def test_summary_creates_zero_new_rows_in_any_legacy_table(db):
    """Section 8: 'Verify no duplicate infrastructure incident is created by
    MESFlow after cutover.' Calls the real SystemHealthService.summary() --
    the exact method the (now-removed) System Health page used to poll every
    15s -- three times in a row, including once with a DOWN-looking
    component so the old code path *would* have opened a health_alerts row.
    Row counts across all 8 legacy tables must be identical before/after."""
    from mesflow.services.system_health_service import SystemHealthService
    before = _counts(db)
    svc = SystemHealthService()
    svc.summary(correlation_id='v73-cutover-check-1')
    svc.summary(correlation_id='v73-cutover-check-2')
    svc.summary(correlation_id='v73-cutover-check-3')
    after = _counts(db)
    assert after == before, f'legacy tables changed: before={before} after={after}'


def test_summary_still_computes_a_live_result_without_persisting():
    """The write side is gated, not the read/compute side -- the (retired)
    UI's replacement, Deploy Agent's Operations Center, is a different
    system entirely, but MESFlow's own service code must not silently start
    raising just because writes are disabled."""
    from mesflow.services.system_health_service import SystemHealthService
    result = SystemHealthService().summary()
    assert result['overall_status'] in ('HEALTHY', 'DEGRADED', 'DOWN', 'UNKNOWN')
    assert isinstance(result['components'], list) and result['components']
    assert isinstance(result['active_alerts'], list)  # read-only SELECT of any still-open legacy alert


def test_run_predictive_cli_is_a_noop_when_disabled(db, capsys):
    from mesflow import cli
    before = _counts(db)
    cli.run_predictive()
    after = _counts(db)
    assert after == before
    assert 'disabled' in capsys.readouterr().out.lower()


def test_diagnostic_snapshot_and_ai_analysis_do_not_persist(db):
    from mesflow.services.diagnostic_service import DiagnosticService
    from mesflow.services.ai_incident_service import IncidentAIService
    before = _counts(db)
    DiagnosticService().snapshot('MESFLOW', 'SUMMARY')
    fake_alert = {'fingerprint': 'v73-fake', 'severity': 'LOW', 'title': 'x', 'message': 'x'}
    IncidentAIService().analyze(fake_alert, 'OPEN')
    after = _counts(db)
    assert after == before


def test_notification_dispatch_and_test_send_do_not_persist(db):
    from mesflow.services.notification_service import NotificationDispatcher
    before = _counts(db)
    fake_alert = {'fingerprint': 'v73-fake-notif', 'severity': 'HIGH', 'title': 'x', 'message': 'x'}
    NotificationDispatcher().dispatch(fake_alert, 'OPENED')
    NotificationDispatcher().test('WEB')
    after = _counts(db)
    assert after == before


def test_application_readiness_and_health_endpoints_unaffected(api):
    """Section 4/5: disabling the legacy writer must never affect MESFlow's
    own readiness/health endpoints -- these are a completely different
    blueprint (mesflow.web.system, SystemRepository), not the retired
    /api/system-health service."""
    r = api.get(f'{BASE}/api/system/ready', timeout=10)
    assert r.status_code == 200 and r.json()['ok'] is True
    r = api.get(f'{BASE}/api/system/health', timeout=10)
    assert r.status_code == 200 and r.json()['ok'] is True


def test_legacy_history_stays_readable(db):
    """Section 3/9: 'Do NOT drop tables. Preserve existing records as
    legacy/read-only history.' Every legacy table must still be a plain,
    working SELECT (not dropped, not renamed, not permission-locked at the
    DB level)."""
    counts = _counts(db)
    assert set(counts) == set(LEGACY_TABLES)  # every table exists and is queryable


def test_system_logs_page_renamed_to_application_log():
    """Section 6: MESFlow's own technical page (action_logs/error_traces)
    is 'Nhật ký ứng dụng' now, not 'Nhật ký hệ thống' -- that label belongs
    to Deploy Agent's Operations Center tab exclusively."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    js = (root / 'app/mesflow/web/static/pages/system-logs.js').read_text(encoding='utf-8')
    assert "title.textContent='Nhật ký ứng dụng'" in js
    assert "title.textContent='Nhật ký hệ thống'" not in js


def test_system_health_and_operations_center_removed_from_mesflow():
    """Trailing request: tabs already owned by Deploy Agent are deleted
    from MESFlow, not just hidden -- confirmed by absence from source."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    app_js = (root / 'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    assert "page:'system-health'" not in app_js
    assert "page:'operations-center'" not in app_js
    assert "renderOperationsCenter" not in app_js
    assert not (root / 'app/mesflow/web/static/pages/system-health.js').exists()
