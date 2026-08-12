from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_web_kiosk_rework_flow_contract():
    html = (ROOT / 'app/mesflow/web/templates/kiosk.html').read_text(encoding='utf-8')
    js = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')
    api = (ROOT / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')
    assert 'SẢN PHẨM ĐẠT' in html and 'kiosk-good-quantity' in html
    assert 'SẢN PHẨM LỖI' in html and 'kiosk-defect-quantity' in html
    assert 'CÓ LỖI SỬA ĐƯỢC KHÔNG?' in html
    assert 'kiosk-rework-choice-none' in html and 'kiosk-rework-choice-yes' in html
    assert 'LỖI SỬA ĐƯỢC' in html and 'kiosk-rework-quantity' in html
    assert "pendingFinish.defect" in js
    assert "pendingFinish.defect - pendingFinish.rework" in js
    assert 'request_id:pendingFinish.requestId' in js
    assert 'rework_qty:rework' in js
    assert "body.get('rework_qty')" in api


def test_web_kiosk_keyboard_shortcuts():
    js = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')
    assert "state === 'finish-confirm'" in js
    assert "event.key === '#'" in js
    assert "event.key === '*'" in js
    assert "state === 'ask-rework'" in js
