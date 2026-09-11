"""Contract for "Kiosk điều hành" — the control-room display opened from
Dashboard theo ngày.

NEGATIVE PROOF (what makes this a real regression test, not decoration):
each test below names the single thing whose removal turns it red.

  * test_kiosk_route_is_registered_and_reachable
        -> red if the page module, its <script> tag, or its registerPage()
           call is dropped: the route becomes unreachable and deep-linking
           ?page=daily-dashboard-kiosk renders a blank screen.
  * test_dashboard_exposes_the_open_button_carrying_the_date
        -> red if the "Mở màn hình lớn" button or its date-carrying handler
           is removed from Dashboard theo ngày.
  * test_kiosk_layout_css_exists
        -> red if the kiosk's CSS block (dark full-bleed shell, KPI grid,
           two-column body, 1366 breakpoint) is deleted, which is exactly
           the failure mode "it still renders, but it is not a TV layout
           any more and it overflows".
  * test_kiosk_adds_no_new_endpoint
        -> red if someone bolts a new aggregate API onto this view instead
           of reusing the shipped ones.
  * test_kiosk_is_not_a_device_kiosk
        -> red if this control-room display starts pulling in the
           shop-floor badge-scan kiosk runtime.
  * test_kiosk_controls_share_one_token_surface
        -> red if the kiosk's control tokens (--k-control-*) or
           `color-scheme:dark` are dropped from the .kiosk-display block, or
           if a kiosk button/select goes back to a hardcoded hex. Those tokens
           are what keeps the PO selector and its two buttons on ONE dark
           surface.
  * test_kiosk_po_select_outranks_the_light_shell_surface
        -> red if the `!important` on the PO select's background is dropped.
           That is not stylistic: the shared "Industrial Soft-3D" layer sets
           `background:#fff!important` on EVERY select in the app, so without
           it the kiosk selector renders white with light text -- 1.16:1
           measured, i.e. unreadable. The measured counterpart is
           tests/e2e/kiosk-control-contrast.spec.js.
  * test_sr_only_label_is_actually_hidden
        -> red if the `.sr-only` rule is dropped again. It was MISSING
           entirely: both call sites painted their screen-reader label as
           ordinary text, and on the kiosk's dark header that label sat at
           ~2.2:1.
"""
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/'app/mesflow/web/static/pages/daily-dashboard-kiosk.js'
APP_JS=ROOT/'app/mesflow/web/static/app.js'
APP_HTML=ROOT/'app/mesflow/web/templates/app.html'
UI_CSS=ROOT/'app/mesflow/web/static/ui.css'
ROUTES=ROOT/'app/mesflow/web/analytics.py'


def test_kiosk_route_is_registered_and_reachable():
    assert PAGE.exists()
    page=PAGE.read_text(encoding='utf-8')
    html=APP_HTML.read_text(encoding='utf-8')
    app=APP_JS.read_text(encoding='utf-8')
    # Self-registration through the shared hook -- not a monkey-patch of openPage.
    assert "window.registerPage(PAGE_ID,renderDailyDashboardKiosk)" in page
    assert "const PAGE_ID='daily-dashboard-kiosk'" in page
    # Loaded by the shell, and AFTER app.js (which defines window.registerPage).
    assert '/static/pages/daily-dashboard-kiosk.js' in html
    assert html.index('/static/app.js')<html.index('/static/pages/daily-dashboard-kiosk.js')
    # Gated by the same permission as the dashboard it belongs to.
    assert "'daily-dashboard-kiosk':'dashboard.view'" in app
    # date= is read from the URL, validated, and written back so refresh /
    # deep-link / Back / Forward all restore the same day.
    assert "const date=validDate(query.get('date'))?query.get('date'):hcmToday()" in page
    assert "AppNav.setQuery({date})" in page
    # body[data-page] is what app.js's popstate handler compares against; the
    # kiosk must claim it or Back/Forward stops working for this screen.
    assert "document.body.dataset.page=PAGE_ID" in page


