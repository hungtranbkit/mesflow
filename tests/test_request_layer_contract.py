"""Hợp đồng tĩnh của lớp gọi mạng dùng chung (core/net.js).

Bối cảnh: trước lớp này, mỗi màn tự gọi `fetch` rồi `catch(e){hiện e.message}`.
Khi mạng chớp tắt một nhịp, `fetch` reject bằng TypeError của trình duyệt và
`e.message` đúng bằng chuỗi "Failed to fetch" -- một câu tiếng Anh của trình
duyệt hiện giữa phần mềm tiếng Việt. Những bài dưới đây khoá lại các bất biến
mà việc sửa dựa vào, để một màn mới không lặng lẽ dựng lại đường cũ.

Tất cả đều là kiểm tra NGUỒN: không cần PostgreSQL, không cần trình duyệt.
Phần hành vi thật nằm ở tests/e2e/request-layer-unit.spec.js và
tests/e2e/network-resilience.spec.js.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app/mesflow/web/static'
TEMPLATES = ROOT / 'app/mesflow/web/templates'

pytestmark = pytest.mark.static


def read(rel: str) -> str:
    return (STATIC / rel).read_text(encoding='utf-8')


def test_shared_layer_exists_and_is_loaded_by_both_frontends():
    """Một lớp mạng, hai frontend. Kiosk KHÔNG được có bản sao riêng."""
    assert (STATIC / 'core/net.js').exists()
    app_html = (TEMPLATES / 'app.html').read_text(encoding='utf-8')
    kiosk_html = (TEMPLATES / 'kiosk.html').read_text(encoding='utf-8')
    for html in (app_html, kiosk_html):
        assert '/static/core/net.js' in html
    # Thứ tự nạp là một phần của hợp đồng: api()/kiosk.js gọi MFNet ngay khi
    # chạy, nên net.js phải có mặt trước.
    assert app_html.index('/static/core/net.js') < app_html.index('/static/core/api.js')
    assert kiosk_html.index('/static/core/net.js') < kiosk_html.index('/static/kiosk.js')


def test_api_wrapper_no_longer_calls_fetch_itself():
    api = read('core/api.js')
    assert 'fetch(' not in api
    assert 'MFNet.json(' in api
    kiosk = read('kiosk.js')
    assert 'MFNet.json(' in kiosk


def test_vietnamese_messages_are_defined_once_in_the_shared_layer():
    """Ba câu người dùng thấy khi hết lượt thử lại -- định nghĩa ở đúng một chỗ."""
    net = read('core/net.js')
    for message in ('Mất kết nối mạng',
                    'Kết nối chưa ổn định, vui lòng thử lại',
                    'Máy chủ tạm thời không phản hồi',
                    'Đang kết nối lại…'):
        assert net.count(f"'{message}'") == 1, message


def test_retry_status_list_is_transient_only():
    """400/401/403/404/409/422 là câu trả lời DỨT KHOÁT: thử lại mù là sai."""
    net = read('core/net.js')
    listed = re.search(r'const RETRY_STATUS=\[([^\]]*)\]', net)
    assert listed, 'RETRY_STATUS không còn là một literal đọc được'
    codes = {int(x) for x in listed.group(1).split(',') if x.strip()}
    assert codes == {408, 425, 429, 500, 502, 503, 504}
    for never in (400, 401, 403, 404, 409, 422):
        assert never not in codes


def test_only_get_and_head_retry_by_default():
    net = read('core/net.js')
    assert "const SAFE_METHODS=['GET','HEAD']" in net
    # Mutation chỉ được thử lại khi call site TỰ khai `idempotent:true`.
    assert 'const canRetry=safeMethod||idempotent;' in net
    assert "const idempotent=opt.idempotent===true;" in net


def test_idempotent_optin_is_limited_to_endpoints_that_carry_a_request_id():
    """`idempotent:true` là lời cam kết backend dedupe được -- không phải mặc định.

    Chỉ hai mutation của Kiosk web đủ điều kiện: chúng mang `request_id` và
    backend chặn trùng qua bảng kiosk_idempotency + pg_advisory_xact_lock.
    Nếu có màn nào thêm `idempotent:true` ở chỗ khác, bài này phải đỏ và người
    thêm phải chứng minh endpoint đó dedupe được.
    """
    optins = []
    for path in sorted(STATIC.rglob('*.js')):
        for line in path.read_text(encoding='utf-8').splitlines():
            if 'idempotent:true' in line:
                optins.append((path.relative_to(STATIC).as_posix(), line))
    assert len(optins) == 2, optins
    for rel, line in optins:
        assert rel == 'kiosk.js'
        assert '/api/kiosk-web/start' in line or '/api/kiosk-web/finish/' in line
        assert 'request_id' in line

    backend = (ROOT / 'app/mesflow/web/kiosk.py').read_text(encoding='utf-8')
    assert backend.count("'request_id'") >= 2
    repo = (ROOT / 'app/mesflow/db/repositories/production_state.py').read_text(encoding='utf-8')
    assert 'def lock_idempotency_key' in repo


def test_refresh_error_stays_on_the_mfui_export_line():
    """Khoá đúng dòng mà hai nhánh cùng sửa.

    `core/ui.js` kết thúc bằng MỘT dòng `return {…}` liệt kê mọi primitive của
    MFUI. hp3 (nhánh bo góc/progressive disclosure) chèn export của họ vào
    CÙNG dòng đó, nên git chắc chắn báo conflict ở đây và cách gỡ đúng là giữ
    cả hai danh sách. Nếu ai gỡ bằng cách "lấy dòng của một bên", `refreshError`
    có thể biến mất khỏi export trong khi hàm vẫn còn nguyên bên trên -- một
    thay đổi mà bài test_polling_screens_* ở dưới KHÔNG bắt được, vì nó chỉ
    kiểm hàm có tồn tại và call site có gọi.
    """
    ui = read('core/ui.js')
    # Dòng export của MFUI là dòng `return {…}` ở tầng IIFE -- neo vào
    # `statusBadge` (phần tử đầu, có từ trước mọi lane hiện tại) để không bắt
    # nhầm hai `return {…}` của openDrawer/openModal bên trong file.
    lines = [line for line in ui.splitlines()
             if line.strip().startswith('return {') and 'statusBadge' in line]
    assert len(lines) == 1, 'không tìm thấy đúng một dòng export MFUI trong core/ui.js'
    # Tách TÊN chứ không `in` cả dòng: `in` vẫn xanh nếu tên chỉ tình cờ là
    # khúc con của một tên khác. Và khi đỏ thì in ra cả danh sách đang export
    # -- người đang gỡ conflict cần thấy ngay phía nào bị lấy mất.
    inside = lines[0].strip()[len('return {'):].rsplit('}', 1)[0]
    exported = {name.split(':')[0].strip() for name in inside.split(',')}
    assert 'refreshError' in exported, (
        'refreshError rơi khỏi danh sách export của MFUI. Đang export: '
        + ', '.join(sorted(exported)))


def test_polling_screens_keep_stale_data_instead_of_rendering_the_error():
    """Màn tự làm mới không được xoá dữ liệu đang đọc vì một nhịp hỏng.

    Dashboard theo ngày làm mới mỗi 10s; Tổng quan / Điều hành PO / Tiến trình
    mỗi 15s. Trước đây mỗi nhịp hỏng ghi đè cả vùng nội dung bằng khối lỗi.
    """
    assert 'const refreshError=' in read('core/ui.js')
    for rel in ('app.js', 'pages/overview.js', 'pages/po-control.js'):
        assert 'MFUI.refreshError' in read(rel), rel
    # Dashboard theo ngày và Tiến trình sản xuất cùng nằm trong app.js.
    assert read('app.js').count('MFUI.refreshError') >= 4


def test_page_change_cancels_the_previous_screen_requests():
    """Phản hồi về muộn sau khi đã đổi màn chỉ có thể vẽ nhầm hoặc báo nhầm."""
    app = read('app.js')
    assert 'MFNet.abortGroup(leavingPage)' in app
    assert 'MFNet.clearReconnect()' in app
    assert "group:document.body.dataset.page||'app'" in read('core/api.js')


def test_no_screen_module_calls_fetch_directly():
    """Mọi lời gọi API đi qua lớp chung; ngoại lệ phải được liệt kê ở đây.

    Danh sách dưới là các trường hợp CỐ Ý đứng ngoài, mỗi cái một lý do:
      login.js      -- chạy trước khi app nạp, tự xử lý lỗi bằng tiếng Việt
      kiosk.js      -- heartbeat fire-and-forget (keepalive), không được retry
      core/net.js   -- chính là lớp đó
      app.js        -- ba lần upload multipart (FormData) + logout + manifest
      wallboard-*   -- màn TV đã tự giữ bản vẽ cuối + banner "đang thử lại"
      text-guide.js -- đọc file JSON tĩnh trong /static, không phải API
    """
    allowed = {
        'core/net.js': None,
        'login.js': 2,
        'kiosk.js': 1,
        'app.js': 5,
        'wallboard-employee-productivity.js': 2,
        'pages/text-guide.js': 1,
    }
    for path in sorted(STATIC.rglob('*.js')):
        rel = path.relative_to(STATIC).as_posix()
        count = len(re.findall(r'\bfetch\(', path.read_text(encoding='utf-8')))
        if not count:
            continue
        assert rel in allowed, f'{rel} gọi fetch() thẳng -- phải đi qua api()/MFNet'
        expected = allowed[rel]
        if expected is not None:
            assert count == expected, f'{rel}: {count} lời gọi fetch(), chờ {expected}'


def test_auth_expiry_cannot_loop_the_login_page():
    net = read('core/net.js')
    assert "if(path.startsWith('/login'))return;" in net
    assert 'if(authRedirecting)return;' in net
