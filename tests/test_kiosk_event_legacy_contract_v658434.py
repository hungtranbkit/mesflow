from pathlib import Path

def test_kiosk_event_accepts_legacy_esp_fields():
    text=Path("app/mesflow/db/repositories/analytics.py").read_text()
    assert "data.get('event_uuid') or data.get('client_event_id')" in text
    assert "data.get('device_uuid') or data.get('device_id')" in text

def test_system_logs_detail_is_inline():
    text=Path("app/mesflow/web/static/pages/system-logs.js").read_text()
    assert 'data-log-detail=' in text
    assert 'data-error-detail=' in text
    assert 'sl-inline-detail' in text
    assert 'slDetail' not in text
