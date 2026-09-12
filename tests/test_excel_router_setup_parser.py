"""File Lộ trình sản xuất khai báo thời gian setup thì phải tự sinh OP SETUP.

BỐI CẢNH. Tờ GO ROUTER của xưởng có sẵn ô "Thời gian Setup ( phút )" trong mỗi
block Operation, nhưng importer trước đây không đọc nó: mọi Operation vào hệ
thống với ``requires_setup=False``, và người quản lý phải vào từng OP bật tay.
Với file thật (NEWARK ARM CHAIR: 44 sheet, 112 block OPERATION + 1 công đoạn quy
trình suy ra từ tờ 'SƠN TĨNH ĐIỆN', 47 chỗ có setup) thì
đó là 47 lần bật tay cho MỘT lần nhập file.

Bài test khoá bốn thứ:

  * đọc đúng số, theo NEO NHÃN chứ không theo ô tuyệt đối;
  * >0 mới sinh setup; 0 / trống / '-' thì không;
  * số âm và chữ vô nghĩa bị CHẶN kèm sheet + dòng, không âm thầm bỏ qua;
  * mã Operation trùng trong cùng một Part được tách xác định, và va chạm được
    báo lên chứ không nuốt.

Các workbook ở đây dựng bằng openpyxl theo ĐÚNG bố cục file thật (xem
``_router_sheet``), nên bài test không phụ thuộc một file nhị phân nào.
"""
import pytest
from io import BytesIO

from openpyxl import Workbook, load_workbook

from mesflow.web.excel_io import _parse_go_router_template

# Cách bố cục một block Operation trong tờ router thật, tính từ dòng tiêu đề:
#   +0  A='OPERATION # NN- TÊN'
#   +1  A='Part Number ( Mã bản vẽ )'        B=<mã>
#   +2  A='Ngày/Tháng/Năm'                   L='Thời gian Setup ( phút )'
#   +3  A='SETUP'                            L=<số phút>
#   +4  A='Nhân viên Setup'
#   +5  A='Ngày/Tháng/Năm'                   L='Thời gian gia công / sản phẩm (s)'
#   +6  A='Thời gian gia công'               L=<giây/sp>
BLOCK_HEIGHT = 12
FIRST_BLOCK_ROW = 8


def _router_sheet(wb, title, drawing_code, blocks):
    """Một sheet Part đúng bố cục xưởng. ``blocks`` = [(seq, tên, setup, cycle)]."""
    ws = wb.create_sheet(title)
    ws['A2'] = 'PO NUMBER:'; ws['C2'] = 6126
    ws['A3'] = 'QTY:'; ws['C3'] = 110
    ws['A4'] = 'TÊN BẢN VẼ:'; ws['C4'] = title
    ws['A5'] = 'MÃ BẢN VẼ:'; ws['C5'] = drawing_code
    row = FIRST_BLOCK_ROW
    for seq, name, setup_value, cycle_value in blocks:
        ws.cell(row=row, column=1, value=f'OPERATION # {seq:02d}- {name}')
        ws.cell(row=row + 1, column=1, value='Part Number ( Mã bản vẽ )')
        ws.cell(row=row + 1, column=2, value=drawing_code)
        ws.cell(row=row + 2, column=1, value='Ngày/Tháng/Năm')
        ws.cell(row=row + 2, column=12, value='Thời gian Setup ( phút )')
        ws.cell(row=row + 3, column=1, value='SETUP')
        ws.cell(row=row + 3, column=12, value=setup_value)
        ws.cell(row=row + 4, column=1, value='Nhân viên Setup')
        ws.cell(row=row + 5, column=1, value='Ngày/Tháng/Năm')
        ws.cell(row=row + 5, column=12, value='Thời gian gia công / sản phẩm (s)')
        ws.cell(row=row + 6, column=1, value='Thời gian gia công')
        ws.cell(row=row + 6, column=12, value=cycle_value)
        for offset, label in enumerate(('Hàng đạt:', 'Hàng lỗi:', 'Tổng số lượng sản xuất:',
                                        'Nhân viên SX:', 'Nhân viên QC:'), start=7):
            ws.cell(row=row + offset, column=1, value=label)
        row += BLOCK_HEIGHT
    return ws


