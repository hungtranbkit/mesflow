from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "mesflow" / "web" / "static"


def test_shared_ui_foundation_exposes_required_primitives():
    """Các primitive nền tảng phải CÓ MẶT trong core/ui.js.

    KHÔNG trùng với test_mfui_export_line_keeps_every_shared_primitive ở cuối
    file, dù đọc lướt thì giống: bài này kiểm tên có tồn tại trong file (bắt ca
    "primitive bị xoá hẳn"), bài kia kiểm tên có nằm trong DÒNG `return {…}`
    (bắt ca "primitive còn nguyên nhưng rơi khỏi export"). Một tên vẫn xuất hiện
    ở chỗ khai báo và ở lời gọi nội bộ sau khi đã rơi khỏi export, nên phép kiểm
    dưới đây XANH ở đúng ca kia -- và với mountBackToTop thì cả E2E cũng xanh
    (nó chỉ được gọi nội bộ, không caller ngoài). Bỏ bài kia đi là gỡ mất tuyến
    phòng thủ DUY NHẤT cho ca đó. Đừng gộp hai bài này.
    """
    source = (STATIC / "core" / "ui.js").read_text(encoding="utf-8")
    for primitive in (
        "pageShell", "pageHeader", "openDrawer", "openModal", "confirmDialog",
        "filterBar", "statusBadge", "loadingState", "emptyState", "errorState",
    ):
        assert primitive in source


def test_shared_drawer_has_keyboard_history_focus_and_standard_sizes():
    source = (STATIC / "core" / "ui.js").read_text(encoding="utf-8")
    css = (STATIC / "ui.css").read_text(encoding="utf-8")
    assert "Escape" in source
    assert "popstate" in source
    assert "history.back" in source
    assert "origin.focus" in source
    for size in ("--ui-drawer-sm", "--ui-drawer-md", "--ui-drawer-lg", "--ui-drawer-xl"):
        assert size in css


def test_session_management_uses_shared_vertical_slice():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    session = (STATIC / "pages" / "session-detail.js").read_text(encoding="utf-8")
    # Session Management builds its shell inline (not via MFUI.pageShell,
    # whose header is always-on and duplicated the page title already shown
    # by the outer workspace-header -- real defect reported live). Since the
    # UI Template Standard's Golden Reference migration (real structural
    # convergence, not just a shared class name on divergent containers),
    # it uses the same .page-shell/.page-header/.content-panel geometry as
    # Production Order and Session Exception Center -- verified pixel-equal
    # via getBoundingClientRect() across all three, not just class presence.
    assert 'id="sessionManagementPage"' in app
    assert '"page-shell"' in app
    assert '"page-header"' in app
    assert '"content-panel"' in app
    assert "MFUI.filterBar" in app
    assert "SessionDetailDrawer.open" in app
    assert "MFUI.openDrawer" in session
    assert "MFUI.loadingState" in session
    assert "MFUI.errorState" in session


def test_navigation_supports_url_and_refresh_state():
    nav = (STATIC / "core" / "nav.js").read_text(encoding="utf-8")
    template = (ROOT / "app" / "mesflow" / "web" / "templates" / "app.html").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "sessionStorage" in nav
    assert "setPageUrl" in nav
    assert "setQuery" in nav
    assert "bootParams.get('page')" in template
    assert "/static/core/ui.js" in template
    # Dashboard/URL nav-audit fix (2026-09-09): every top-level page --
    # including Overview/Dashboard, previously the only two sidebar entries
    # with no `?page=` URL at all -- gets it from this one place in
    # openPage(), and a single popstate listener (not a second, parallel
    # routing mechanism) renders whichever page the URL now names on
    # browser Back/Forward. The boot call normalizes the URL with
    # replaceState, not pushState, so a refresh never leaves a phantom
    # history entry behind.
    assert "AppNav.setPageUrl(id,{replace:historyMode==='replace'||samePage})" in app
    assert "window.addEventListener('popstate'" in app
    assert "{historyMode:'replace'}" in template


