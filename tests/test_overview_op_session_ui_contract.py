from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JS=(ROOT/'app/mesflow/web/static/pages/overview.js').read_text()
CSS=(ROOT/'app/mesflow/web/static/ui.css').read_text()

def test_edit_buttons_use_modal_event_delegation():
    assert "modal.addEventListener('click',e=>" in JS
    assert "e.target.closest('[data-edit-session-qty]')" in JS
    assert "e.stopPropagation()" in JS

def test_session_rows_are_full_width_and_share_one_grid():
    assert ".op-detail-session-item{display:block;width:100%" in CSS
    assert ".op-detail-session-item .op-detail-session-row{width:100%" in CSS
    assert "grid-template-columns:minmax(160px,1fr) minmax(190px,1.25fr) 120px 110px minmax(150px,.9fr) 92px!important" in CSS

def test_action_column_stays_clickable_above_editor():
    assert ".op-session-actions{position:relative;z-index:10;pointer-events:auto!important" in CSS
    assert ".op-session-actions .btn{position:relative;z-index:11;pointer-events:auto!important" in CSS
    assert ".op-session-qty-editor[hidden]{display:none!important}" in CSS
