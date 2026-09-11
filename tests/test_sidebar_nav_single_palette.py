"""Rail điều hướng trái chỉ được có MỘT nguồn màu: token --nav-*.

Bối cảnh (2026-09-11): trong vòng một ngày, bốn nhóm KẾ HOẠCH / ĐIỀU HÀNH /
DANH MỤC / QUẢN TRỊ hỏng hai lần. Lần đầu là cascade bị một dấu phẩy cắt đôi
nên <button> rơi về mặt mặc định của trình duyệt -- bốn khối TRẮNG giữa một
sidebar navy. Lần soi lại sau đó cho thấy nguyên nhân sâu hơn: màu của rail
nằm rải rác ở NĂM lớp chồng nhau trong ui.css, lớp sau ghi đè lớp trước, nên
giá trị đọc được ở lớp trước là giá trị CHẾT và đọc lên thì sai:

    nền rail       khối gốc #132235   <- thật ra là #18364e (lớp v71)
    nền active     khối gốc #21364b   <- thật ra là #1c3d59 (lớp polish)
    thanh accent   khối gốc #e39a22   <- thật ra là #4fa8dd (lớp polish)
    hover          ba giá trị khác nhau ở ba lớp
    thanh chỉ mục  vạch trắng 1px ở lớp cũ vẫn thắng khi sidebar thu gọn

Ai sửa nav cũng phải đoán, và đoán sai thì ra hồi quy. Bài test này chốt lại
kết quả dọn dẹp: hàng nav không được mang một mã màu viết cứng nào nữa.

Đây là bài test NGUỒN. Diện mạo thật -- bốn trạng thái, tương phản, thanh
accent, desktop/mobile/thu gọn -- do tests/e2e/sidebar-nav-surface.spec.js đo
bằng computed style.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.static

UI_CSS = pathlib.Path(__file__).resolve().parents[1] / 'app/mesflow/web/static/ui.css'

# Selector chạm vào HÀNG nav. Vỏ rail (.app-sidebar), nút thu gọn, brand và
# khối tài khoản cố ý không nằm trong danh sách: chúng là chrome của sidebar,
# không phải thang trạng thái điều hướng, và có ngôn ngữ viền/bóng riêng.
ROW_SELECTORS = ('.sidebar-item', '.sidebar-group-trigger', '.sidebar-sub-item',
                 '.sidebar-sub-heading', '.sidebar-group-panel')
COLOR_PROPS = ('background', 'background-color', 'color', 'box-shadow', 'outline', 'outline-color')
# Giá trị không phải "một màu viết cứng": token, hoặc từ khoá không mang màu.
ALLOWED = re.compile(
    r'^(?:[^#]*var\(--nav-[a-z-]+\)[^#]*|none|0|transparent|inherit|currentColor|initial|unset)$',
    re.IGNORECASE)
NAV_TOKENS = ('--nav-surface', '--nav-surface-open', '--nav-surface-hover',
              '--nav-surface-active', '--nav-surface-active-hover', '--nav-text',
              '--nav-text-open', '--nav-text-strong', '--nav-text-muted',
              '--nav-heading', '--nav-icon', '--nav-accent', '--nav-accent-icon',
              '--nav-divider')


def _rules():
    """[(selector, [(prop, value)])] -- bỏ comment trước khi tách rule."""
    text = re.sub(r'/\*.*?\*/', ' ', UI_CSS.read_text(encoding='utf-8'), flags=re.S)
    out = []
    for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', text):
        decls = []
        for decl in match.group(2).split(';'):
            if ':' not in decl:
                continue
            prop, _, value = decl.partition(':')
            decls.append((prop.strip().lower(), value.replace('!important', '').strip()))
        out.append((' '.join(match.group(1).split()), decls))
    return out


def test_every_nav_token_exists():
    text = UI_CSS.read_text(encoding='utf-8')
    missing = [t for t in NAV_TOKENS if not re.search(rf'{t}\s*:', text)]
    assert not missing, f'thiếu token nav: {missing}'


def test_no_hardcoded_colour_on_a_nav_row():
    offenders = []
    for selector, decls in _rules():
        if not any(key in selector for key in ROW_SELECTORS):
            continue
        for prop, value in decls:
            if prop in COLOR_PROPS and not ALLOWED.match(value):
                offenders.append(f'{selector[:80]} -> {prop}:{value}')
    assert not offenders, (
        'hàng nav đang mang màu viết cứng -- dùng token --nav-* trong khối :root '
        '(xem THANG TRẠNG THÁI ở cuối ui.css):\n  ' + '\n  '.join(offenders))


def test_every_sidebar_background_points_at_one_token():
    """Ba rule .app-sidebar cùng khai nền; cả ba phải trỏ về --nav-surface.

    Chính chỗ này sinh ra giá trị chết: khối gốc ghi #132235 trong khi màn hình
    thật chạy var(--bg-command) = #18364e của lớp v71.
    """
    backgrounds = [
        value for selector, decls in _rules() if selector == '.app-sidebar'
        for prop, value in decls if prop in ('background', 'background-color')
    ]
    assert backgrounds, 'không tìm thấy rule nền nào của .app-sidebar'
    assert all('var(--nav-surface)' in v for v in backgrounds), (
        f'nền rail đang khai ở nhiều nguồn khác nhau: {backgrounds}')
