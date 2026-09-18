from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/mesflow/web/static"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_primary_surfaces_use_vietnamese_work_session_copy():
    app = _read("app/mesflow/web/static/app.js")
    detail = _read("app/mesflow/web/static/pages/session-detail.js")
    exceptions = _read("app/mesflow/web/static/pages/session-exceptions.js")
    kiosk = _read("app/mesflow/web/static/kiosk.js")

    for label in (
        "Quản lý phiên làm việc",
        "B · Nhân viên / phiên làm việc",
        "Phiên làm việc theo bộ lọc",
        "${g.sessions.length} phiên làm việc",
        "Mở chi tiết phiên làm việc",
    ):
        assert label in app
    assert "Thông tin phiên làm việc" in detail
    assert "Nhận và mở phiên làm việc" in exceptions
    assert "kiểm tra phiên làm việc đang mở" in kiosk


def test_known_legacy_visible_copy_is_gone_from_managed_ui_sources():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [STATIC / "app.js", STATIC / "kiosk.js", *sorted((STATIC / "pages").glob("*.js"))]
    )
    sources = re.sub(r"/\*.*?\*/", "", sources, flags=re.DOTALL)
    sources = re.sub(r"^[ \t]*//[^\n]*$", "", sources, flags=re.MULTILINE)
    for old_copy in (
        "Quản lý Session",
        "Session theo bộ lọc",
        "Nhận và mở Session",
        "Session đã kết thúc",
        "Timeline session trong ngày",
        "Chưa session nào chốt số",
    ):
        assert old_copy not in sources


def test_work_session_exception_copy_uses_natural_vietnamese_meaning():
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [STATIC / "app.js", *sorted((STATIC / "pages").glob("*.js"))]
    )
    for final_copy in (
        "Phiên làm việc bất thường",
        "Các phiên làm việc bất thường",
        "Không có phiên làm việc bất thường",
        "Xử lý phiên làm việc bất thường",
        "Mã phiên làm việc",
        "Chưa có phiên làm việc nào chốt số",
    ):
        assert final_copy in sources
    for unnatural_copy in (
        "Ngoại lệ phiên làm việc",
        "ngoại lệ phiên làm việc",
        "Phiên làm việc ngoại lệ",
        "phiên làm việc ngoại lệ",
        "Phiên làm việc ID",
        "Chưa phiên làm việc nào",
    ):
        assert unnatural_copy not in sources


def test_machine_contract_names_remain_unchanged():
    app = _read("app/mesflow/web/static/app.js")
    execution = _read("app/mesflow/db/repositories/execution.py")
    audit = _read("app/mesflow/domain/audit_presentation.py")

    for token in (
        "'session-management'",
        "'session-exceptions'",
        "data-session-id",
        "/api/session-management",
        "/api/supervisor/sessions/",
        "session_id",
        "SessionDetailDrawer",
    ):
        assert token in app
    assert "{'ok':True,'session':dict(row)" in execution
    assert "response['session']" in execution
    assert "'SESSION_STARTED'" in execution
    assert "'session': 'Phiên làm việc'" in audit
