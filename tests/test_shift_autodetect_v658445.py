from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
CSS=(ROOT/'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')

def test_current_shift_autodetect_present():
    assert 'currentShiftContext' in JS
    assert 'Asia/Ho_Chi_Minh' in JS
    assert "if(now.minute>=start)return {shift,date:now.date,active:true}" in JS
    assert 'previousDate(now.date)' in JS

def test_daily_dashboard_exposes_shift_metadata_without_a_filter():
    assert 'daily-shift-reference' in JS
    assert 'không lọc theo ca' in JS
    assert 'Ca ngày' in JS
    assert 'Ca tối' in JS

def test_date_is_the_only_dashboard_filter():
    assert 'id="dailyShift"' not in JS
    assert '/api/dashboard/day?date=${encodeURIComponent(date)}' in JS
    assert 'value="${currentCtx.date}"' in JS
