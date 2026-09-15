"""Web kiosk auto-update on redeploy.

Context: a web kiosk machine can be physically locked (no keyboard/mouse
access) with no remote admin either -- its browser tab, once loaded, ran
whatever JS/CSS/HTML it fetched at that moment forever. Deploying a fix to
the server changed nothing for that already-open tab: kiosk.js had no
version check or reload, so /static/kiosk.css?v={{version}} cache-busting
only takes effect on the NEXT page load, which never came.

Fix: kiosk.html now stamps the loaded version onto <html data-version=...>;
/api/kiosk-web/heartbeat (already polled every 30s) now also returns the
server's current version; kiosk.js compares the two and calls
location.reload() -- but only when idle (state==='ready', demo panel
closed), so an operator mid-task is never interrupted.

Verified live (see commit message) with a real server + Playwright: an
idle tab reloads within one heartbeat cycle when the server reports a
different version; a tab parked mid-flow does not.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_kiosk_page_stamps_its_loaded_version():
    html = (ROOT / 'app/mesflow/web/templates/kiosk.html').read_text(encoding='utf-8')
    assert 'data-version="{{ version }}"' in html


def test_heartbeat_endpoint_returns_current_server_version():
    source = (ROOT / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')
    fn = source.split('def kiosk_web_heartbeat():', 1)[1].split('\n@bp.', 1)[0]
    assert 'version=__version__' in fn


def test_kiosk_js_reloads_only_when_idle_on_version_mismatch():
    """Ba bảo đảm, không phụ thuộc chúng nằm trong hàm nào.

    Bản trước soi chuỗi bên trong đúng một hàm. Khi phần "đã rảnh chưa" được
    tách ra thành isIdleForReload()/applyPendingReload() -- để còn nạp được
    ngay lúc quay về màn chờ mà không chờ thêm một nhịp heartbeat -- bài kiểm
    đỏ dù hành vi không đổi. Nay canh BẢO ĐẢM: so sánh phiên bản, chặn khi bận,
    và chỉ có đúng một chỗ gọi reload.
    """
    js = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')

    # 1. Không bao giờ nạp lại khi hai bên cùng một phiên bản.
    assert 'function reloadIfNewVersionAvailable(serverVersion) {' in js
    assert 'serverVersion === loadedVersion' in js

    # 2. Ranh giới "rảnh" nằm ở một chỗ duy nhất, và gồm cả bảng demo đang mở.
    idle = js.split('function isIdleForReload() {', 1)[1].split('}', 1)[0]
    assert "state === 'ready'" in idle
    assert 'demoIsOpen()' in idle

    # 3. ĐÚNG MỘT chỗ gọi reload, và nó đi qua cổng "rảnh" + cờ chống lặp.
    assert js.count('window.location.reload()') == 1, 'reload phải có đúng một lối vào'
    apply_fn = js.split('function applyPendingReload() {', 1)[1].split('\n  function ', 1)[0]
    assert 'isIdleForReload()' in apply_fn
    assert 'reloadPending' in apply_fn
    assert 'window.location.reload()' in apply_fn

    # 4. Bản mới thấy lúc đang bận phải được NHỚ, và được nạp đúng lúc quay về
    #    màn chờ -- không chờ thêm một vòng mạng nào (nhịp sau cách tới 30 giây,
    #    và mạng xưởng có thể rớt ngay sau lúc phát hiện).
    assert 'pendingVersion' in js
    show_fn = js.split('function show(name) {', 1)[1]
    assert 'applyPendingReload()' in show_fn.split('\n  function ', 1)[0]

    # 5. sendHeartbeat vẫn là nhịp đưa phiên bản máy chủ vào.
    hb = js.split('async function sendHeartbeat() {', 1)[1]
    assert 'reloadIfNewVersionAvailable(data.version)' in hb


def test_kiosk_documents_are_never_cached():
    """Cache-busting `?v=` chỉ có tác dụng nếu CHÍNH tài liệu HTML không bị
    cache -- nó là thứ mang các con trỏ đó. Trang kiosk từng trả về không kèm
    header cache nào, tức phó mặc cho phép đoán của trình duyệt/proxy."""
    source = (ROOT / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')
    assert 'def _never_cache(' in source
    assert "'Cache-Control'" in source and 'no-store' in source
    for fn_name in ('def kiosk_page():', 'def kiosk_mobile_page():', 'def kiosk_health():'):
        fn = source.split(fn_name, 1)[1].split('\n@bp.', 1)[0]
        assert '_never_cache(' in fn, fn_name
