"""Regression guard for the web kiosk "XÁC NHẬN" screen bug.

Bug: screen-finish-confirm has three .choice-button elements sharing one
choice-grid: finish-confirm-ok ('#' XÁC NHẬN), finish-confirm-edit
('*' QUAY LẠI), and finish-submit-retry ('#' THỬ LẠI, toggled by JS via the
`hidden` attribute -- shown only after a failed submit, in place of the OK
button). kiosk.css set `.choice-button{display:flex;...}` with no
`[hidden]` override. Author CSS beats the browser's built-in
`[hidden]{display:none}` rule at equal specificity regardless of selector
order, so `.choice-button[hidden]` (retry) stayed rendered even though its
`hidden` DOM property was true -- verified live: getComputedStyle(el).display
was "flex", not "none". The result: the confirm screen showed the retry
button wrapped onto a second row from the very first view (before any
submit was even attempted), so the operator saw TWO '#'-labeled buttons
side by side ('#' XÁC NHẬN and '#' THỬ LẠI) -- reported as "2 dấu # giống
nhau" on the confirmation screen.

Fix: `.choice-button[hidden]{display:none}` (specificity 0-2-0, so it wins
regardless of source order) restores the correct hide behavior.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def _css():
    return (ROOT / 'app/mesflow/web/static/kiosk.css').read_text(encoding='utf-8')


def test_choice_button_has_a_hidden_override():
    css = _css()
    assert '.choice-button{display:flex' in css
    assert '.choice-button[hidden]{display:none}' in css


def test_confirm_screen_still_has_the_three_expected_buttons():
    html = (ROOT / 'app/mesflow/web/templates/kiosk.html').read_text(encoding='utf-8')
    assert 'id="finish-confirm-ok"' in html and '<strong>#</strong><span>XÁC NHẬN</span>' in html
    assert 'id="finish-confirm-edit"' in html and '<strong>*</strong><span>QUAY LẠI</span>' in html
    # Must stay `hidden` by default in markup -- the CSS override is what
    # makes that attribute actually take effect once JS toggles it.
    assert 'id="finish-submit-retry"' in html
    retry_tag = html[html.index('id="finish-submit-retry"') - 40 : html.index('id="finish-submit-retry"') + 120]
    assert 'hidden' in retry_tag
