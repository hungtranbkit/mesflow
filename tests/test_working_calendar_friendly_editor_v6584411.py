from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'app/mesflow/web/static/app.js').read_text()
CSS=(ROOT/'app/mesflow/web/static/ui.css').read_text()

def test_no_minute_inputs_exposed_to_user():
    block=JS[JS.index('async function renderWorkingCalendar(){'):JS.index('async function renderProductionOrders(){')]
    assert 'Từ phút' not in block
    assert 'Đến phút' not in block
    assert 'name="start_time"' in block
    assert 'name="end_time"' in block

def test_target_is_entered_as_hours_but_saved_as_minutes():
    assert 'name="target_hours"' in JS
    assert 'target_minutes:Math.round(Number(f.elements.target_hours.value)*60)' in JS

def test_cross_midnight_is_automatic():
    assert 'const isCrossMidnight=' in JS
    assert 'cross_midnight:cross' in JS
    block=JS[JS.index('async function renderWorkingCalendar(){'):JS.index('async function renderProductionOrders(){')]
    assert 'name="cross_midnight"' not in block

def test_friendly_interval_layout_css_exists():
    assert '.shift-interval-friendly' in CSS
    assert '.shift-interval-head' in CSS