def test_dashboard_exposes_the_open_button_carrying_the_date():
    app=APP_JS.read_text(encoding='utf-8')
    assert 'id="dailyOpenKiosk"' in app
    assert 'Mở màn hình lớn' in app
    assert "document.getElementById('dailyOpenKiosk').onclick" in app
    # The selected working day must travel with the click, and exactly one
    # history entry may be pushed (page= and date= together) so a single Back
    # press returns to the dashboard.
    assert "url.searchParams.set('page','daily-dashboard-kiosk')" in app
    # Từ REQ-DASH-006, cú bấm mang theo CẢ ngày lẫn PO: Kiosk v1 chỉ có nghĩa
    # khi biết đang xem PO nào.
    assert "url.searchParams.set('date',document.getElementById('dailyDate').value)" in app
    assert "url.searchParams.set('po_id',String(poId))" in app
    assert "openPage('daily-dashboard-kiosk',null,{historyMode:'none'})" in app
    # Đang "Tất cả PO" thì HỎI, không đoán -- đoán là đẩy lên màn hình lớn một
    # đơn hàng người dùng không hề chọn.
    assert 'askKioskPo' in app and 'kiosk-pick-modal' in app


def test_kiosk_layout_css_exists():
    css=UI_CSS.read_text(encoding='utf-8')
    # Scoped dark full-bleed shell: without this the page renders inside the
    # light admin chrome and is unreadable from across a workshop.
    assert 'body[data-page="daily-dashboard-kiosk"]' in css
    assert '.kiosk-display{' in css
    # The three structural blocks the TV layout depends on.
    assert '.kiosk-kpis{display:grid' in css
    assert '.kiosk-body{display:grid' in css
    assert '.kiosk-chart-plot{' in css
    # Operation NAME is the headline, code is the secondary line.
    assert '.kiosk-op b{' in css and '.kiosk-op small{' in css
    # 1366x768 must be an explicit step, not an accident.
    assert '@media(max-width:1500px)' in css


def test_kiosk_uses_only_its_two_read_only_endpoints():
    """Kiosk đọc đúng hai endpoint chỉ-đọc của nó, và không gì khác.

    Bản trước của bài test này khẳng định "kiosk KHÔNG thêm endpoint nào" -- nó
    dùng thẳng /api/dashboard/day + overview + production-control rồi lọc ở
    trình duyệt. Điều đó không còn đúng được nữa sau REQ-KIOSK-010: phạm vi một
    PO phải nằm trong truy vấn, mà ba endpoint kia không nhận phạm vi đó. Hai
    endpoint mới là chỉ-đọc và gọi lại chính repository sẵn có, nên phần "không
    viết lại quy tắc nghiệp vụ" vẫn giữ nguyên -- đó mới là điều bài test này
    thật sự canh.
    """
    page=PAGE.read_text(encoding='utf-8')
    board=(ROUTES.parent/'kiosk_board.py').read_text(encoding='utf-8')
    assert '/api/kiosk-board?' in page
    assert '/api/kiosk-board/activity?' in page
    assert "@bp.get('/kiosk-board')" in board
    assert "@bp.get('/kiosk-board/activity')" in board
    # Chỉ đọc: không có đường ghi nào trong blueprint của màn hình lớn.
    for write in ("@bp.post", "@bp.patch", "@bp.put", "@bp.delete"):
        assert write not in board, f'màn hình lớn không được có đường ghi: {write}'
    # Không tự viết lại quy tắc: dữ liệu đến từ repository sẵn có.
    assert 'DashboardRepository' in board
    # Vẫn không có route "gom sẵn cho một màn hình" nào chui vào analytics.
    routes=ROUTES.read_text(encoding='utf-8')
    assert 'kiosk-display' not in routes
    assert "@bp.get('/dashboard/kiosk" not in routes


def _code_only(source:str)->str:
    """Strip whole-line // comments.

    The page's own header comment deliberately NAMES the shop-floor kiosk
    modules to explain what this view is not; only executable code may be
    searched for references to them.
    """
    return '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('//'))


