"""ui.css chỉ được có MỘT nguồn token, và không token nào mâu thuẫn với chính nó.

Bối cảnh (2026-09-09): ui.css tích tụ SÁU khối :root chồng nhau, di sản của năm
lớp "chuẩn hoá thiết kế" nối đuôi. Mười một token bị khai báo hai lần với hai
giá trị KHÁC nhau -- --radius-panel là 6px ở khối này và 8px ở khối kia,
--border-default là #d6dce3 và #c8d0d8, --surface-subtle là #f8fafc và #f6f8fa.

Vì mọi khối đều là :root và không khối nào dùng !important, khối đứng sau luôn
thắng. Nghĩa là hệ thống VẪN chạy đúng -- nhưng không ai đọc file này mà biết
được giá trị thật là gì, nên lớp sau lại đoán sai và đắp thêm !important. Đó là
cơ chế sinh ra 222 !important, chứ không phải ai đó lười.

Bài test này chốt lại kết quả dọn dẹp để lớp thứ bảy không mọc ra:

  * đúng một khối :root khai báo token;
  * không token nào khai báo hai lần;
  * các token nền tảng giữ đúng giá trị đã chốt -- đổi một trong số này là
    đổi diện mạo toàn hệ thống, phải là quyết định có chủ ý chứ không phải
    hệ quả phụ của một bản vá màn hình lẻ.

Đây là bài test NGUỒN, cố ý không mở trình duyệt: nó bảo vệ cấu trúc file, còn
diện mạo thật do tests/e2e/design-token-contract.spec.js đo.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.static

UI_CSS = pathlib.Path(__file__).resolve().parents[1] / 'app/mesflow/web/static/ui.css'

# Giá trị đã chốt khi gộp -- chính là giá trị ĐANG chạy trước khi gộp (khối
# cuối thắng), nên lần gộp không đổi một pixel nào.
FOUNDATION = {
    '--surface-canvas': '#eef1f4',
    '--surface-default': '#fff',
    '--surface-subtle': '#f6f8fa',
    '--surface-row-alt': '#fafbfc',
    '--text-primary': '#17212b',
    '--text-secondary': '#556170',
    '--border-subtle': '#d8dee5',
    '--border-default': '#c8d0d8',
    '--border-strong': '#9eabb7',
    '--border-emphasis': '#7f909f',
    '--action-primary': '#23658b',
    '--radius-control': '5px',
    '--radius-row': '5px',
    '--radius-card': '7px',
    '--radius-panel': '8px',
    '--radius-overlay': '9px',
}


def _css() -> str:
    return UI_CSS.read_text(encoding='utf-8')


def _root_spans(text: str):
    """Biên từng khối :root{...}, khớp ngoặc thật.

    Không dùng rindex('}'): dòng đầu ui.css là một dòng minified chứa hàng chục
    rule khác nhau, cắt kiểu đó sẽ nuốt luôn phần sau (đã dính một lần).
    """
    spans = []
    for match in re.finditer(r':root\{', text):
        index, depth = match.end(), 1
        while index < len(text) and depth:
            if text[index] == '{':
                depth += 1
            elif text[index] == '}':
                depth -= 1
            index += 1
        spans.append((match.start(), index))
    return spans


def _declarations():
    """[(tên token, giá trị, thứ tự khối)] theo đúng thứ tự xuất hiện."""
    text = _css()
    found = []
    for order, (start, end) in enumerate(_root_spans(text)):
        inner = text[start + len(':root{'):end - 1]
        for name, value in re.findall(r'(--[a-z0-9-]+)\s*:\s*([^;}]+)', inner):
            found.append((name.strip(), value.split('/*')[0].strip(), order))
    return found


def test_exactly_one_root_block_declares_tokens():
    """Khối :root chỉ đặt font/màu/nền thì không tính -- chúng không phải token."""
    declaring = {order for _n, _v, order in _declarations()}
    assert len(declaring) == 1, (
        f'{len(declaring)} khối :root đang khai báo token. Gộp vào khối token '
        'duy nhất ở đầu ui.css; đừng mở khối thứ hai.')


def test_no_token_is_declared_twice():
    seen: dict[str, str] = {}
    duplicates = []
    for name, value, _order in _declarations():
        if name in seen and seen[name] != value:
            duplicates.append(f'{name}: {seen[name]!r} rồi {value!r}')
        elif name in seen:
            duplicates.append(f'{name}: khai báo lại cùng giá trị {value!r}')
        seen[name] = value
    assert not duplicates, 'token khai báo trùng:\n  ' + '\n  '.join(duplicates)


@pytest.mark.parametrize('token,expected', sorted(FOUNDATION.items()))
def test_foundation_token_keeps_its_agreed_value(token, expected):
    """Đổi một trong số này là đổi diện mạo TOÀN hệ thống.

    Bài test không cấm đổi -- nó bắt người đổi phải sửa cả ở đây, nghĩa là phải
    biết mình đang đổi cái gì.
    """
    values = {value for name, value, _o in _declarations() if name == token}
    assert values == {expected}, f'{token} = {values or "(không thấy)"}, kỳ vọng {expected!r}'


def test_no_root_block_uses_important():
    """!important trong :root làm hỏng luôn quy tắc 'khối sau thắng'."""
    text = _css()
    for start, end in _root_spans(text):
        block = text[start:end]
        assert '!important' not in block, 'khối :root không được dùng !important'


def test_radius_values_come_from_tokens_where_a_token_exists():
    """Bo góc trùng KHỚP một token thì phải viết bằng token đó.

    Chỉ chốt bốn giá trị có token tương ứng (5/7/8/9px). Các giá trị khác
    (6/10/12/14/16px...) cố ý còn nguyên: quy chúng về token là ĐỔI diện mạo,
    thuộc các giai đoạn sau, không phải việc của lần gộp không-đổi-pixel này.
    """
    text = _css()
    spans = _root_spans(text)
    body = ''.join(
        text[a:b] for a, b in zip(
            [0] + [end for _s, end in spans],
            [start for start, _e in spans] + [len(text)]))
    offenders = {
        value for value in re.findall(
            r'border-radius\s*:\s*([0-9]+px)\s*(?:!important)?(?=[;}])', body)
        if value in {'5px', '7px', '8px', '9px'}
    }
    assert not offenders, (
        f'còn bo góc viết cứng dù đã có token: {sorted(offenders)} -- '
        'dùng var(--radius-control/card/panel/overlay)')
