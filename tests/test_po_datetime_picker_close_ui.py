from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_po_datetime_fields_offer_an_explicit_picker_close_action():
    js = (ROOT / "app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "app/mesflow/web/static/ui.css").read_text(encoding="utf-8")

    assert "function poDateTimeField" in js
    assert "function bindPoDateTimeDoneButtons" in js
    assert 'data-close-picker="${name}"' in js
    assert ">Xong</button>" in js
    assert "input.blur();button.focus()" in js
    assert js.count("bindPoDateTimeDoneButtons(box)") == 3
    assert ".po-datetime-control" in css
