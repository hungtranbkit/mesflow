from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_overview_rework_visible():
    repo = text('app/mesflow/db/repositories/analytics.py')
    ui = text('app/mesflow/web/static/pages/overview.js')
    assert 'total_rework_qty' in repo and 'rework_qty' in repo
    assert 'Lỗi tổng' in ui and 'CHỜ SỬA' in ui and 'Phế' in ui
    assert 'TERMINAL_OPERATION_EQUAL_PART_WEIGHT' in repo and 'remaining_quantity' in ui


def test_daily_rework_visible():
    repo = text('app/mesflow/db/repositories/analytics.py')
    ui = text('app/mesflow/web/static/app.js')
    assert 'day_rework_qty' in repo and 'total_rework_qty' in repo
    assert 'day_rework_qty' in ui and 'sửa được' in ui and 'phế' in ui


def test_kiosk_rework_hint_visible():
    html = text('app/mesflow/web/templates/kiosk.html')
    assert 'CÓ LỖI SỬA ĐƯỢC KHÔNG?' in html
    assert 'KHÔNG, XONG' in html and 'CÓ LỖI SỬA ĐƯỢC' in html
