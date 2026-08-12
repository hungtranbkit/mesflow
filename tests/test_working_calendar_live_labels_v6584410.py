from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/mesflow/web/static/app.js").read_text(encoding="utf-8")

def test_shift_interval_time_inputs_are_direct():
    assert 'name="start_time"' in JS
    assert 'name="end_time"' in JS
    assert 'Từ phút' not in JS[JS.index('async function renderWorkingCalendar(){'):JS.index('async function renderProductionOrders(){')]

def test_anchor_times_sync_work_interval_edges():
    assert 'syncWorkEdges' in JS
    assert "f.elements.anchor_start?.addEventListener('change',syncWorkEdges)" in JS
    assert "f.elements.anchor_end?.addEventListener('change',syncWorkEdges)" in JS
    assert 'isCrossMidnight' in JS

def test_new_interval_follows_previous_interval():
    assert 'const last=current.intervals[current.intervals.length-1]' in JS
    assert 'end_minute:start+60' in JS
