from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_routes_and_ui_present():
 s=(ROOT/'app/mesflow/web/execution.py').read_text()
 assert "/kiosk/bind" in s and "/station/heartbeat" in s and "/station/events/sync" in s
 js=(ROOT/'app/mesflow/web/static/app.js').read_text()
 # Kiosk timeline label was localized; still require its renderer and event list.
 assert 'renderKioskManagement' in js and 'Dòng thời gian thao tác' in js and 'event-timeline' in js
