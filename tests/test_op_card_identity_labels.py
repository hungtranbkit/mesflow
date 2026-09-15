"""Thẻ Operation phải tự nói ra nó là Operation nào, của Part nào, PO nào.

VÌ SAO. Một PO có nhiều Part, và cùng một công đoạn trên các Part khác nhau
mang ĐÚNG một cái tên. Trên TEST (audit read-only 2026-09-15):

    op 2416  6126-KM-349170-204-OP01  HÀN ROBOT  part KM-349170-204
    op 2418  6126-KM-367170-204-OP01  HÀN ROBOT  part KM-367170-204
    (cùng PO 6126, cùng source_op_no=1, cùng định mức 90s/SP)

Hai dòng "HÀN ROBOT" cạnh nhau đọc như dữ liệu bị nhân đôi. Đối chiếu bằng
truy vấn cho thấy KHÔNG có trùng lặp nào: 0 mã Operation trùng toàn hệ thống,
0 mã Part trùng trong một PO, 0 bản sao (PO, Part, mã). Mã và Part vốn đã hiện
trên thẻ nhưng không có nhãn, nên người mới không đọc ra dòng thứ hai là gì.

Bài này chốt NHÃN, không chốt dữ liệu -- grouping vẫn là o.id ở tầng SQL.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_JS = ROOT / 'app/mesflow/web/static/core/ui.js'
APP_JS = ROOT / 'app/mesflow/web/static/app.js'
UI_CSS = ROOT / 'app/mesflow/web/static/ui.css'


def test_primitive_supports_an_optional_code_label():
    js = UI_JS.read_text(encoding='utf-8')
    assert "codeLabel=''" in js, 'opIdentity phải nhận codeLabel'
    # Nhãn là TUỲ CHỌN: chip timeline và hàng Quản lý Session chỉ rộng vài chục
    # pixel, bật cứng "Operation:" ở đó là cướp chỗ của chính cái mã.
    assert 'codeLabel?' in js, 'codeLabel phải là tuỳ chọn, không bật cứng'
    assert 'op-identity-key' in js


def test_every_operation_card_uses_the_labelled_identity():
    app = APP_JS.read_text(encoding='utf-8')
    assert 'const opCardIdentity=' in app
    # Ba nơi dựng .op-card: "Tiến độ theo Operation", "Operation cần chú ý",
    # và "Danh sách OP phát sinh". Cả ba phải đi qua cùng một helper -- để
    # không màn nào tự dựng lại khối nhận dạng theo kiểu riêng rồi lệch dần.
    assert app.count('opCardIdentity(x)') == 3, app.count('opCardIdentity(x)')
    # Không còn nơi nào dựng meta po/part thủ công cho op-card.
    assert "meta:`${x.po_code||''} · ${x.part_code||''}`" not in app


def test_identity_renders_the_three_agreed_lines():
    app = APP_JS.read_text(encoding='utf-8')
    helper = app.split('const opCardIdentity=', 1)[1].split('});', 1)[0]
    # dòng 1: tên (primitive lo)
    assert 'name:x.operation_name' in helper
    # dòng 2: "Operation: <mã>"
    assert "codeLabel:'Operation'" in helper
    assert 'code:x.operation_code' in helper
    # dòng 3 dựng ở helper dùng chung opMetaHtml -- xem bài
    # test_one_shared_helper_binds_part_and_po_everywhere.
    assert 'metaHtml:opMetaHtml(x)' in helper
    meta = app.split('const opMetaHtml=', 1)[1].split(';\n', 1)[0]
    assert '>Part:<' in meta and '>PO:<' in meta
    assert meta.index('>Part:<') < meta.index('>PO:<'), 'Part phải đứng trước PO'
    # Giá trị do người gọi escape (quy ước của metaHtml trong ui.js).
    assert 'esc(x.part_code' in meta and 'esc(x.po_code' in meta
    # Dữ liệu thật, không hardcode mã nào.
    for literal in ('6126', 'KM-349170', 'HÀN ROBOT'):
        assert literal not in helper and literal not in meta, f'không được hardcode {literal}'


def test_part_name_stays_reachable_in_the_tooltip():
    """Tên Part ("Cung nhỏ"/"Cung lớn") là thứ phân biệt nhanh nhất với người
    trong xưởng. Format đã chốt không đặt nó lên mặt thẻ, nên nó phải còn ở
    title= chứ không được biến mất khỏi giao diện."""
    app = APP_JS.read_text(encoding='utf-8')
    helper = app.split('const opCardIdentity=', 1)[1].split('});', 1)[0]
    assert 'tooltip:opTooltip(x)' in helper
    tooltip = app.split('const opTooltip=', 1)[1].split(';\n', 1)[0]
    assert 'x.part_name' in tooltip and 'x.part_code' in tooltip and 'x.po_code' in tooltip


def test_label_typography_is_secondary_and_code_never_wraps():
    css = UI_CSS.read_text(encoding='utf-8')
    key = css.split('.op-identity .op-identity-key{', 1)[1].split('}', 1)[0]
    # Nhãn nhẹ hơn giá trị đứng sau nó, và không bao giờ tách khỏi dấu hai chấm.
    assert 'font-weight:500' in key
    assert 'var(--muted)' in key
    assert 'white-space:nowrap' in key
    # Mã Operation vẫn không được ngắt giữa chừng (ngắt ra đọc thành mã khác);
    # luật chung của primitive lo phần đó.
    assert '.op-identity>small.row-code,.op-identity>small.op-identity-meta{' in css
    assert 'white-space:nowrap' in css.split(
        '.op-identity>small.row-code,.op-identity>small.op-identity-meta{', 1)[1].split('}', 1)[0]


def test_timeline_session_chip_shows_code_and_part():
    """Ba chip liên tiếp cùng ghi "HÀN ROBOT 07:32–09:42 / 09:43–Đang chạy /
    13:32–Đang chạy" là ba dòng không phân biệt nổi: người đọc không biết đó là
    ba lần làm MỘT việc hay ba việc khác nhau.

    Bản trước cố ý bỏ mã khỏi chip (showCode:false) vì "khối tổng hợp phía trên
    đã mang mã". Lý do đó chỉ đúng khi mỗi Operation một tên khác nhau."""
    app = APP_JS.read_text(encoding='utf-8')
    chip = app.split('const sessionChip=', 1)[1].split('\n    };', 1)[0]
    assert chip.strip(), 'không tách được sessionChip'
    # Bỏ comment trước khi soi: phần giải thích có NHẮC tới showCode:false như
    # thứ đã gỡ, và một bài kiểm đọc trúng lời giải thích của chính nó thì đo
    # sai. Chỉ lệnh gọi thật mới tính.
    call = '\n'.join(l for l in chip.splitlines() if not l.strip().startswith('//'))
    assert 'showCode:false' not in call, 'chip phải hiện lại mã Operation'
    assert "codeLabel:'Operation'" in call
    assert 'opMetaHtml(x)' in call, 'chip phải có Part · PO'
    # Thời gian/sản lượng vẫn có, nhưng đứng SAU phần nhận dạng.
    assert 'op-identity-when' in call
    meta = call.split('metaHtml:', 1)[1]
    assert meta.index('opMetaHtml(x)') < meta.index('op-identity-when')


