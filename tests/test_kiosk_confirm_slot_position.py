"""Ô "tiến/xác nhận" của Kiosk web phải nằm BÊN PHẢI, giống footer ESP.

Gốc lỗi: `#screen-finish-confirm > .choice-grid` xếp các nút theo đúng thứ tự
DOM, và trong markup `#finish-confirm-ok` ('#' XÁC NHẬN) đứng TRƯỚC
`#finish-confirm-edit` ('*' QUAY LẠI). Kết quả: web hiện `# XÁC NHẬN` bên trái,
`* QUAY LẠI` bên phải -- ĐẢO so với ESP.

Trên firmware, mọi màn đều vẽ qua `drawFooterTwoActions(left, right)`
(`esp-kiosk/esp/mesflow_app.cpp:1386`) và MỌI lời gọi đều là dạng
`("* ...", "# ...")` -- `*` trái, `#` phải (mesflow_app.cpp:2951..3120). Công
nhân đứng máy nhớ vị trí chứ không đọc chữ; đảo hai nút là mời người ta bấm
QUAY LẠI khi định XÁC NHẬN.

Cách khoá: vị trí do **slot** quyết định, không do thứ tự DOM tình cờ --
`data-action-slot="back"` (order:1) và `data-action-slot="confirm"` (order:2).
Bài test hình học thật (đo toạ độ trên trình duyệt, cả ở 390px) nằm ở
`tests/e2e/kiosk-esp-parity.spec.js`; bài này khoá phần tĩnh để hỏng là đỏ ngay
cả khi không chạy được Playwright.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'app/mesflow/web/templates/kiosk.html'
CSS = ROOT / 'app/mesflow/web/static/kiosk.css'

SLOT_RE = re.compile(r'data-action-slot="(back|confirm)"')
ROW_RE = re.compile(r'<div class="(?:actions|choice-grid[^"]*)">(.*?)</div>', re.S)


def _html():
    return HTML.read_text(encoding='utf-8')


def test_css_puts_confirm_slot_after_back_slot():
    css = CSS.read_text(encoding='utf-8')
    assert '[data-action-slot="back"]{order:1}' in css
    assert '[data-action-slot="confirm"]{order:2}' in css


def test_confirm_screen_has_back_on_the_left_and_hash_on_the_right():
    html = _html()
    confirm_screen = html[html.index('id="screen-finish-confirm"'):html.index('id="screen-finished"')]
    assert SLOT_RE.findall(confirm_screen) == ['back', 'confirm', 'confirm'], (
        'Màn XÁC NHẬN phải là: * QUAY LẠI (back) rồi mới tới # XÁC NHẬN và # THỬ LẠI (confirm)'
    )
    # Nhãn phải đi cùng slot: phím xác nhận ở ô confirm, '*' ở ô back.
    #
    # Nhãn ô confirm là `Enter`, KHÔNG còn là `#` (2026-09-12, P1 bàn phím số
    # rời): bàn phím số rời không có phím `#` nào để bấm, nhưng CÓ `*` -- nên ô
    # back giữ nguyên ký tự. Đây chỉ là nhãn của WEB; bàn phím màng của ESP vẫn
    # có `#` vật lý và firmware không đổi (docs/KIOSK_ESP_PARITY.md §2).
    # Luật VỊ TRÍ ở trên (* trái, xác nhận phải) không liên quan tới việc đổi
    # nhãn và phải giữ nguyên.
    for slot, glyph, ident in [('back', '*', 'finish-confirm-edit'),
                               ('confirm', 'Enter', 'finish-confirm-ok'),
                               ('confirm', 'Enter', 'finish-submit-retry')]:
        tag = confirm_screen[confirm_screen.index(f'id="{ident}"'):]
        tag = tag[:tag.index('</button>')]
        assert f'data-action-slot="{slot}"' in tag
        assert f'>{glyph}</strong>' in tag


def test_every_action_row_lists_back_before_confirm():
    """Không màn nào được phép xếp ngược -- kể cả màn thêm sau này."""
    rows_with_both = 0
    for row in ROW_RE.findall(_html()):
        slots = SLOT_RE.findall(row)
        if 'back' in slots and 'confirm' in slots:
            rows_with_both += 1
            assert slots.index('back') < slots.index('confirm'), row
    # Bảo hiểm chống test rỗng: nếu attribute bị xoá sạch thì vòng lặp trên
    # không kiểm gì cả mà vẫn xanh.
    assert rows_with_both >= 3, f'chỉ thấy {rows_with_both} hàng có đủ 2 ô slot'
