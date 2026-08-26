from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
CSS=(ROOT/'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')

def test_current_shift_autodetect_present():
    assert 'currentShiftContext' in JS
    assert 'Asia/Ho_Chi_Minh' in JS
    assert "if(now.minute>=start)return {shift,date:now.date,active:true}" in JS
    assert 'previousDate(now.date)' in JS

def test_shift_picker_is_prominent():
    assert 'shift-picker' in JS
    assert 'Ca hiện tại' in JS  # label is no longer all-caps in the JS literal itself
    assert '.shift-picker.is-current' in CSS
    assert '.shift-picker.is-night' in CSS

def test_current_shift_selected_on_initial_render():
    assert "Number(x.id)===Number(currentCtx.shift.id)?'selected':''" in JS
    assert 'value="${currentCtx.date}"' in JS