def test_kiosk_is_not_a_device_kiosk():
    """Control-room display, not the shop-floor badge-scan terminal."""
    page=_code_only(PAGE.read_text(encoding='utf-8'))
    for forbidden in ('/api/kiosk/','/api/kiosk-v2/','/station/heartbeat','device_uuid','templates/kiosk.html'):
        assert forbidden not in page, forbidden
    # Date is the only filter: ca is metadata, never a query parameter.
    assert 'shift_id=' not in page
    assert '&shift=' not in page


def test_kiosk_does_not_fabricate_an_hourly_plan():
    """Mô hình dữ liệu không có kế hoạch theo giờ, nên màn hình không được vẽ ra một đường mục tiêu tưởng tượng.

    Bản trước kiểm bằng cách đòi có câu "Chưa cấu hình kế hoạch theo giờ". Bản
    hiện tại không nói câu đó vì nó không còn vẽ khung kế hoạch nào để mà chú
    thích -- cột giờ chỉ là sản lượng THẬT đã ghi nhận. Nên bài test chuyển sang
    khẳng định điều đáng canh hơn: không có chữ "kế hoạch/mục tiêu" nào gắn vào
    biểu đồ giờ.
    """
    page=PAGE.read_text(encoding='utf-8')
    assert 'paintHourly' in page
    for invented in ('plan_per_hour', 'hourly_plan', 'target_per_hour', 'kế hoạch/giờ'):
        assert invented not in page, f'biểu đồ giờ bịa ra kế hoạch: {invented}'
    # Phần nguồn dữ liệu còn thiếu vẫn phải được nói ra, không im lặng bỏ qua.
    assert 'chưa có nguồn dữ liệu' in page


def test_kiosk_keeps_last_good_data_on_api_failure():
    """A control-room display must never go blank on a transient API error."""
    page=PAGE.read_text(encoding='utf-8')
    assert "setLive('stale'" in page
    assert 'Mất kết nối' in page
    # The paint* helpers are only called on the success path, so a failed poll
    # leaves the previous screen untouched.
    assert 'if(!alive())return;' in page


# --------------------------------------------------------------- vùng điều khiển
# Bề mặt điều khiển của kiosk (select chọn PO + nút "Làm mới"/"Thoát"). Phần đo
# THẬT nằm ở tests/e2e/kiosk-control-contrast.spec.js -- computed style là chỗ
# duy nhất nói được màu đang chạy, vì ui.css có nhiều lớp ghi đè nhau. Hai bài
# static dưới đây canh thứ mà e2e KHÔNG canh được: cấu trúc của bản sửa, tức là
# nó vẫn đi qua token và vẫn còn lý do tồn tại của `!important`.

KIOSK_CONTROL_TOKENS=(
    '--k-control-bg', '--k-control-bg-hover',
    '--k-control-text', '--k-control-text-hover',
    '--k-control-line', '--k-control-line-hover', '--k-control-focus',
    '--k-control-bg-disabled', '--k-control-text-disabled',
)


def _rule(css:str, selector:str)->str:
    """Thân của MỘT rule CSS, ĐÃ BỎ COMMENT, tìm theo selector nguyên văn.

    Bỏ comment là phần bắt buộc, không phải dọn dẹp: khối .kiosk-display có một
    comment nhắc chính chữ `color-scheme:dark`, nên nếu không bỏ thì bài test
    dưới đây vẫn xanh khi CÂU LỆNH bị xoá và chỉ còn lời nhắc về nó -- test
    canh chú thích của chính mình. Cùng lý do cho phép kiểm "không còn hex".
    """
    start=css.index(selector+'{')+len(selector)+1
    return re.sub(r'/\*.*?\*/', ' ', css[start:css.index('}', start)], flags=re.S)


