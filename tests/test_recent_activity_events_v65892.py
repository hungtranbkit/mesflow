from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_recent_activity_has_start_and_quantity_events():
    text=(ROOT/'app/mesflow/db/repositories/analytics.py').read_text(encoding='utf-8')
    assert "'SESSION_STARTED'" in text
    assert "'QUANTITY_REPORTED'" in text
    assert 'ws.started_at activity_at' in text
    assert 'good_qty' in text and 'defect_qty' in text

def test_dashboard_labels_both_event_types():
    text=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    assert 'Bắt đầu session' in text
    assert 'Nhập sản lượng' in text