def test_employee_summary_lists_each_operation_instead_of_joining():
    """Khối "nhân viên này hôm nay làm những OP nào" từng nối tên và mã bằng
    ' · '. Hai Part dùng chung tên công đoạn cho ra "HÀN ROBOT · HÀN ROBOT" rồi
    hai mã dính liền -- đọc như dữ liệu hỏng."""
    app = APP_JS.read_text(encoding='utf-8')
    block = app.split('employee-day-summary">', 1)[1].split('}<small>', 1)[0]
    assert 'ops.slice(0,3).map(' in block
    assert 'MFUI.opIdentity({' in block, 'mỗi Operation là một khối riêng'
    assert "codeLabel:'Operation'" in block and 'opMetaHtml(x)' in block
    # Không còn nối chuỗi tên/mã.
    assert "String(x.operation_name||x.operation_code||'').trim()).filter(Boolean).join(' · ')" not in app
    assert 'op-identity-stacked' in block


def test_one_shared_helper_binds_part_and_po_everywhere():
    """Ba renderer (card, chip, khối tổng hợp) phải dùng CHUNG một helper.
    Mỗi nơi tự dựng Part/PO theo kiểu riêng là cách chúng lệch dần."""
    app = APP_JS.read_text(encoding='utf-8')
    assert app.count('opMetaHtml(x)') == 3
    helper = app.split('const opMetaHtml=', 1)[1].split(';\n', 1)[0]
    assert 'x.part_code' in helper and 'x.po_code' in helper
    assert 'esc(' in helper, 'metaHtml do người gọi escape'


def test_stacked_and_when_lines_have_styling():
    css = UI_CSS.read_text(encoding='utf-8')
    assert '.op-identity .op-identity-when{' in css
    assert 'display:block' in css.split('.op-identity .op-identity-when{', 1)[1].split('}', 1)[0]
    assert '.op-identity.op-identity-stacked{' in css
    assert '.op-identity-more{' in css
