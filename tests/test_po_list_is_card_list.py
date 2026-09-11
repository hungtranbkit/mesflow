"""Danh sách Production Order là DANH SÁCH THẺ, không phải bảng (REQ-UI-022).

Bài E2E tests/e2e/po-list-card-contract.spec.js đo PIXEL THẬT (gap dọc giữa
hai thẻ liền nhau, bo góc computed, không tràn ngang ở 390px) -- đó mới là
bằng chứng người dùng thấy gì. File này khoá những thứ E2E KHÔNG nhìn được,
và khoá rẻ hơn nhiều:

  1. renderProductionOrders() không dựng lại <table>/.table-wrap;
  2. .po-card-list khai báo gap THẬT (gap:0 là đúng thứ bài E2E bắt được,
     nhưng bắt sớm ở đây thì không phải dựng cả trình duyệt);
  3. .po-card KHÔNG tự viết border-radius -- hình khối do rule quét
     `[class$="-card"]` sở hữu (ui.css §838, xem
     tests/test_admin_list_card_radius_contract.py). Viết lại ở .po-card là
     viết vào chỗ CHẾT: rule quét dùng !important nên giá trị đó không bao
     giờ chạy, và người đọc sau sẽ tin nhầm nó;
  4. REQ-UI-022 có ở CẢ HAI bản EN và VI, mỗi bản đúng một định nghĩa.

NEGATIVE PROOF: đổi `.po-card-list{gap:...}` thành `gap:0` -> (2) đỏ; thêm
`border-radius` vào khối `.po-card` -> (3) đỏ; xoá dòng REQ-UI-022 khỏi bản
VI -> (4) đỏ.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / 'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
CSS = (ROOT / 'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')

#: Image test KHÔNG copy docs/ (cùng lý do DESIGN.md vắng mặt trong
#: tests/test_admin_list_card_radius_contract.py). Hai bài requirement bên
#: dưới vì thế phải tự bỏ qua khi chạy trong container, và chỉ chạy thật khi
#: gọi pytest từ một checkout đầy đủ.
REQUIREMENT_DOCS = {
    'EN': ROOT / 'docs/MESFLOW_MASTER_REQUIREMENTS.md',
    'VI': ROOT / 'docs/MESFLOW_MASTER_REQUIREMENTS_VI.md',
}


def _requirement_docs():
    missing = [str(p) for p in REQUIREMENT_DOCS.values() if not p.exists()]
    if missing:
        pytest.skip(f'{missing[0]} not present in this test image -- run from a real checkout')
    return {lang: path.read_text(encoding='utf-8') for lang, path in REQUIREMENT_DOCS.items()}


def _render_po_list_source() -> str:
    """Thân renderProductionOrders(), tới ngay trước hàm kế tiếp."""
    start = APP_JS.index('async function renderProductionOrders(')
    end = APP_JS.index('window.openProductionOrder=', start)
    return APP_JS[start:end]


def _rule_body(selector: str) -> str:
    """Thân rule mà selector ĐÚNG BẰNG `selector` (bỏ qua @media)."""
    stripped = re.sub(r'/\*.*?\*/', ' ', CSS, flags=re.S)
    for sel, body in re.findall(r'([^{}]+)\{([^{}]*)\}', stripped):
        parts = [p.strip() for p in sel.strip().replace('\n', ' ').split(',')]
        if selector in parts:
            return body
    return ''


def test_po_list_renders_cards_not_a_table():
    source = _render_po_list_source()
    assert 'po-card-list' in source, 'danh sách PO phải dựng khung .po-card-list'
    assert 'class="po-card"' in source, 'mỗi PO phải là một .po-card'
    for dead in ('<table', 'table-wrap', '<tbody', '<tr ', '<th>'):
        assert dead not in source, f'danh sách PO dựng lại markup bảng: {dead!r}'


def test_po_card_keeps_the_click_and_menu_hooks():
    """Đổi markup không được làm rơi hành vi: bấm cả thẻ mở PO, menu thao tác."""
    source = _render_po_list_source()
    for hook in ('data-po-row=', 'data-po-menu=', 'data-po-start=', 'role="link"', 'tabindex="0"'):
        assert hook in source, f'thẻ PO mất hook {hook!r}'


def test_po_card_list_declares_a_real_vertical_gap():
    body = _rule_body('.po-card-list')
    assert body, '.po-card-list không có rule nào'
    gap = re.search(r'(?<![-\w])gap:\s*([^;]+)', body)
    assert gap, '.po-card-list phải khai báo gap -- đó là thứ tách các thẻ'
    value = gap.group(1).strip()
    assert value not in ('0', '0px', 'normal'), f'.po-card-list gap={value}: thẻ sẽ dính nhau'


def test_po_card_does_not_redeclare_its_shape():
    body = _rule_body('.po-card')
    assert body, '.po-card không có rule nào'
    assert 'border-radius' not in body, (
        '.po-card không được tự viết border-radius: hình khối do rule quét '
        '[class$="-card"] sở hữu bằng !important, giá trị viết ở đây là giá trị chết'
    )


def test_req_ui_022_is_defined_once_in_both_languages():
    for label, doc in _requirement_docs().items():
        definitions = re.findall(r'^\|\s*REQ-UI-022\s*\|', doc, flags=re.M)
        assert len(definitions) == 1, (
            f'REQ-UI-022 phải được định nghĩa đúng một lần trong bản {label}, '
            f'đang có {len(definitions)}'
        )


def test_req_ui_022_points_at_its_runtime_contract():
    for label, doc in _requirement_docs().items():
        assert 'tests/e2e/po-list-card-contract.spec.js' in doc, (
            f'bảng truy vết bản {label} phải trỏ REQ-UI-022 sang bài E2E đo pixel'
        )