def _workbook(sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for title, drawing_code, blocks in sheets:
        _router_sheet(wb, title, drawing_code, blocks)
    # Đi qua bytes để đọc lại y như file người dùng upload.
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    return load_workbook(buffer, data_only=True)


def _parse(sheets, filename='Lộ trình sản xuất TEST.xlsx'):
    return _parse_go_router_template(_workbook(sheets), filename)


def _by_code(parsed):
    return {op['code']: op for op in parsed['operations']}


# --- sinh OP SETUP --------------------------------------------------------

@pytest.mark.parametrize('minutes', [20, 120, 1, 999])
def test_setup_duong_thi_sinh_op_setup(minutes):
    """Bất kỳ số phút > 0 nào cũng phải bật requires_setup và giữ nguyên số."""
    parsed = _parse([('Chân ghế A', 'KM-001', [(1, 'CẮT LASER', minutes, 100)])])
    op = _by_code(parsed)['KM-001-OP01']
    assert op['requires_setup'] is True
    assert op['expected_setup_minutes'] == minutes


@pytest.mark.parametrize('empty_value', [0, None, '', '-', '–', 'x', 'N/A', 'không'])
def test_setup_bang_khong_hoac_trong_thi_khong_sinh_setup(empty_value):
    """0, ô trống, và các cách xưởng viết "không có" đều KHÔNG tạo OP SETUP.

    Dấu '-' không phải dữ liệu hỏng: file NEWARK thật dùng nó ở sheet 'Gân tăng
    cường cung ghế lớn' để nói công đoạn đó không phải set máy. Từ chối cả file
    44 sheet vì một dấu gạch là biến tính năng thành không dùng được.
    """
    parsed = _parse([('Chân ghế A', 'KM-001', [(1, 'LÀM NGUỘI', empty_value, 50)])])
    op = _by_code(parsed)['KM-001-OP01']
    assert op['requires_setup'] is False
    assert op['expected_setup_minutes'] is None


@pytest.mark.parametrize('bad_value', [-1, -20, -0.5])
def test_setup_am_bi_tu_choi_chu_khong_lam_tron_ve_khong(bad_value):
    """Số âm là dữ liệu sai, phải báo -- không được im lặng coi như 'không có'."""
    with pytest.raises(ValueError) as excinfo:
        _parse([('Chân ghế A', 'KM-001', [(1, 'CẮT LASER', bad_value, 100)])])
    message = str(excinfo.value)
    assert 'không được âm' in message
    # Người đọc đang mở file: thông báo phải chỉ đúng sheet và dòng.
    assert "Chân ghế A" in message and 'dòng 8' in message


@pytest.mark.parametrize('bad_value', ['hai mươi', '20 phút', '??'])
def test_setup_khong_doc_duoc_thi_bao_loi_co_vi_tri(bad_value):
    with pytest.raises(ValueError) as excinfo:
        _parse([('Chân ghế A', 'KM-001', [(1, 'CẮT LASER', bad_value, 100)])])
    message = str(excinfo.value)
    assert 'phải là số' in message
    assert "Chân ghế A" in message and 'dòng 8' in message


# --- neo nhãn, nhiều block, nhiều sheet -----------------------------------

def test_moi_block_doc_dung_so_cua_chinh_no():
    """Nhãn 'Thời gian Setup' lặp ở MỌI block, nên phải đọc trong phạm vi block.

    Đây là lỗi dễ mắc nhất: tìm nhãn trên cả sheet thì block nào cũng nhận số
    của block ĐẦU TIÊN, và một file có 3 công đoạn sẽ ra 3 OP setup 20 phút.
    """
    parsed = _parse([('Chân ghế A', 'KM-001', [
        (1, 'CẮT LASER', 20, 100),
        (2, 'LÀM NGUỘI', 0, 50),
        (3, 'XOẮN CHÂN GHẾ', 40, 120),
    ])])
    ops = _by_code(parsed)
    assert ops['KM-001-OP01']['expected_setup_minutes'] == 20
    assert ops['KM-001-OP02']['requires_setup'] is False
    assert ops['KM-001-OP03']['expected_setup_minutes'] == 40
    # Thời gian gia công cũng phải theo block của nó.
    assert ops['KM-001-OP01']['standard_seconds_per_unit'] == 100
    assert ops['KM-001-OP02']['standard_seconds_per_unit'] == 50
    assert ops['KM-001-OP03']['standard_seconds_per_unit'] == 120


def test_nhieu_sheet_moi_part_giu_so_cua_rieng_minh():
    """Hai Part cùng có 'OPERATION # 01' là hợp lệ và KHÔNG được lẫn số."""
    parsed = _parse([
        ('Chân ghế A', 'KM-001', [(1, 'CẮT LASER', 20, 100)]),
        ('HÀN ROBOT - Hàn vòng đệm', 'KM-002', [(1, 'HÀN ROBOT', 120, 120)]),
    ])
    ops = _by_code(parsed)
    assert ops['KM-001-OP01']['expected_setup_minutes'] == 20
    assert ops['KM-002-OP01']['expected_setup_minutes'] == 120
    assert {op['_excel_sheet'] for op in parsed['operations']} == {
        'Chân ghế A', 'HÀN ROBOT - Hàn vòng đệm'}


def test_block_khong_co_nhan_setup_thi_khong_khai_bao_gi():
    """Không có nhãn setup = file KHÔNG nói gì, khác hẳn file nói 'setup = 0'.

    Phân biệt này quyết định lúc nhập lại: file có khai báo thì file thắng cấu
    hình trên web, file không nói gì thì giữ nguyên cấu hình người ta đã đặt tay.
    """
    wb = Workbook(); wb.remove(wb.active)
    ws = wb.create_sheet('Chân ghế A')
    ws['A2'] = 'PO NUMBER:'; ws['C2'] = 6126
    ws['A5'] = 'MÃ BẢN VẼ:'; ws['C5'] = 'KM-001'
    ws['A8'] = 'OPERATION # 01- CẮT LASER'
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    parsed = _parse_go_router_template(load_workbook(buffer, data_only=True), 'x.xlsx')
    op = _by_code(parsed)['KM-001-OP01']
    assert op['_setup_declared'] is False
    assert op['requires_setup'] is False


# --- danh tính Operation ---------------------------------------------------

def test_ma_op_trung_trong_cung_part_duoc_ghi_nhan_de_chan():
    """Trùng số trong CÙNG một Part: parser ghi nhận, không tự sửa.

    Một Part không thể có hai công đoạn số 02. Parser KHÔNG đẻ ra mã thứ hai để
    cho qua -- làm vậy là hợp thức hoá lỗi. Nó ghi lại đủ tờ/Part/số/hai dòng,
    và tầng nhập biến cái đó thành lỗi chặn.
    """
    parsed = _parse([('Thanh la khung ngồi', 'KM-317', [
        (1, 'CẮT LASER', 20, 100),
        (2, 'CHAMFER LỖ', 0, 40),
        (2, 'LÀM NGUỘI', 0, 50),
    ])])
    duplicates = [n for n in parsed['notes'] if n['kind'] == 'DUPLICATE_OP_IN_PART']
    assert len(duplicates) == 1
    note = duplicates[0]
    assert note['part'] == 'KM-317'
    assert note['op_code'] == 'OP02'
    # Cả hai dòng đụng nhau, không chỉ dòng thứ hai.
    assert note['first_row'] == 20 and note['row'] == 32
    # Và KHÔNG có mã nào bị đẻ thêm hậu tố.
    assert all('-2' not in op['code'] for op in parsed['operations'])
    assert [op['code'] for op in parsed['operations']] == [
        'KM-317-OP01', 'KM-317-OP02', 'KM-317-OP02']

def test_ma_op_trung_giua_hai_part_khac_nhau_la_hop_le():
    """OP01 ở Part khác KHÔNG phải va chạm -- không được cảnh báo nhầm."""
    parsed = _parse([
        ('Chân ghế A', 'KM-001', [(1, 'CẮT LASER', 20, 100)]),
        ('Chân ghế B', 'KM-002', [(1, 'CẮT LASER', 20, 100)]),
    ])
    assert parsed['notes'] == []
    assert sorted(_by_code(parsed)) == ['KM-001-OP01', 'KM-002-OP01']


def test_nhap_lai_cung_file_cho_ket_qua_y_het():
    """Idempotent ở mức parser: cùng bytes vào thì cùng mã và cùng setup ra.

    Nếu hậu tố tách trùng phụ thuộc thứ tự dict hay thời điểm chạy thì lần nhập
    thứ hai sẽ tạo ra Operation mang mã khác -- tức là nhân đôi dữ liệu.
    """
    sheets = [('Thanh la khung ngồi', 'KM-317', [
        (1, 'CẮT LASER', 20, 100), (2, 'CHAMFER LỖ', 0, 40), (2, 'LÀM NGUỘI', 0, 50)])]
    first, second = _parse(sheets), _parse(sheets)
    fields = ('code', 'name', 'requires_setup', 'expected_setup_minutes',
              'standard_seconds_per_unit', 'sort_order')
    assert ([{k: op[k] for k in fields} for op in first['operations']]
            == [{k: op[k] for k in fields} for op in second['operations']])
    assert first['notes'] == second['notes']


def test_file_khong_co_setup_van_nhap_duoc_nhu_cu():
    """Hồi quy: workbook cũ (không có ô setup nào) không được vỡ."""
    wb = Workbook(); wb.remove(wb.active)
    ws = wb.create_sheet('Chân ghế A')
    ws['A2'] = 'PO NUMBER:'; ws['C2'] = 6126
    ws['A5'] = 'MÃ BẢN VẼ:'; ws['C5'] = 'KM-001'
    for index, (row, name) in enumerate(((8, 'CẮT LASER'), (20, 'LÀM NGUỘI')), start=1):
        ws.cell(row=row, column=1, value=f'OPERATION # {index:02d}- {name}')
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    parsed = _parse_go_router_template(load_workbook(buffer, data_only=True), 'x.xlsx')
    assert len(parsed['operations']) == 2
    assert all(op['requires_setup'] is False for op in parsed['operations'])
    assert parsed['notes'] == []