def test_foundation_keeps_business_and_kiosk_boundaries_unchanged():
    source = (STATIC / "core" / "ui.js").read_text(encoding="utf-8")
    assert "/api/" not in source
    assert "fetch(" not in source
    assert "good_qty" not in source
    assert "repairable" not in source.lower()

def _mfui_exported_names() -> set[str]:
    """Tên THỰC SỰ nằm trong dòng `return {…}` của IIFE MFUI.

    Cố ý không dùng `"mountBackToTop" in source`: tên đó vẫn xuất hiện ở chỗ khai
    báo và ở lời gọi nội bộ, nên phép kiểm kiểu đó VẪN XANH khi tên bị rơi khỏi
    dòng export. Đây không phải giả định -- `mountBackToTop` được gọi nội bộ
    trong chính IIFE và không có caller ngoài nào, nên mất export là mất IM
    LẶNG: nút vẫn mount, vẫn chạy, mọi bài E2E vẫn xanh, chỉ có tính tái dùng
    cho màn khác là biến mất -- tức đúng lý do REQ-UI-018 tồn tại.
    """
    source = (STATIC / "core" / "ui.js").read_text(encoding="utf-8")
    line = next(l for l in source.splitlines() if l.strip().startswith("return {statusBadge"))
    body = line[line.index("{") + 1:line.rindex("}")]
    return {name.strip() for name in body.split(",") if name.strip()}


def test_mfui_export_line_keeps_every_shared_primitive():
    """Dòng export của MFUI là chỗ HAI LANE cùng sửa khi thêm primitive.

    hp3 chèn `mountBackToTop,BACK_TO_TOP_VIEWPORTS,`, một lane khác chèn tên của
    họ vào CÙNG dòng đó -> git chắc chắn báo conflict, và cách gỡ đúng là giữ cả
    hai danh sách. Bài này tồn tại để ai gỡ conflict bằng cách "lấy một bên" thì
    đỏ ngay ở tầng rẻ nhất, thay vì phải chạy tới E2E (mà với hướng mất-hp3 thì
    E2E cũng không đỏ).

    Xem thêm test_shared_ui_foundation_exposes_required_primitives ở đầu file:
    hai bài bắt hai ca KHÁC nhau ("bị xoá hẳn" vs "rơi khỏi export"), cố ý cùng
    tồn tại. Đây là tuyến phòng thủ duy nhất cho ca thứ hai.
    """
    exported = _mfui_exported_names()
    for primitive in ("mountBackToTop", "BACK_TO_TOP_VIEWPORTS", "opIdentity",
                      "filterBar", "contentPanel", "errorState", "debounce"):
        assert primitive in exported, (
            f"{primitive} không còn trong dòng export của MFUI -- nhiều khả năng "
            f"một lần gỡ conflict đã lấy dòng của một bên và bỏ bên kia. "
            f"Đang export: {sorted(exported)}"
        )


def test_back_to_top_automount_runs_after_its_declaration():
    """Khối auto-mount phải nằm SAU `const mountBackToTop`.

    Đặt trước là temporal dead zone: nhánh `else` (script nạp khi DOM đã ready)
    ném ReferenceError NGAY, trước cả `return {…}` -- `window.MFUI` không được
    gán và cả app chết. Hôm nay nhánh đó không chạy vì core/ui.js là script CHẶN
    (không defer/async), nên lỗi nằm im cho tới khi ai đó thêm `defer`, đổi thứ
    tự nạp, hoặc nạp file này động. Đã suýt ship đúng bug này.
    """
    source = (STATIC / "core" / "ui.js").read_text(encoding="utf-8")
    declaration = source.index("const mountBackToTop =")
    call = source.index("} else { mountBackToTop(); }")
    assert declaration < call, (
        "khối auto-mount đang gọi mountBackToTop() TRƯỚC khi nó được khai báo "
        "-- nhánh else sẽ ném ReferenceError và window.MFUI không bao giờ được gán"
    )
