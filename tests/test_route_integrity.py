"""Vào được thì phải ra được: mọi route đều có hàm render thật.

BỐI CẢNH. openPage() ở app.js là một chuỗi if dài, mỗi nhánh gọi một hàm
render. Các hàm đó nằm rải ở app.js và ở pages/*.js, nạp qua thẻ script riêng.
Không có gì nối hai bên lại -- xoá hay đổi tên một hàm render thì nhánh dispatch
vẫn còn, và trang chỉ đơn giản là TRẮNG kèm một ReferenceError trong console mà
người dùng không mở.

Đã xảy ra: nhánh ``if(id==='esp-ota')return renderEspOta();`` gọi một hàm không
tồn tại ở bất kỳ file nào. Route không nằm trong menu nên không ai bấm phải,
nhưng ai gõ ?page=esp-ota thì nhận trang trắng. Nhánh này đã gỡ cùng với việc
bỏ firmware ESP đời cũ.

Bài test đọc NGUỒN chứ không mở trình duyệt: nó phải phủ được cả những route
không có trong menu -- đúng loại mà smoke theo menu bỏ sót, và cũng đúng loại
đã hỏng.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.static

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app/mesflow/web/static'


def _app_js() -> str:
    return (STATIC / 'app.js').read_text(encoding='utf-8')


def _all_frontend_source() -> str:
    parts = [_app_js()]
    for path in sorted((STATIC / 'pages').glob('*.js')):
        parts.append(path.read_text(encoding='utf-8'))
    for path in sorted((STATIC / 'core').glob('*.js')):
        parts.append(path.read_text(encoding='utf-8'))
    return '\n'.join(parts)


def _defined(name: str, source: str) -> bool:
    """Hàm này có được định nghĩa ở đâu đó trong frontend không?"""
    patterns = (
        rf'\bfunction\s+{name}\s*\(',
        rf'\b(?:const|let|var)\s+{name}\s*=',
        rf'\bwindow\.{name}\s*=',
        rf'\b{name}\s*=\s*(?:async\s*)?function',
        rf'\b{name}\s*=\s*(?:async\s*)?\(',
    )
    return any(re.search(p, source) for p in patterns)


def test_every_dispatched_render_function_exists():
    """Nhánh dispatch gọi hàm không tồn tại = trang trắng, không có cảnh báo."""
    app = _app_js()
    source = _all_frontend_source()
    dispatched = sorted(set(re.findall(r"id===['\"][a-z0-9-]+['\"]\)\s*return\s+(\w+)\(", app)))
    assert dispatched, 'không đọc được nhánh dispatch nào -- bài test này đã mất tác dụng'
    missing = [fn for fn in dispatched if not _defined(fn, source)]
    assert not missing, (
        'openPage() gọi hàm không tồn tại, các route này sẽ ra trang trắng:\n  '
        + '\n  '.join(missing))


def test_every_menu_page_has_a_handler():
    """Trang có trong menu thì phải có nhánh dispatch hoặc registerPage."""
    app = _app_js()
    source = _all_frontend_source()
    menu_pages = set(re.findall(r"page:'([a-z0-9-]+)'", app))
    assert menu_pages, 'không đọc được registry trang'
    dispatched = set(re.findall(r"id===['\"]([a-z0-9-]+)['\"]", app))
    registered = set(re.findall(r"registerPage\(['\"]([a-z0-9-]+)['\"]", source))
    # renderResource xử lý mọi trang danh mục qua bảng `resources`.
    resource_pages = set(re.findall(r"^\s*([a-z0-9-]+)\s*:\s*\{", app, re.M))
    orphans = sorted(menu_pages - dispatched - registered - resource_pages)
    assert not orphans, ('trang có trong menu nhưng không có handler:\n  '
                         + '\n  '.join(orphans))


def test_no_dispatch_branch_points_at_a_removed_feature():
    """Bỏ một tính năng thì phải gỡ cả nhánh dispatch của nó."""
    app = _app_js()
    assert 'renderEspOta' not in app, (
        'nhánh esp-ota đã gỡ cùng firmware ESP đời cũ; đừng thêm lại nếu chưa có '
        'hàm render thật, nếu không route đó lại ra trang trắng')


def test_unknown_route_renders_a_not_found_state_not_a_blank_screen():
    """Gỡ một route thì phải để lại thông báo, không để lại khoảng trống.

    Gỡ nhánh esp-ota đã đổi một ReferenceError thành một màn hình trắng im
    lặng -- chưa khá hơn là bao. Người gõ nhầm URL hay bấm bookmark cũ cần biết
    mình đang ở đâu.
    """
    app = _app_js()
    assert 'Không tìm thấy trang' in app, (
        'openPage() không có nhánh cuối cho route lạ -- route không khớp sẽ ra trang trắng')
    assert 'Không có màn hình' in app


def test_registered_pages_are_loaded_by_the_shell():
    """pages/*.js phải được nạp, nếu không registerPage không bao giờ chạy."""
    index = None
    for candidate in ('app/mesflow/web/templates/app.html',
                      'app/mesflow/web/templates/index.html'):
        path = ROOT / candidate
        if path.exists():
            index = path.read_text(encoding='utf-8')
            break
    if index is None:
        pytest.skip('không tìm thấy template shell để kiểm thẻ script')
    source = _all_frontend_source()
    registered_files = {
        path.name for path in sorted((STATIC / 'pages').glob('*.js'))
        if re.search(r"registerPage\(", path.read_text(encoding='utf-8'))
    }
    missing = [name for name in sorted(registered_files) if name not in index]
    assert not missing, ('page module có registerPage nhưng shell không nạp:\n  '
                         + '\n  '.join(missing))