def test_kiosk_controls_share_one_token_surface():
    css=UI_CSS.read_text(encoding='utf-8')
    display=_rule(css, '.kiosk-display')
    for token in KIOSK_CONTROL_TOKENS:
        assert token+':' in display, f'thiếu token bề mặt điều khiển {token}'
    # color-scheme là thứ DUY NHẤT tác động được vào popup <option> native, mũi
    # tên select và thanh cuộn -- CSS của trang không vẽ được mấy thứ đó. Thiếu
    # nó thì danh sách PO bung ra vẫn là popup SÁNG trên Chromium/Safari.
    assert 'color-scheme:dark' in display
    assert 'color-scheme:dark' in _rule(css, 'body[data-page="daily-dashboard-kiosk"]')

    # Nút và select cùng lấy MỘT bộ token, không ai giữ hex riêng nữa.
    for selector in ('.kiosk-btn', '.kiosk-btn:hover', '.kiosk-btn:disabled',
                     '.kiosk-display .kiosk-po-pick select',
                     '.kiosk-display .kiosk-po-pick select:hover',
                     '.kiosk-display .kiosk-po-pick select:disabled',
                     '.kiosk-display .kiosk-po-pick select option'):
        body=_rule(css, selector)
        assert 'var(--k-control-' in body, f'{selector} không dùng token điều khiển'
        assert '#' not in body, f'{selector} còn màu viết cứng: {body.strip()}'

    # Danh sách option do JS dựng; màu phải đến từ CSS token, không gắn vào
    # từng <option> (yêu cầu: "not per-option hardcoded colors").
    page=PAGE.read_text(encoding='utf-8')
    option_markup=page[page.index('function paintSelector'):]
    option_markup=option_markup[:option_markup.index('</select>')] if '</select>' in option_markup else option_markup[:1200]
    assert 'style=' not in option_markup, 'option của bộ chọn PO mang style inline'


def test_sr_only_label_is_actually_hidden():
    """`.sr-only` được DÙNG thì phải được ĐỊNH NGHĨA.

    Đỏ nếu luật .sr-only bị xoá: lúc đó nhãn `Chọn Production Order` trong bộ
    chọn PO của kiosk (và `Tìm Production Order` trong modal "Mở màn hình lớn")
    được VẼ RA thành chữ thường -- trên header tối của kiosk là ~2.2:1, đúng
    phần thứ hai của báo cáo "không đọc được chữ".
    """
    css=UI_CSS.read_text(encoding='utf-8')
    assert '.sr-only{' in css, '.sr-only được dùng trong markup nhưng không có luật CSS nào định nghĩa'
    body=_rule(css, '.sr-only')
    # Ẩn bằng clip, KHÔNG bằng display:none -- phải còn trong cây a11y.
    assert 'position:absolute' in body and 'clip-path:inset(50%)' in body
    assert 'display:none' not in body
    # Và chỗ dùng vẫn còn, nếu không thì luật này thành rác.
    assert 'class="sr-only">Chọn Production Order' in PAGE.read_text(encoding='utf-8')


def test_kiosk_po_select_outranks_the_light_shell_surface():
    css=UI_CSS.read_text(encoding='utf-8')
    # Điều kiện làm cho !important bên dưới là BẮT BUỘC chứ không phải thói
    # quen: lớp nền chung vẫn đang ép nền trắng lên MỌI select của ứng dụng.
    shared=_rule(css, 'input:not([type="checkbox"]):not([type="radio"]),select,textarea')
    assert 'background:#fff!important' in shared, (
        'lớp nền chung không còn ép nền trắng lên select -- nếu đúng là đã bỏ '
        'thật thì gỡ !important ở khối kiosk và sửa bài test này cùng lúc'
    )
    select=_rule(css, '.kiosk-display .kiosk-po-pick select')
    assert 'background:var(--k-control-bg)!important' in select
    # Cùng lớp đó đặt một inset shadow SÁNG (vệt trắng bên trong) bằng
    # !important; trên nền tối nó thành một vết bẩn, phải tắt hẳn.
    assert 'box-shadow:none!important' in select
    # Và luật :focus-visible chung dùng --action-primary của shell sáng.
    focus=_rule(css, '.kiosk-display .kiosk-po-pick select:focus,\n.kiosk-display .kiosk-po-pick select:focus-visible')
    assert 'outline:2px solid var(--k-control-focus)!important' in focus
