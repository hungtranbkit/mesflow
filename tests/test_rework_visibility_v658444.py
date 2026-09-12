from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_overview_rework_visible():
    repo = text('app/mesflow/db/repositories/analytics.py')
    ui = text('app/mesflow/web/static/pages/overview.js')
    assert 'total_rework_qty' in repo and 'rework_qty' in repo
    assert 'NG tổng' in ui and 'CHỜ SỬA' in ui and 'Phế' in ui
    assert 'TERMINAL_OPERATION_EQUAL_PART_WEIGHT' in repo and 'remaining_quantity' in ui


def test_daily_rework_visible():
    repo = text('app/mesflow/db/repositories/analytics.py')
    ui = text('app/mesflow/web/static/app.js')
    assert 'day_rework_qty' in repo and 'total_rework_qty' in repo
    assert 'day_rework_qty' in ui and 'sửa được' in ui and 'phế' in ui


def test_kiosk_rework_hint_visible():
    """Kiosk phải HỎI rõ về lỗi sửa được, và nhãn phải nói đúng phím nào làm gì.

    Nhãn đổi ở REQ-KIOSK-011: chủ sản phẩm chốt `1` = CÓ, `2` = tiếp tục (bản
    trước là `1 KHÔNG, XONG` / `2 CÓ LỖI SỬA ĐƯỢC`, khớp firmware ESP v2 —
    xem docs/KIOSK_ESP_PARITY.md §2.2 để biết hai thiết bị đang lệch chỗ nào).
    Bài test khoá cả nhãn lẫn ÁNH XẠ PHÍM, vì một nhãn đúng đặt cạnh phím sai
    còn tệ hơn không có nhãn.
    """
    html = text('app/mesflow/web/templates/kiosk.html')
    assert 'CÓ LỖI SỬA ĐƯỢC KHÔNG?' in html
    # Nút "1" là nhánh CÓ, nút "2" là nhánh tiếp tục.
    assert '<strong>1</strong><span>CÓ, NHẬP SỐ</span>' in html
    assert '<strong>2</strong><span>TIẾP TỤC, KHÔNG CÓ</span>' in html
    # Phím tắt phải nhìn thấy được, không chỉ nằm trong JavaScript.
    assert 'để tiếp tục mà không nhập lỗi sửa được' in html

    js = text('app/mesflow/web/static/kiosk.js')
    assert "if (event.key === '1') { event.preventDefault(); chooseRework(); }" in js
    # `#` đã rời ánh xạ phím của WEB (P1 2026-09-12): bàn phím số rời không có
    # phím đó. ESP giữ `#` — thiết bị khác, firmware khác, xem §2.2 của doc trên.
    assert "event.key === '2' || event.key === 'Enter'" in js
