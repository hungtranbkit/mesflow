from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_po_planned_dates_match_the_compact_due_date_control():
    js = (ROOT / "app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "app/mesflow/web/static/ui.css").read_text(encoding="utf-8")

    assert "function poPlannedDateField" in js
    assert 'type="date"' in js
    assert 'type="datetime-local"' not in js[js.index("function poPlannedDateField"):js.index("function canStartProductionOrder")]
    assert "data-close-picker" not in js
    assert "po-datetime-done" not in js
    assert ".po-datetime-control" not in css


def test_po_planned_end_date_is_inclusive_through_end_of_day():
    js = (ROOT / "app/mesflow/web/static/app.js").read_text(encoding="utf-8")

    assert "function localInputToIso(value,endOfDay=false)" in js
    assert "endOfDay?'23:59:59':'00:00:00'" in js
    assert js.count("planned_end_at:localInputToIso(f.planned_end_at.value,true)") == 3
