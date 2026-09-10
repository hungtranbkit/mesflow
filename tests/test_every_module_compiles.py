"""Mọi module trong app/ phải COMPILE được, không chỉ parse được.

ast.parse() dựng cây cú pháp nhưng KHÔNG kiểm các quy tắc chỉ có ở bước biên
dịch. Quy tắc đáng nhớ nhất: `from __future__ import ...` bắt buộc phải là câu
lệnh đầu tiên. Một script sửa hàng loạt chèn import lên trên nó sẽ qua được
ast.parse trơn tru, rồi container chết lúc khởi động với

    SyntaxError: from __future__ imports must occur at the beginning of the file

Đã xảy ra đúng như vậy (2026-09-10, khi quét bộ lọc operation_type sang
policy): sáu file, ast.parse báo OK cả sáu, gate đỏ ở bước dựng container --
tức là mất một vòng build mới biết.

Bài test này chạy trong một giây và bắt được ngay lớp lỗi đó.
"""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.static

APP = pathlib.Path(__file__).resolve().parents[1] / 'app' / 'mesflow'
MODULES = sorted(p for p in APP.rglob('*.py') if '__pycache__' not in p.parts)


def test_there_are_modules_to_check():
    """Nếu đường dẫn đổi, bài test phải đỏ chứ không được lặng lẽ kiểm 0 file."""
    assert len(MODULES) > 20, f'chỉ tìm thấy {len(MODULES)} module -- đường dẫn sai?'


@pytest.mark.parametrize('path', MODULES, ids=lambda p: str(p.relative_to(APP)))
def test_module_compiles(path):
    source = path.read_text(encoding='utf-8')
    try:
        compile(source, str(path), 'exec')
    except SyntaxError as exc:
        pytest.fail(f'{path.relative_to(APP)}:{exc.lineno} {exc.msg}')
