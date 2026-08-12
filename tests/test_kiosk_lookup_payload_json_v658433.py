from pathlib import Path


def test_kiosk_event_payload_is_json_serialized():
    text = Path("app/mesflow/db/repositories/analytics.py").read_text(encoding="utf-8")
    assert "json.dumps(payload,ensure_ascii=False,default=str)" in text


def test_legacy_lookup_writes_scan_events():
    text = Path("app/mesflow/web/execution.py").read_text(encoding="utf-8")
    assert "'event_type':'SCAN_EMPLOYEE'" in text
    assert "'event_type':'SCAN_OPERATION'" in text
