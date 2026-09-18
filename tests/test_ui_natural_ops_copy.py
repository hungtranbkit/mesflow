from pathlib import Path


ROOT = Path(__file__).parents[1]
STATIC = ROOT / "app/mesflow/web/static"


def test_operational_copy_uses_natural_vietnamese_labels():
    app = (STATIC / "app.js").read_text()
    detail = (STATIC / "pages/session-detail.js").read_text()
    overview = (STATIC / "pages/overview.js").read_text()
    kiosk = (STATIC / "pages/daily-dashboard-kiosk.js").read_text()
    rework = (STATIC / "pages/rework-queue.js").read_text()

    assert "Chậm hơn dự kiến" in app
    assert "Vượt dự kiến</small>" not in app
    assert "Tự động kết thúc khi hết ca · Chờ xác nhận sản lượng" in detail
    assert "Chờ xác nhận sản lượng" in overview
    assert "tự động kết thúc khi hết ca" in kiosk
    assert "chờ xác nhận sản lượng" in kiosk
    assert "Số lượng nhập vượt số đang chờ sửa" in rework
    assert "Vượt quá số chờ sửa" not in rework
