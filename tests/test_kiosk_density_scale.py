"""Thang mật độ của Kiosk điều hành nằm ở MỘT chỗ — REQ-KIOSK-012.

Bài Playwright `tests/e2e/kiosk-density-contract.spec.js` canh KẾT QUẢ (bao
nhiêu task/sự kiện thấy được, có hàng nào bị cắt không). Bài này canh CẤU TRÚC —
thứ mà một phép đo trên màn hình không bao giờ bắt được: mật độ vẫn có thể đạt
chỉ tiêu trong khi các con số quyết định nó lại nằm rải ở bốn khối rule khác
nhau, và lần sửa sau lại bỏ sót một khối.

Đó không phải lo xa: trước bản này, cỡ chữ tên Operation được khai ở ba chỗ
(`.kiosk-task-main b`, khối `@media(min-width:1800px)`, khối
`@media(max-width:1500px)`), padding hàng task ở hai chỗ, và chiều cao biểu đồ ở
ba chỗ. `ui.css` của repo này là năm lớp "chuẩn hoá thiết kế" nối đuôi nhau nên
giá trị đọc được trong một rule thường KHÔNG phải giá trị đang chạy.

PHẢN CHỨNG cho từng bài (thứ mà xoá đi sẽ làm nó đỏ):

  * test_density_tokens_live_in_one_block
        -> đỏ nếu khối token `--kd-*` bị xoá hoặc bị tách ra nhiều nơi.
  * test_media_queries_only_retune_tokens
        -> đỏ ngay khi ai đó lại khai `font-size`/`padding` bằng px cứng cho
           một phần tử Kiosk bên trong media query, thay vì đổi giá trị token.
  * test_js_reads_the_same_scale
        -> đỏ nếu JS quay lại chốt cứng số hàng panel phụ, tức bố cục và số
           hàng vẽ ra có thể lệch nhau mà không ai biết.
  * test_hourly_bars_have_a_paint_rule
        -> đỏ nếu luật vẽ cột biểu đồ bị bỏ lần nữa. Bản trước KHÔNG có luật
           cho cấu trúc mà `paintHourly` thật sự dựng, nên panel chiếm 272px ở
           1920 mà mọi cột đo ra width:0/height:0 — và không bài test nào đỏ.
  * test_sr_only_is_defined
        -> đỏ nếu `.sr-only` lại mất định nghĩa: hai nhãn dành cho trình đọc
           màn hình sẽ hiện ra như chữ thường, một trong hai nằm giữa header
           Kiosk vốn phải vừa đúng một hàng.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_CSS = ROOT / 'app/mesflow/web/static/ui.css'
PAGE = ROOT / 'app/mesflow/web/static/pages/daily-dashboard-kiosk.js'

# Những token phải tồn tại vì có ít nhất một rule (hoặc JS) đọc chúng.
REQUIRED_TOKENS = [
    '--kd-pad-screen', '--kd-gap', '--kd-pad-panel', '--kd-pad-head', '--kd-head-pb',
    '--kd-row-py', '--kd-row-px', '--kd-row-gap', '--kd-lh',
    '--kd-fs-panel', '--kd-fs-title', '--kd-fs-meta', '--kd-fs-kpi', '--kd-fs-kpi-label',
    '--kd-fs-event', '--kd-fs-event-meta', '--kd-fs-brand', '--kd-fs-headline',
    '--kd-fs-clock', '--kd-fs-label', '--kd-chart-h',
    '--kd-attn-rows', '--kd-other-rows', '--kd-feed-max',
]


def _css() -> str:
    return UI_CSS.read_text(encoding='utf-8')


def _strip_comments(text: str) -> str:
    """Xoá comment nhưng GIỮ NGUYÊN số dòng/độ dài, để vị trí còn dùng được."""
    return re.sub(r'/\*.*?\*/', lambda m: ' ' * len(m.group(0)), text, flags=re.S)


def test_density_tokens_live_in_one_block():
    """Mọi token `--kd-*` được ĐỊNH NGHĨA trong các khối `.kiosk-display`, không rải rác."""
    css = _strip_comments(_css())
    defined: dict[str, int] = {}
    for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        selector, body = match.group(1).strip(), match.group(2)
        for token in re.findall(r'(--kd-[a-z0-9-]+)\s*:', body):
            assert selector.endswith('.kiosk-display'), (
                f'{token} được khai ở `{selector[:80]}` — thang mật độ chỉ được khai '
                f'trên .kiosk-display'
            )
            defined[token] = defined.get(token, 0) + 1

    missing = [t for t in REQUIRED_TOKENS if t not in defined]
    assert not missing, f'thiếu token mật độ: {missing}'

    # Mỗi token phải được BẬC MẶC ĐỊNH khai (khối `.kiosk-display` không nằm
    # trong media query) — nếu không, một bề rộng không khớp media query nào sẽ
    # rơi vào giá trị rỗng và rule đọc nó im lặng mất hiệu lực.
    base = re.search(r'\.kiosk-display\{([^{}]*)\}', css)
    assert base, 'không tìm thấy khối token mặc định của .kiosk-display'
    base_tokens = set(re.findall(r'(--kd-[a-z0-9-]+)\s*:', base.group(1)))
    # khối đầu tiên là khối màu (--k-*); gom tất cả khối .kiosk-display ngoài media.
    for m in re.finditer(r'(?<![-\w])\.kiosk-display\s*\{([^{}]*)\}', css):
        base_tokens |= set(re.findall(r'(--kd-[a-z0-9-]+)\s*:', m.group(1)))
    unbased = [t for t in REQUIRED_TOKENS if t not in base_tokens]
    assert not unbased, f'token chỉ có trong media query, thiếu giá trị mặc định: {unbased}'


def test_no_token_is_declared_but_never_read():
    """Token khai ra mà không ai đọc là một GIÁ TRỊ CHẾT.

    `ui.css` của repo này đã có tiền lệ: giá trị đọc được trong file không phải
    giá trị đang chạy. Một token không ai đọc là đúng cái bẫy đó ở dạng mới —
    người sau sẽ chỉnh nó rồi tưởng màn hình đã đổi.
    """
    css = _css()
    js = PAGE.read_text(encoding='utf-8')
    declared = set(re.findall(r'(--kd-[a-z0-9-]+)\s*:', _strip_comments(css)))
    for token in sorted(declared):
        read_in_css = f'var({token})' in css
        read_in_js = f"'{token}'" in js
        assert read_in_css or read_in_js, f'{token} được khai nhưng không ai đọc'


def _live_classes() -> set[str]:
    """Các class mà trang THẬT SỰ dựng ra, đọc từ chính source của trang.

    Cần phân biệt vì `ui.css` còn nguyên khối rule của Kiosk bản v0 (bảng
    Operation `.kiosk-tr`/`.kiosk-op`, ba panel nhỏ `.kiosk-mini-panel`,
    `.kiosk-alert`, `.kiosk-list`, chú giải biểu đồ `.kiosk-chart-legend`) mà
    `renderDailyDashboardKiosk` không còn dựng phần tử nào mang class đó. Bắt
    khối chết đó theo thang mật độ là bắt nhầm chỗ; dọn nó là một việc khác,
    có rủi ro riêng, không thuộc REQ-KIOSK-012.

    Đọc từ source thay vì liệt kê tay để danh sách tự đúng khi trang đổi markup.
    """
    js = PAGE.read_text(encoding='utf-8')
    names: set[str] = set()
    for attr in re.findall(r'class="([^"]*)"', js):
        for name in re.split(r'[\s${}`]+', attr):
            if name.startswith('kiosk-'):
                names.add(name)
    assert 'kiosk-task' in names and 'kiosk-event' in names, 'không đọc được class của trang'
    return names


def test_media_queries_only_retune_tokens():
    """Media query của Kiosk đổi GIÁ TRỊ TOKEN, không khai lại px cho từng phần tử.

    Chỉ xét những rule chạm class mà trang thật sự dựng (xem `_live_classes`).

    Ngoại lệ được phép và có lý do: BỐ CỤC (grid-template-*, flex, display, bề
    rộng cột, `max-width` của hộp chọn PO) vốn không phải một đại lượng của thang
    mật độ — thang mật độ nói "dày bao nhiêu", bố cục nói "xếp ra sao".
    """
    # Mốc cắt phải là RULE, không phải comment: `_strip_comments` xoá comment
    # nên mọi mốc dạng comment biến mất cùng nó.
    css = _strip_comments(_css())
    start = css.index('.kiosk-display{')
    end = css.index('.daily-po-picker{')
    assert start < end
    region = css[start:end]
    live = _live_classes()

    offenders = []
    for block in re.finditer(r'@media\(([^)]*)\)\s*\{', region):
        # cắt đúng thân của media query bằng cách đếm ngoặc
        i = block.end() - 1
        depth, j = 0, i
        while j < len(region):
            if region[j] == '{':
                depth += 1
            elif region[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = region[i + 1:j]
        for rule in re.finditer(r'([^{}]+)\{([^{}]*)\}', body):
            selector, decls = rule.group(1).strip(), rule.group(2)
            if selector.endswith('.kiosk-display'):
                continue                       # đây chính là chỗ đổi token
            touched = {c for c in re.findall(r'\.(kiosk-[a-z0-9-]+)', selector)}
            if not (touched & live):
                continue                       # rule của bản v0, không còn ai dựng
            if 'po-pick select' in selector:
                continue                       # cỡ/đệm của ô chọn là bố cục header
            for prop in ('font-size', 'line-height'):
                for decl in re.findall(rf'{prop}\s*:\s*([^;]+)', decls):
                    if 'var(--kd-' in decl:
                        continue
                    offenders.append(f'{block.group(1)} › {selector[:70]} › {prop}:{decl.strip()}')
    assert not offenders, (
        'media query của Kiosk khai lại cỡ chữ bằng px thay vì đổi token:\n  '
        + '\n  '.join(offenders)
    )


def test_js_reads_the_same_scale():
    """Số hàng panel phụ đến từ token CSS, không phải hằng số chốt trong JS."""
    js = PAGE.read_text(encoding='utf-8')
    assert 'function density(' in js, 'thiếu primitive đọc token mật độ'
    for token in ('--kd-attn-rows', '--kd-other-rows', '--kd-feed-max'):
        assert f"'{token}'" in js, f'JS không đọc {token}'
    # Và số hàng vẽ ra phải được ĐO lại trên khung thật, vì hàng sự kiện không
    # cao cố định (câu dài thì xuống dòng).
    assert 'function fitDown(' in js
    assert 'function fitRows(' in js


def test_hourly_bars_have_a_paint_rule():
    """Cấu trúc mà paintHourly() THẬT SỰ dựng phải có luật vẽ.

    paintHourly dựng `<div class="kiosk-bar"><span…><i style="height:N%"><small…>`.
    Trước bản này CSS chỉ có `.kiosk-bar-stack i` — một cấu trúc không còn ai
    dựng — nên mọi cột đo ra width:0/height:0, nền trong suốt.
    """
    css = _css()
    js = PAGE.read_text(encoding='utf-8')
    # markup thật vẫn là `<i style="height:...">` nằm thẳng trong .kiosk-bar
    assert re.search(r'<i style="height:\$\{[^}]+\}%"></i>', js), \
        'markup cột biểu đồ đã đổi — cập nhật cả luật CSS lẫn bài test này'
    assert '.kiosk-bar>i{' in css, 'không có luật vẽ cho cột biểu đồ'
    rule = css[css.index('.kiosk-bar>i{'):]
    rule = rule[:rule.index('}')]
    assert 'background:' in rule and 'width:100%' in rule


def test_sr_only_is_defined():
    """`.sr-only` được dùng thì phải được định nghĩa."""
    css = _css()
    js = PAGE.read_text(encoding='utf-8')
    assert 'class="sr-only"' in js
    assert '.sr-only{' in css, '.sr-only được dùng nhưng không stylesheet nào định nghĩa'
    rule = css[css.index('.sr-only{'):]
    rule = rule[:rule.index('}')]
    assert 'position:absolute' in rule and 'clip-path' in rule


def test_the_scale_names_its_requirement():
    """Khối token nói rõ nó thuộc requirement nào.

    (Bài kiểm EN/VI của chính REQ-KIOSK-012 không nằm ở đây được: `docs/` không
    được COPY vào image test — xem Dockerfile.test — nên một bài đọc file
    requirement sẽ đỏ vì FileNotFoundError chứ không vì tài liệu sai.)
    """
    assert 'REQ-KIOSK-012' in _css()
    assert 'REQ-KIOSK-012' in PAGE.read_text(encoding='utf-8')
