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
    assert 'const codeKey=codeLabel' in js, 'codeLabel phải là tuỳ chọn, không bật cứng'
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


def test_timeline_parent_item_shows_code_and_part():
    """Ba dòng liên tiếp cùng ghi "HÀN ROBOT" là ba dòng không phân biệt nổi.

    Bảo đảm này TRƯỚC ĐÂY do chip session giữ. Lớp chip đã bị gỡ (nó lặp lại
    chính Operation đã liệt kê ngay trên), nên nay ITEM CHA của mỗi Operation
    phải mang nhận dạng -- cùng một bảo đảm, chỗ khác."""
    app = APP_JS.read_text(encoding='utf-8')
    fn = app.split('const opGroupList=', 1)[1].split('\n    };', 1)[0]
    head = fn.split('const ident=', 1)[1].split('});', 1)[0]
    assert "codeLabel:'Operation'" in head
    assert 'opMetaHtml(x)' in head, 'item cha phải có Part · PO'
    assert 'opTooltip(x)' in head


def test_employee_summary_lists_each_operation_instead_of_joining():
    """Khối "nhân viên này hôm nay làm những OP nào" từng nối tên và mã bằng
    ' · ' -- hai Part cùng tên cho ra "HÀN ROBOT · HÀN ROBOT" rồi hai mã dính
    liền. Nay mỗi Operation là một item riêng do opGroupList dựng."""
    app = APP_JS.read_text(encoding='utf-8')
    block = app.split('employee-day-summary">', 1)[1].split('</div></article>', 1)[0]
    assert 'opGroupList(ordered,g)' in block
    assert "String(x.operation_name||x.operation_code||'').trim()).filter(Boolean).join(' · ')" not in app


def test_one_shared_helper_binds_part_and_po_everywhere():
    """Ba renderer (card, chip, khối tổng hợp) phải dùng CHUNG một helper.
    Mỗi nơi tự dựng Part/PO theo kiểu riêng là cách chúng lệch dần."""
    app = APP_JS.read_text(encoding='utf-8')
    # op-card (3 màn, một helper) + item cha của Ngày công. Lớp chip cũ đã gỡ.
    assert app.count('opMetaHtml(x)') == 2
    helper = app.split('const opMetaHtml=', 1)[1].split(';\n', 1)[0]
    assert 'x.part_code' in helper and 'x.po_code' in helper
    assert 'esc(' in helper, 'metaHtml do người gọi escape'


def test_stacked_and_when_lines_have_styling():
    css = UI_CSS.read_text(encoding='utf-8')
    assert '.op-identity .op-identity-when{' in css
    assert 'display:block' in css.split('.op-identity .op-identity-when{', 1)[1].split('}', 1)[0]
    assert '.op-identity.op-identity-stacked{' in css
    assert '.op-identity-more{' in css


def test_employee_day_groups_by_operation_not_by_session():
    """Một dòng = một Operation, không phải một session.

    Trước đây khối "Ngày công theo nhân viên" liệt kê Operation ở trên rồi lại
    liệt kê từng session thành chip ở dưới, nên một người làm 2 Operation x 1
    session hiện ra BỐN dòng cho đúng hai việc -- hai lớp nói cùng một chuyện.
    """
    app = APP_JS.read_text(encoding='utf-8')
    assert 'const opGroupList=' in app
    block = app.split('employee-day-summary">', 1)[1].split('</div></article>', 1)[0]
    assert 'opGroupList(ordered,g)' in block, 'khối tổng hợp phải đi qua opGroupList'
    # Lớp chip session cũ đã gỡ hẳn, không còn render song song.
    assert 'sessionChip' not in app
    assert 'employee-session-chips' not in app


def test_grouping_key_is_operation_identity_not_name():
    """Hai Part của cùng một PO dùng chung tên công đoạn ("HÀN ROBOT"), nên gom
    theo tên là nhập hai việc khác nhau làm một."""
    app = APP_JS.read_text(encoding='utf-8')
    fn = app.split('const opGroupList=', 1)[1].split('\n    };', 1)[0]
    assert 'x.operation_id??x.operation_code' in fn, 'ưu tiên id, fallback code'
    # Tên chỉ được dùng làm chốt cuối cùng, không phải khoá chính.
    key_line = [l for l in fn.splitlines() if 'const key=' in l][0]
    assert key_line.index('operation_id') < key_line.index('operation_name')


def test_children_carry_no_duplicate_identity_and_default_collapsed():
    app = APP_JS.read_text(encoding='utf-8')
    fn = app.split('const opGroupList=', 1)[1].split('\n    };', 1)[0]
    kids = fn.split('emp-op-sessions', 1)[1].split('}).join', 1)[0]
    # Child chỉ giờ/thời lượng/sản lượng -- parent ngay trên đã mang nhận dạng.
    for forbidden in ('opMetaHtml', 'opTooltip', 'codeLabel', 'operation_code'):
        assert forbidden not in kids, f'child lặp lại {forbidden}'
    assert 'emp-op-when' in kids and 'emp-op-dur' in kids and 'emp-op-qty' in kids
    # Mặc định đóng, và chỉ Operation có >=2 phiên mới có nút mở.
    assert "expanded?'':' hidden'" in fn
    assert 'multi=n>1' in fn and 'multi?' in fn


def test_expand_state_survives_the_ten_second_refresh():
    """Dashboard tự vẽ lại mỗi 10 giây. Trạng thái mở nằm trong hàm vẽ sẽ bị
    đặt lại mỗi nhịp -- người đang đọc chi tiết thấy nó tự đóng sập."""
    app = APP_JS.read_text(encoding='utf-8')
    assert 'const dailyOpExpanded=new Set()' in app
    # Khai báo ở MODULE, trước hàm vẽ dashboard.
    assert app.index('const dailyOpExpanded') < app.index('async function renderDashboard')
    # Uỷ quyền sự kiện, không gán onclick lại sau mỗi lần vẽ.
    assert "data-op-toggle" in app and "closest?.('[data-op-toggle]')" in app
