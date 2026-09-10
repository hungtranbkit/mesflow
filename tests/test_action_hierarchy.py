"""Một màn hình chỉ có MỘT hành động chính, và "Làm mới" không bao giờ là nó.

BỐI CẢNH. Audit 2026-09-10 đếm nút trên 12 màn ở 1366px và 390px. Kết quả:
"Làm mới" -- cùng một hành động, cùng một chữ -- xuất hiện 8 lần dưới dạng
``class="btn"`` và 7 lần dưới dạng ``class="btn primary"``. Người dùng học được
màu đậm = việc chính; ở đây màu đậm không nói lên gì cả vì nó gắn vào những
việc khác hẳn nhau tuỳ màn.

Chỗ hỏng rõ nhất là Năng suất nhân viên: "Làm mới" và "Áp dụng lên Kiosk" cùng
là primary, nằm cạnh nhau. Một cái nạp lại bảng, cái kia đẩy cấu hình xuống
thiết bị ngoài xưởng. Bấm nhầm không giống nhau chút nào.

Bài test đọc nguồn thay vì mở trình duyệt: nó phải phủ cả những màn cần dữ liệu
mới hiện nút, và những màn không nằm trong menu.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.static

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app/mesflow/web/static'

#: Nút chỉ nạp lại dữ liệu đang xem. Không đổi gì, không gửi gì đi.
RELOAD_LABELS = ('Làm mới',)


def _sources() -> list[pathlib.Path]:
    return [STATIC / 'app.js'] + sorted((STATIC / 'pages').glob('*.js'))


def _buttons(source: str) -> list[tuple[str, str]]:
    """(chuỗi class, nhãn) của mọi nút viết thẳng trong template."""
    return re.findall(r'class="((?:btn|mf-btn)[^"]*)"[^>]*>\s*([^<>{]{1,40}?)\s*<', source)


def test_reload_is_never_the_primary_action():
    offenders = []
    for path in _sources():
        for classes, label in _buttons(path.read_text(encoding='utf-8')):
            if label.strip() in RELOAD_LABELS and 'primary' in classes:
                offenders.append(f'{path.relative_to(ROOT)}: "{label.strip()}" -> {classes}')
    assert not offenders, (
        '"Làm mới" chỉ nạp lại dữ liệu, nó không phải việc chính của màn nào.\n'
        'Để nó là primary thì hành động thật sự của màn mất chỗ đứng:\n  '
        + '\n  '.join(offenders))


def test_reload_buttons_all_look_the_same():
    """Cùng một chữ thì phải cùng một dáng, không thì màu sắc hết nghĩa."""
    shapes: dict[str, set[str]] = {}
    for path in _sources():
        for classes, label in _buttons(path.read_text(encoding='utf-8')):
            if label.strip() in RELOAD_LABELS:
                shapes.setdefault(label.strip(), set()).add(classes.strip())
    assert shapes, 'không tìm thấy nút Làm mới nào -- bài test này đã mất tác dụng'
    mixed = {k: sorted(v) for k, v in shapes.items() if len(v) > 1}
    assert not mixed, f'cùng một nhãn nhưng nhiều kiểu nút khác nhau: {mixed}'
