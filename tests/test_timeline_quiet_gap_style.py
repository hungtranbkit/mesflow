"""Timeline ngày công: thời gian KHÔNG làm việc chỉ có một diện mạo, và màu
thanh việc do công đoạn quyết định chứ không do vị trí.

Bối cảnh (hotfix): dải timeline nhân viên vẽ bốn thứ khác nhau chồng lên nhau
-- thanh việc thật, khoảng hở giữa hai session, giờ nghỉ giữa ca, và phần ngoài
ca. Ba thứ sau đều có nghĩa "lúc đó không ai làm gì", nhưng mỗi thứ lại có công
thức nền riêng, và hai trong số đó là vàng cam sọc (#f3b94f / #e27e40) rực hơn
cả thanh việc thật nằm ngay cạnh. Mắt đọc "đang làm gì đó" ở đúng chỗ KHÔNG ai
làm gì -- đó là đọc ngược dữ liệu, không phải chuyện thẩm mỹ.

Cùng lúc đó thanh việc lấy màu bằng palette[i % 6], tức màu của VỊ TRÍ trong
vòng lặp. Cùng một OP đổi màu khi người khác làm nó ở thứ tự khác, và hai OP
khác nhau trùng màu ngay trong một hàng. Người dùng timeline lại đọc màu đúng
như một mã công đoạn, nên màu theo vị trí trả lời sai câu hỏi họ đang hỏi.

Bài test này là bài test NGUỒN: nó khoá cấu trúc file (một nguồn duy nhất cho
nền "không làm việc", khoá màu theo danh tính công đoạn). Diện mạo thật -- nền
ba loại bằng nhau từng pixel, cùng OP cùng tông qua nhiều hàng -- do
tests/e2e/dashboard-employee-timeline.spec.js đo trên trình duyệt thật.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.static

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_CSS = ROOT / 'app/mesflow/web/static/ui.css'
APP_JS = ROOT / 'app/mesflow/web/static/app.js'

# Mọi thứ trên timeline không phải việc thật.
QUIET_SELECTORS = {
    '.employee-gap',    # khoảng hở giữa hai session
    '.shift-off',       # trước giờ vào ca / sau giờ hết ca
    '.shift-lunch',     # giờ nghỉ giữa ca
    '.legend-gap',      # ...và ba ô chú giải giải thích chính chúng
    '.legend-lunch',
    '.legend-off',
}

QUIET_TOKENS = (
    '--timeline-quiet-fill',
    '--timeline-quiet-stripe',
    '--timeline-quiet-border',
    '--timeline-quiet-border-strong',
    '--timeline-quiet-text',
)

# Những màu đã nghỉ hưu: vàng/cam của khoảng hở ngắn và khoảng hở dài, cùng
# viền của chúng. Để sót một cái là để sót đúng cái đang gây hiểu nhầm.
RETIRED_COLORS = (
    '#f3b94f', '#fff3cf', '#e1a72f',           # khoảng hở -- vàng
    'rgba(243,185,79', 'rgba(255,243,207',
    '#e27e40', '#d46f31', '#d46f31',           # khoảng hở dài -- cam
    'rgba(226,126,64', 'rgba(255,226,207',
    'rgba(210,148,29',                         # viền khoảng hở
)


def _css() -> str:
    return UI_CSS.read_text(encoding='utf-8')


def _css_body() -> str:
    """ui.css đã bỏ chú thích.

    Chú thích ở đây cố ý nêu đích danh những màu đã nghỉ hưu (đó là điểm của
    chú thích), nên kiểm màu trên văn bản thô sẽ tự bắt chính lời giải thích.
    Bỏ chú thích cũng làm phần selector sạch: nếu không, cả khối chú thích
    đứng trước rule bị hút vào chuỗi selector.
    """
    return re.sub(r'/\*.*?\*/', '', _css(), flags=re.S)


def _js() -> str:
    return APP_JS.read_text(encoding='utf-8')


def _rules(text: str):
    """[(selector, thân rule)] cho mọi rule phẳng của file.

    ui.css phần lớn là một dòng minified, nên tách theo dấu ngoặc chứ không
    theo dòng. Rule lồng trong @media bị bỏ qua -- không rule nào ở đây cần.
    """
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r'([^{}@]+)\{([^{}]*)\}', text)]


def _hex_to_rgb(value: str):
    value = value.lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def test_one_rule_is_the_single_source_of_the_quiet_background():
    """Đúng MỘT rule đặt nền "không làm việc", và nó phủ đủ cả sáu selector."""
    css = _css_body()
    declaring = [sel for sel, body in _rules(css)
                 if re.search(r'background\s*:\s*var\(--timeline-quiet-pattern\)', body)]
    assert len(declaring) == 1, (
        f'{len(declaring)} rule cùng đặt nền timeline yên: {declaring}. '
        'Giữ đúng một nguồn, đừng mở nguồn thứ hai.')

    covered = {part.strip() for part in declaring[0].split(',')}
    missing = QUIET_SELECTORS - covered
    assert not missing, f'còn thiếu trong nguồn chung: {sorted(missing)}'


def test_no_quiet_element_keeps_a_background_of_its_own():
    """Không selector nào trong nhóm được tự đặt background lần nữa.

    Kể cả một background xám "vô hại" cũng đủ làm ba loại lệch nhau trở lại --
    đó chính là cách bốn công thức cũ sinh ra.
    """
    def touches_quiet(selector):
        # Cả biến thể cũng tính: .employee-gap.long từng là chỗ màu cam lẻn về.
        return any(part.strip() == quiet or part.strip().startswith(quiet + '.')
                   or part.strip().endswith(' ' + quiet)
                   for part in selector.split(',') for quiet in QUIET_SELECTORS)

    offenders = []
    for sel, body in _rules(_css_body()):
        if not touches_quiet(sel):
            continue
        if 'var(--timeline-quiet-pattern)' in body:
            continue
        if re.search(r'(^|;)\s*background(-color|-image)?\s*:', body):
            offenders.append(f'{sel} {{{body}}}')
    assert not offenders, 'nền riêng còn sót:\n  ' + '\n  '.join(offenders)


@pytest.mark.parametrize('token', QUIET_TOKENS)
def test_quiet_tokens_are_actually_neutral_not_warm(token):
    """"Yên" phải đo được: xám/xám-lam, không ngả vàng cam.

    Hai điều kiện: độ bão hoà thấp, và không ấm (kênh lam không thấp hơn kênh
    đỏ). #f3b94f trượt cả hai; #eef1f4 và #5b6773 qua cả hai.
    """
    match = re.search(rf'{token}\s*:\s*([^;}}]+)', _css_body())
    assert match, f'{token} chưa được khai báo'
    value = match.group(1).strip()
    red, green, blue = _hex_to_rgb(value)
    saturation = 0 if max(red, green, blue) == 0 else (
        (max(red, green, blue) - min(red, green, blue)) / max(red, green, blue))
    assert saturation <= 0.25, f'{token}={value} bão hoà {saturation:.0%}, không còn là màu yên'
    assert blue >= red, f'{token}={value} ngả ấm (lam {blue} < đỏ {red})'


@pytest.mark.parametrize('color', sorted(set(RETIRED_COLORS)))
def test_retired_task_like_gap_colors_are_gone(color):
    assert color not in _css_body(), f'{color} vẫn còn -- đây là màu khoảng hở đã bỏ'


def test_quiet_tokens_live_in_the_one_root_block():
    """Token mới phải vào khối :root duy nhất, không mở khối thứ bảy.

    test_ui_design_tokens_single_source.py canh luật chung; ở đây chỉ chốt
    rằng nhóm token này tuân theo nó.
    """
    css = _css()
    first_root = css.index(':root{', css.index('TOKEN DUY NHẤT'))
    depth, index = 1, first_root + len(':root{')
    while index < len(css) and depth:
        depth += (css[index] == '{') - (css[index] == '}')
        index += 1
    block = css[first_root:index]
    for token in (*QUIET_TOKENS, '--timeline-quiet-pattern'):
        assert f'{token}:' in block, f'{token} nằm ngoài khối token duy nhất'
        assert css.count(f'{token}:') == 1, f'{token} khai báo nhiều lần'


def test_task_bars_stay_solid_and_distinct_from_the_quiet_background():
    """Thanh việc thật vẫn là màu ĐẶC -- đó là thứ duy nhất được nổi bật."""
    css = _css_body()
    tones = re.findall(r'\.employee-session-segment\.tone-\d\{background:(#[0-9a-f]{6})\}', css)
    assert len(tones) == 6, f'kỳ vọng 6 tông đặc, thấy {tones}'
    assert len(set(tones)) == 6, f'hai tông trùng nhau: {tones}'
    for tone in tones:
        red, green, blue = _hex_to_rgb(tone)
        # Đặc và đủ tối để chữ trắng trên thanh đọc được -- ngược hẳn với nền yên.
        assert max(red, green, blue) < 210, f'{tone} quá nhạt cho một thanh việc'


def test_segment_tone_comes_from_the_operation_not_the_loop_index():
    js = _js()
    assert 'palette[i%palette.length]' not in js, 'màu theo vị trí vẫn còn'
    assert "const palette=['p1'" not in js, 'palette theo vị trí vẫn còn'
    assert 'timelineToneClass(x)' in js, 'thanh việc chưa lấy tông từ nguồn chung'

    body = js[js.index('function timelineToneKey'):js.index('function timelineToneClass')]
    for field in ('operation_id', 'operation_code', 'operation_name'):
        assert field in body, f'khoá tông không đọc {field}'

    # Chỉ số vòng lặp vẫn còn -- nó xếp tầng cho phiên chồng giờ (lanes[i]),
    # một việc chỉ vị trí mới trả lời được. Điều phải chốt là nó không quay
    # lại quyết định MÀU: biểu thức sinh lớp tone- không được nhắc tới i.
    render = js[js.index('return ordered.map('):]
    render = render[:render.index('employee-session-segment')]
    assert 'lanes[i]' in render, 'chỉ số đang ở đây vì việc xếp tầng -- đã mất việc đó?'
    marker = 'employee-session-segment ${'
    tone_expression = js[js.index(marker) + len(marker):]
    tone_expression = tone_expression[:tone_expression.index('}')]
    assert tone_expression == 'timelineToneClass(x)', (
        f'tông không còn đến từ nguồn chung: {tone_expression!r}')


def test_tone_mapping_has_exactly_one_home():
    """Một bảng tông, một hàm. Bản sao thứ hai là chỗ hai màn hình trôi ra xa nhau."""
    js = _js()
    assert js.count('const TIMELINE_TONES=') == 1
    assert js.count('function timelineToneClass') == 1
    static_dir = ROOT / 'app/mesflow/web/static'
    others = [path for path in static_dir.rglob('*.js')
              if path != APP_JS and 'TIMELINE_TONES' in path.read_text(encoding='utf-8')]
    assert not others, f'bảng tông bị chép sang: {[p.name for p in others]}'
