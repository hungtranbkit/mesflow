"""Timeline ngày công: ba ý nghĩa, ba diện mạo, không cái nào mượn của cái nào.

Dải timeline vẽ ba loại thời gian chồng lên nhau, và người đọc phân biệt chúng
bằng mắt trước khi kịp rê chuột. Nên mỗi loại phải có đúng một diện mạo, và
diện mạo đó phải nói đúng việc cần làm:

  (A) THANH VIỆC THẬT  -- mảng đặc, màu theo DANH TÍNH công đoạn.
  (B) NGHỈ THEO LỊCH   -- ngoài ca, nghỉ giữa ca. Xám lạnh, yên, không nhắc ai:
                          không ai phải làm gì với nó.
  (C) TRỐNG VIỆC TRONG CA -- đang giờ làm mà không việc nào chạy. Vàng rất nhạt
                          + viền đứt: đây là việc của quản lý nên nó ĐƯỢC nhắc,
                          nhưng không bao giờ bằng mảng đặc -- mảng đặc là ngôn
                          ngữ của (A), mượn nó là nói dối rằng có người đang làm.

Hai lỗi lịch sử bài test này khoá lại:

  * (C) từng là vàng cam sọc rực (#f3b94f) và (B) có tới ba công thức nền khác
    nhau -- nên chỗ KHÔNG ai làm gì lại bắt mắt hơn chỗ có người đang làm.
  * (A) lấy màu bằng palette[i % 6]: màu của VỊ TRÍ chứ không của công đoạn.
    Cùng một OP đổi màu khi người khác làm nó ở thứ tự khác; hai OP khác nhau
    trùng màu ngay trong một hàng dù bảng màu vẫn còn chỗ trống. Thêm nữa mã OP
    lặp lại được giữa các Part, nên khoá phải là Part + mã OP.

Đây là bài test NGUỒN: nó khoá cấu trúc file. Diện mạo thật -- ba nền khác nhau
từng pixel, cùng OP cùng màu qua nhiều hàng, OP khác nhau không trùng màu khi
bảng còn chỗ -- do tests/e2e/dashboard-employee-timeline.spec.js đo trên trình
duyệt thật.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.static

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_CSS = ROOT / 'app/mesflow/web/static/ui.css'
APP_JS = ROOT / 'app/mesflow/web/static/app.js'

# (B) Nghỉ theo lịch -- và hai ô chú giải giải thích chính chúng.
QUIET_SELECTORS = {'.shift-off', '.shift-lunch', '.legend-lunch', '.legend-off'}
# (C) Trống việc trong ca -- và ô chú giải của nó.
IDLE_SELECTORS = {'.employee-gap', '.legend-gap'}

QUIET_TOKENS = ('--timeline-quiet-fill', '--timeline-quiet-stripe',
                '--timeline-quiet-border', '--timeline-quiet-text')
IDLE_TOKENS = ('--timeline-idle-fill', '--timeline-idle-stripe',
               '--timeline-idle-border', '--timeline-idle-border-strong',
               '--timeline-idle-text')

# Màu đã nghỉ hưu: vàng/cam rực của khoảng hở cũ. (C) bây giờ vẫn ấm, nhưng là
# vàng RẤT nhạt -- khác hẳn, và test độ sáng bên dưới là chỗ chốt khác biệt đó.
RETIRED_COLORS = (
    '#f3b94f', '#fff3cf', '#e1a72f',
    'rgba(243,185,79', 'rgba(255,243,207',
    '#e27e40', '#d46f31',
    'rgba(226,126,64', 'rgba(255,226,207', 'rgba(210,148,29',
)


def _css() -> str:
    return UI_CSS.read_text(encoding='utf-8')


def _css_body() -> str:
    """ui.css đã bỏ chú thích.

    Chú thích cố ý nêu đích danh những màu đã nghỉ hưu (đó là điểm của chú
    thích), nên kiểm màu trên văn bản thô sẽ tự bắt chính lời giải thích. Bỏ
    chú thích cũng làm phần selector sạch: nếu không, cả khối chú thích đứng
    trước một rule bị hút vào chuỗi selector.
    """
    return re.sub(r'/\*.*?\*/', '', _css(), flags=re.S)


def _js() -> str:
    return APP_JS.read_text(encoding='utf-8')


def _rules(text: str):
    """[(selector, thân rule)] cho mọi rule phẳng. ui.css phần lớn minified
    một dòng, nên tách theo dấu ngoặc chứ không theo dòng."""
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r'([^{}@]+)\{([^{}]*)\}', text)]


def _rgb(value: str):
    value = value.strip().lstrip('#')
    if len(value) == 3:
        value = ''.join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _saturation(rgb) -> float:
    high, low = max(rgb), min(rgb)
    return 0.0 if high == 0 else (high - low) / high


def _luminance(rgb) -> float:
    """Độ sáng tương đối WCAG."""
    channels = []
    for raw in rgb:
        c = raw / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _token(name: str) -> str:
    match = re.search(rf'{name}\s*:\s*([^;}}]+)', _css_body())
    assert match, f'{name} chưa được khai báo'
    return match.group(1).strip()


def _single_source(pattern_token: str, expected: set[str]) -> str:
    css = _css_body()
    declaring = [sel for sel, body in _rules(css)
                 if re.search(rf'background\s*:\s*var\({pattern_token}\)', body)]
    assert len(declaring) == 1, (
        f'{len(declaring)} rule cùng đặt {pattern_token}: {declaring}. '
        'Giữ đúng một nguồn, đừng mở nguồn thứ hai.')
    covered = {part.strip() for part in declaring[0].split(',')}
    assert expected <= covered, f'thiếu trong nguồn chung: {sorted(expected - covered)}'
    return declaring[0]


# --------------------------------------------------------------------------
# (B) và (C): mỗi loại đúng một nguồn, và hai nguồn KHÁC nhau
# --------------------------------------------------------------------------

def test_scheduled_rest_has_exactly_one_background_source():
    _single_source('--timeline-quiet-pattern', QUIET_SELECTORS)


def test_in_shift_idle_has_exactly_one_background_source():
    _single_source('--timeline-idle-pattern', IDLE_SELECTORS)


def test_idle_and_scheduled_rest_are_not_the_same_visual():
    """Gộp hai loại vào một nền là xoá mất thông tin người dùng cần nhất."""
    idle, quiet = _token('--timeline-idle-fill'), _token('--timeline-quiet-fill')
    assert idle != quiet, 'trống việc và nghỉ theo lịch đang dùng chung một nền'
    assert _rgb(idle) != _rgb(quiet)
    idle_selectors = {p.strip() for p in _single_source('--timeline-idle-pattern', IDLE_SELECTORS).split(',')}
    quiet_selectors = {p.strip() for p in _single_source('--timeline-quiet-pattern', QUIET_SELECTORS).split(',')}
    assert not (idle_selectors & quiet_selectors), (
        f'selector nằm ở cả hai nhóm: {sorted(idle_selectors & quiet_selectors)}')


def test_no_timeline_background_element_keeps_a_background_of_its_own():
    """Không selector nào trong hai nhóm được tự đặt background lần nữa.

    Kể cả một background "vô hại" cũng đủ làm các loại lệch nhau trở lại -- đó
    chính là cách bốn công thức cũ sinh ra. Biến thể cũng tính: .employee-gap.long
    từng là chỗ màu cam lẻn về.
    """
    group = QUIET_SELECTORS | IDLE_SELECTORS

    def touches(selector):
        return any(part.strip() == base or part.strip().startswith(base + '.')
                   or part.strip().endswith(' ' + base)
                   for part in selector.split(',') for base in group)

    offenders = []
    for sel, body in _rules(_css_body()):
        if not touches(sel) or 'timeline-idle-pattern' in body or 'timeline-quiet-pattern' in body:
            continue
        if re.search(r'(^|;)\s*background(-color|-image)?\s*:', body):
            offenders.append(f'{sel} {{{body}}}')
    assert not offenders, 'nền riêng còn sót:\n  ' + '\n  '.join(offenders)


# --------------------------------------------------------------------------
# Từng họ màu phải đúng tính chất của ý nghĩa nó mang
# --------------------------------------------------------------------------

@pytest.mark.parametrize('token', QUIET_TOKENS)
def test_scheduled_rest_tokens_stay_cool_and_unsaturated(token):
    """(B) không nhắc ai: xám lạnh (lam ≥ đỏ), bão hoà thấp."""
    value = _token(token)
    red, _green, blue = _rgb(value)
    assert blue >= red, f'{token}={value} ngả ấm -- nghỉ theo lịch không được nhắc việc'
    assert _saturation(_rgb(value)) <= 0.25, f'{token}={value} quá đậm cho một nền yên'


@pytest.mark.parametrize('token', ('--timeline-idle-fill', '--timeline-idle-stripe'))
def test_idle_fill_is_warm_but_very_light(token):
    """(C) nhắc được, nhưng bằng vàng RẤT nhạt -- không phải vàng rực cũ."""
    value = _token(token)
    red, _green, blue = _rgb(value)
    assert red >= blue, f'{token}={value} không còn ấm -- mất hẳn tín hiệu nhắc việc'
    assert _saturation(_rgb(value)) <= 0.15, (
        f'{token}={value} bão hoà {_saturation(_rgb(value)):.0%} -- quá rực cho một nền')
    assert _luminance(_rgb(value)) >= 0.75, (
        f'{token}={value} quá tối; nền nhắc việc phải rất nhạt để không thành mảng đặc')


def test_idle_border_is_dashed_and_readable():
    """Viền đứt là nửa còn lại của tín hiệu -- màu nhạt một mình quá khẽ."""
    css = _css_body()
    rule = next(body for sel, body in _rules(css)
                if '.employee-gap' in {p.strip() for p in sel.split(',')}
                and 'timeline-idle-pattern' in body)
    assert re.search(r'border\s*:\s*1px\s+dashed\s+var\(--timeline-idle-border\)', rule), (
        f'viền trống việc phải là nét đứt: {rule}')
    assert _saturation(_rgb(_token('--timeline-idle-border'))) <= 0.55
    # Chữ trên nền nhắc việc phải đọc được.
    contrast = (_luminance(_rgb(_token('--timeline-idle-fill'))) + 0.05) / (
        _luminance(_rgb(_token('--timeline-idle-text'))) + 0.05)
    assert contrast >= 4.5, f'chữ "Trống việc" tương phản {contrast:.1f}:1, cần ≥ 4.5:1'


@pytest.mark.parametrize('color', sorted(set(RETIRED_COLORS)))
def test_retired_saturated_gap_colors_are_gone(color):
    assert color not in _css_body(), f'{color} vẫn còn -- đây là màu khoảng hở đã bỏ'


def test_timeline_tokens_live_in_the_one_root_block():
    """Token mới phải vào khối :root duy nhất, không mở khối thứ bảy."""
    css = _css()
    first_root = css.index(':root{', css.index('TOKEN DUY NHẤT'))
    depth, index = 1, first_root + len(':root{')
    while index < len(css) and depth:
        depth += (css[index] == '{') - (css[index] == '}')
        index += 1
    block = css[first_root:index]
    for token in (*QUIET_TOKENS, *IDLE_TOKENS,
                  '--timeline-quiet-pattern', '--timeline-idle-pattern'):
        assert f'{token}:' in block, f'{token} nằm ngoài khối token duy nhất'
        assert css.count(f'{token}:') == 1, f'{token} khai báo nhiều lần'


# --------------------------------------------------------------------------
# (A) Thanh việc: đặc, đọc được, và đủ chỗ cho nhiều OP cùng hiện
# --------------------------------------------------------------------------

def _tones():
    return re.findall(r'\.employee-session-segment\.tone-\d\{background:(#[0-9a-f]{6})\}', _css_body())


def test_task_bars_are_solid_distinct_and_readable():
    tones = _tones()
    assert len(tones) >= 8, f'bảng màu chỉ có {len(tones)} tông -- quá ít chỗ để OP khác nhau khác màu'
    assert len(set(tones)) == len(tones), f'hai tông trùng nhau: {tones}'
    for tone in tones:
        # Đặc và đủ tối để chữ trắng đọc được -- ngược hẳn với hai nền nhạt.
        contrast = 1.05 / (_luminance(_rgb(tone)) + 0.05)
        assert contrast >= 4.5, f'{tone}: chữ trắng chỉ đạt {contrast:.1f}:1, cần ≥ 4.5:1'


def test_task_tones_are_far_enough_apart_to_tell_apart():
    """Khác tông chưa đủ -- phải khác đủ XA để mắt tách được.

    Giải va chạm chỉ tránh việc hai OP nhận CÙNG một tông. Nó không cứu được
    khi hai tông khác nhau trên giấy lại gần nhau trên võng mạc: bảng cũ có
    teal 182° ngay cạnh xanh dương 204°, và ô liu 80° cạnh lục 132° -- hai OP
    rơi vào một cặp đó trông như cùng một OP, đúng thứ người dùng báo lỗi.

    Nên khoảng cách sắc tối thiểu được chốt ở đây, và độ sáng so le là chiều
    phân biệt thứ hai (phòng cho người khó phân biệt màu).
    """
    import colorsys
    tones = _tones()
    hues, lums = [], []
    for tone in tones:
        red, green, blue = (channel / 255 for channel in _rgb(tone))
        hues.append(colorsys.rgb_to_hls(red, green, blue)[0] * 360)
        lums.append(_luminance(_rgb(tone)))

    order = sorted(hues)
    gaps = [(b - a) for a, b in zip(order, order[1:] + [order[0] + 360])]
    assert min(gaps) >= 30, (
        f'hai tông chỉ cách nhau {min(gaps):.0f}° sắc -- quá gần để tách bằng mắt: '
        f'{sorted(round(h) for h in hues)}')

    # Chiều thứ hai: bảng phải có cả tông đậm và tông nhạt, không phẳng một mức.
    assert max(lums) / min(lums) >= 1.3, (
        'mọi tông cùng một độ sáng -- mất chiều phân biệt thứ hai')


def test_task_palette_count_matches_the_javascript_palette():
    """Bảng màu CSS và bảng tông JS lệch nhau là sinh ra thanh không có màu."""
    js_tones = re.search(r"const TIMELINE_TONES=\[([^\]]*)\]", _js()).group(1)
    assert len(re.findall(r"'tone-\d'", js_tones)) == len(_tones())


def test_status_does_not_overwrite_the_operation_identity_colour():
    """Trạng thái nói bằng viền/vòng sáng, không bằng cách sơn đè lên màu OP.

    Trước đây mọi session đang chạy đều bị sơn xanh lá và mọi session quá ca bị
    sơn đỏ -- nên hai OP khác nhau đang chạy trông y hệt nhau, đúng lúc người
    dùng cần phân biệt chúng nhất.
    """
    offenders = []
    for sel, body in _rules(_css_body()):
        if '.employee-session-segment' not in sel or re.search(r'\.tone-\d', sel):
            continue
        if not re.search(r'\.(open|stale-open)\b', sel):
            continue
        if re.search(r'(^|;)\s*background(-color|-image)?\s*:', body):
            offenders.append(f'{sel} {{{body}}}')
    assert not offenders, 'trạng thái đang sơn đè màu công đoạn:\n  ' + '\n  '.join(offenders)


# --------------------------------------------------------------------------
# Nguồn màu trong JavaScript
# --------------------------------------------------------------------------

def test_tone_key_is_part_plus_operation_not_the_loop_index():
    js = _js()
    assert 'palette[i%palette.length]' not in js, 'màu theo vị trí vẫn còn'
    assert "const palette=['p1'" not in js, 'palette theo vị trí vẫn còn'

    key_fn = js[js.index('function timelineToneKey'):js.index('function timelineToneHash')]
    assert 'part_code' in key_fn, (
        'khoá tông không đọc part_code -- mã OP lặp lại được giữa các Part, '
        'nên hai công đoạn khác hẳn nhau sẽ dùng chung màu')
    assert 'operation_code' in key_fn

    # Chỉ số vòng lặp vẫn còn vì nó xếp tầng cho phiên chồng giờ (lanes[i]) --
    # việc chỉ vị trí mới trả lời được. Điều phải chốt là nó không quyết màu.
    render = js[js.index('return ordered.map('):]
    render = render[:render.index('employee-session-segment')]
    assert 'lanes[i]' in render, 'chỉ số đang ở đây vì việc xếp tầng -- đã mất việc đó?'
    marker = 'employee-session-segment ${'
    tone_expression = js[js.index(marker) + len(marker):]
    tone_expression = tone_expression[:tone_expression.index('}')]
    assert tone_expression == 'timelineToneClass(x,toneMap)', (
        f'tông không còn đến từ nguồn chung: {tone_expression!r}')


def test_visible_operations_get_distinct_tones_while_the_palette_has_room():
    """Hai OP cùng hiện chỉ được trùng màu khi bảng đã hết chỗ.

    Băm một mình không đủ: băm rơi trùng ngay cả khi còn tông trống, và đó
    chính là cảnh "hai OP đang chạy đều màu tím". timelineToneMap() vì thế dò
    tiếp từ chỗ ưa thích, trên tập khoá đã sắp xếp (nên không phụ thuộc thứ tự
    session trả về).
    """
    js = _js()
    body = js[js.index('function timelineToneMap'):js.index('function timelineToneClass')]
    assert '.sort()' in body, 'tập khoá chưa sắp xếp -- màu sẽ đổi theo thứ tự dữ liệu trả về'
    assert 'used.has' in body, 'chưa có bước tránh trùng khi bảng còn chỗ'
    assert 'new Set' in body, 'chưa gom tập OP đang hiện'
    # Bảng tông dựng MỘT lần cho cả timeline, nên mọi hàng dùng chung kết quả
    # (một chỗ gọi, ngoài chính dòng định nghĩa hàm).
    calls = js.count('timelineToneMap(sessions)') - js.count('function timelineToneMap(sessions)')
    assert calls == 1, f'{calls} chỗ dựng bảng tông -- các hàng sẽ không dùng chung một bảng'


def test_tone_mapping_has_exactly_one_home():
    """Một bảng tông, một hàm. Bản sao thứ hai là chỗ hai màn hình trôi ra xa nhau."""
    js = _js()
    assert js.count('const TIMELINE_TONES=') == 1
    assert js.count('function timelineToneClass') == 1
    static_dir = ROOT / 'app/mesflow/web/static'
    others = [path for path in static_dir.rglob('*.js')
              if path != APP_JS and 'TIMELINE_TONES' in path.read_text(encoding='utf-8')]
    assert not others, f'bảng tông bị chép sang: {[p.name for p in others]}'


def test_idle_block_says_what_it_is_when_there_is_room():
    """Nền + viền là tín hiệu; chữ là lời giải thích. Hẹp quá thì bỏ chữ, giữ tín hiệu."""
    js = _js()
    assert 'Trống việc' in js, 'khối trống việc chưa có nhãn'
    gap_render = js[js.index('gapBlocks(ordered).map('):]
    gap_render = gap_render[:gap_render.index("}).join('')")]
    assert 'gapWidth>=' in gap_render, 'chưa có ngưỡng bề rộng -- nhãn sẽ bị nhồi vào khối vài pixel'
    assert 'title="Trống việc' in gap_render, 'mất title thì khối hẹp không còn cách nào tự giải thích'
