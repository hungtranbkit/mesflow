"""Tờ Lộ trình sản xuất xuất ra phải mang tem QR quét được cho MỌI Operation.

BỐI CẢNH. Xưởng làm việc trên tờ router in ra. Trước đây tờ đó chỉ đi một
chiều -- từ Excel vào MESFlow -- nên muốn dán tem QR lên máy thì phải in riêng
từ màn "Danh sách QR Code" rồi tự ghép vào đúng công đoạn bằng tay.

Bài test khoá những thứ mà hỏng thì người đứng máy chỉ phát hiện khi đã cầm tờ
giấy sai:

  * QR là ảnh PNG THẬT, và GIẢI MÃ ngược lại đúng payload đã yêu cầu;
  * payload là danh tính canonical, không phải mã OP tự ghép;
  * tem không đè lên bất kỳ ô có chữ nào;
  * có tem Setup KHI VÀ CHỈ KHI Operation đó thật sự có OP SETUP liên kết;
  * mọi Operation của PO đều có tem, kể cả OP không có trong workbook gốc;
  * hai sheet cùng tên công đoạn không dùng chung một tem.

Phần giải mã không cần thư viện ngoài: ``_decode_qr_matrix`` dựng lại ma trận
module từ chính pixel của ảnh rồi so với ma trận mà ``qrcode`` sinh ra cho
payload mong đợi. Nếu ảnh méo, sai cỡ, hay mã hoá nhầm chuỗi thì so sánh này
trượt -- đúng tinh thần "tem in ra quét được", chứ không phải "hàm có chạy".
"""
import pytest
from io import BytesIO

from pathlib import Path

from openpyxl import Workbook, load_workbook

from mesflow.web.router_export import (
    EXTRA_SHEET_TITLE, QR_OP_LABEL, QR_SETUP_LABEL, RouterSourceUnavailable,
    _place_qr, _qr_lane_column, _qr_png, _stamp_source_workbook)

PIL = pytest.importorskip('PIL', reason='Pillow là dependency của tính năng xuất QR')
from PIL import Image  # noqa: E402


def _decode_qr_matrix(png_bytes):
    """Ma trận module đọc NGƯỢC từ pixel của ảnh PNG."""
    image = Image.open(BytesIO(png_bytes)).convert('L')
    width, height = image.size
    assert width == height, f'QR phải vuông, đang là {width}x{height}'
    import qrcode
    probe = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    probe.add_data('x')
    probe.make(fit=True)
    # Suy ra cạnh module từ ảnh: ảnh = (modules + 2*border) * box_size.
    for box_size in range(2, 12):
        if width % box_size:
            continue
        side = width // box_size
        matrix = []
        for row in range(side):
            line = []
            for col in range(side):
                pixel = image.getpixel((col * box_size + box_size // 2,
                                        row * box_size + box_size // 2))
                line.append(pixel < 128)
            matrix.append(line)
        # Viền trắng bắt buộc: nếu chọn sai box_size thì hàng đầu không trắng hết.
        if not any(matrix[0]) and not any(row[0] for row in matrix):
            return matrix
    raise AssertionError('Không dựng lại được ma trận QR từ ảnh')


def _expected_matrix(payload):
    import qrcode
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload)
    qr.make(fit=True)
    return [[bool(cell) for cell in row] for row in qr.get_matrix()]


def _row(op_id, code, name, *, part_code='KM-001', part_name='Chân ghế A',
         setup_id=None, setup_minutes=None, cycle=100, part_id=1, part_sort=0,
         sort_order=0):
    """Một dòng như _load_po_operations() trả về."""
    return {
        'id': op_id, 'code': code, 'name': name, 'sort_order': sort_order,
        'standard_seconds_per_unit': cycle, 'requires_setup': bool(setup_id),
        'expected_setup_minutes': setup_minutes,
        'part_id': part_id, 'part_code': part_code, 'part_name': part_name,
        'part_sort': part_sort,
        'op_qr': f'WF|OPID|{op_id}',
        'setup_id': setup_id, 'setup_code': f'{code}-SU' if setup_id else None,
        'setup_name': f'Setup {name}' if setup_id else None,
        'setup_minutes': setup_minutes,
        'setup_qr': f'WF|OPID|{setup_id}' if setup_id else None,
    }


PO = {'id': 1, 'code': 'PO-6126', 'name': 'NEWARK', 'plan_qty': 110,
      'source_template_id': 7}


# --- ảnh QR ---------------------------------------------------------------

@pytest.mark.parametrize('payload', [
    'WF|OPID|1', 'WF|OPID|4242', 'WF|OPID|999999', 'WF|OP|KM-001-OP01'])
def test_qr_giai_ma_nguoc_lai_dung_payload(payload):
    """Ảnh sinh ra phải giải mã ngược về đúng chuỗi -- không chỉ 'là một ảnh'."""
    raw = _qr_png(payload).getvalue()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n', 'phải là PNG thật'
    assert _decode_qr_matrix(raw) == _expected_matrix(payload)


def test_qr_du_lon_de_quet_duoc_khi_in():
    """Tem nhỏ hơn ~1,8 cm là bắt đầu phụ thuộc máy in; khoá sàn kích thước."""
    for payload in ('WF|OPID|1', 'WF|OPID|' + '9' * 12):
        image = Image.open(BytesIO(_qr_png(payload).getvalue()))
        width, _ = image.size
        # 3 px/module ở 96 DPI, QR nhỏ nhất 25 module kể cả viền -> >= 75 px.
        assert width >= 75, f'{payload}: tem chỉ {width}px, quá nhỏ để in'


def test_qr_khong_bi_noi_suy():
    """Cạnh ảnh phải chia hết cho số module: không có phóng to lẻ làm nhoè."""
    raw = _qr_png('WF|OPID|4242').getvalue()
    width, _ = Image.open(BytesIO(raw)).size
    matrix = _decode_qr_matrix(raw)
    assert width % len(matrix) == 0


# --- vị trí tem -----------------------------------------------------------

def _sheet_with_text(max_column):
    wb = Workbook()
    ws = wb.active
    for column in range(1, max_column + 1):
        ws.cell(row=8, column=column, value=f'nội dung {column}')
    return ws


@pytest.mark.parametrize('max_column', [3, 13, 20])
def test_lan_qr_luon_nam_ngoai_vung_co_chu(max_column):
    """Lời hứa 'không đè chữ' được giữ bằng cấu trúc, không bằng mắt."""
    ws = _sheet_with_text(max_column)
    assert _qr_lane_column(ws) > max_column


def test_tem_khong_de_len_o_nao_co_chu():
    """Đóng tem xong, mọi ô có chữ phải vẫn nguyên giá trị cũ."""
    ws = _sheet_with_text(13)
    ws.cell(row=10, column=12, value='Thời gian Setup ( phút )')
    ws.cell(row=11, column=12, value=20)
    before = {(c.row, c.column): c.value for r in ws.iter_rows() for c in r
              if c.value not in (None, '')}
    column = _qr_lane_column(ws)
    _place_qr(ws, 'WF|OPID|1', QR_OP_LABEL, row=8, column=column)
    _place_qr(ws, 'WF|OPID|2', QR_SETUP_LABEL, row=8, column=column + 2)
    after = {(c.row, c.column): c.value for r in ws.iter_rows() for c in r
             if c.value not in (None, '')}
    for position, value in before.items():
        assert after[position] == value, f'ô {position} bị tem ghi đè'
    # Ảnh phải neo trong làn QR, không lùi vào vùng dữ liệu. openpyxl giữ neo
    # dưới dạng chuỗi ô ('N9') cho tới lúc lưu, nên đọc chữ cái cột từ chuỗi.
    import re as _re
    from openpyxl.utils import column_index_from_string
    for image in ws._images:
        letter = _re.match(r'([A-Z]+)', str(image.anchor)).group(1)
        assert column_index_from_string(letter) >= column


# --- workbook sinh ra ------------------------------------------------------

def _saved(wb):
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    return load_workbook(buffer)


def test_moi_operation_deu_co_tem_va_setup_chi_khi_co_lien_ket():
    rows = [
        _row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', setup_id=201, setup_minutes=20),
        _row(102, 'PO-6126-KM-001-OP02', 'LÀM NGUỘI', sort_order=1),
    ]
    wb, placed, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    kinds = {(p['operation_id'], p['kind']) for p in placed}
    assert (101, 'OP') in kinds and (102, 'OP') in kinds
    assert (201, 'SETUP') in kinds
    # OP không có setup thì TUYỆT ĐỐI không được sinh tem setup.
    assert not any(p['kind'] == 'SETUP' and p['operation_id'] == 102 for p in placed)
    assert sum(1 for p in placed if p['kind'] == 'SETUP') == 1
    assert _saved(wb)  # mở lại được bằng openpyxl


def test_payload_khong_trung_va_khong_mo_ho():
    """Mỗi tem trỏ tới đúng một Operation; không có hai tem cùng chuỗi."""
    rows = [
        _row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', setup_id=201, setup_minutes=20),
        _row(102, 'PO-6126-KM-002-OP01', 'CẮT LASER', part_code='KM-002',
             part_name='Chân ghế B', part_id=2, part_sort=1, setup_id=202,
             setup_minutes=20),
    ]
    _, placed, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    payloads = [p['payload'] for p in placed]
    assert len(payloads) == len(set(payloads)), 'có hai tem mang cùng payload'
    # Hai Part cùng tên công đoạn 'CẮT LASER' -> tem phải khác nhau.
    assert {p['payload'] for p in placed if p['kind'] == 'OP'} == {
        'WF|OPID|101', 'WF|OPID|102'}


def test_nhan_tem_la_tieng_viet_ro_rang():
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', setup_id=201, setup_minutes=20)]
    wb, _, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    values = {c.value for r in _saved(wb)['Chân ghế A'].iter_rows() for c in r}
    assert QR_OP_LABEL in values and QR_SETUP_LABEL in values
    assert 'QR OP' == QR_OP_LABEL and 'QR Setup' == QR_SETUP_LABEL


def test_moi_sheet_part_giu_tem_cua_rieng_no():
    rows = [
        _row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER'),
        _row(102, 'PO-6126-KM-002-OP01', 'CẮT LASER', part_code='KM-002',
             part_name='Chân ghế B', part_id=2, part_sort=1),
    ]
    _, placed, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    by_sheet = {}
    for item in placed:
        by_sheet.setdefault(item['sheet'], set()).add(item['payload'])
    assert by_sheet == {'Chân ghế A': {'WF|OPID|101'}, 'Chân ghế B': {'WF|OPID|102'}}


def test_khong_con_duong_dung_workbook_moi():
    """Hợp đồng: xuất file CHỈ đi qua workbook gốc, không có nhánh dựng lại.

    Tờ router là biểu mẫu của khách (khung in, logo, ô ký, công thức tính giờ).
    Một file "tương đương" trông giống nhưng không phải cái xưởng đang dùng, và
    người cầm tờ giấy không có cách nào biết mình đang cầm bản nào -- nên thiếu
    file gốc phải là LỖI, không phải rơi về bản tự dựng.
    """
    import mesflow.web.router_export as module
    assert not hasattr(module, '_generate_router_workbook')
    source = Path(module.__file__).read_text(encoding='utf-8')
    assert 'Workbook()' not in source, 'không được dựng workbook mới ở đây'
    assert 'RouterSourceUnavailable' in source


# --- đóng tem lên workbook gốc --------------------------------------------

def _source_bytes():
    """Workbook gốc tối giản đúng bố cục xưởng, cho hai Part."""
    wb = Workbook(); wb.remove(wb.active)
    for title, code, name in (('Chân ghế A', 'KM-001', 'CẮT LASER'),
                              ('Chân ghế B', 'KM-002', 'CẮT LASER')):
        ws = wb.create_sheet(title)
        ws['A2'] = 'PO NUMBER:'; ws['C2'] = 6126
        ws['A5'] = 'MÃ BẢN VẼ:'; ws['C5'] = code
        ws['A8'] = f'OPERATION # 01- {name}'
        ws['A9'] = 'Part Number ( Mã bản vẽ )'; ws['B9'] = code
        ws['A10'] = 'Ngày/Tháng/Năm'; ws['L10'] = 'Thời gian Setup ( phút )'
        ws['A11'] = 'SETUP'; ws['L11'] = 20
    buffer = BytesIO(); wb.save(buffer)
    return buffer.getvalue()


def test_dong_tem_len_file_goc_giu_nguyen_o_du_lieu():
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', setup_id=201, setup_minutes=20)]
    wb, placed, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    ws = _saved(wb)['Chân ghế A']
    assert ws['L10'].value == 'Thời gian Setup ( phút )'
    assert ws['L11'].value == 20
    assert ws['A8'].value == 'OPERATION # 01- CẮT LASER'
    assert {p['operation_id'] for p in placed} == {101, 201}


def test_tem_nam_dung_tren_sheet_cua_block_chu_khong_roi_xuong_sheet_phu():
    """Mã Operation thật mang tiền tố PO; quên gỡ là tem rơi hết xuống sheet phụ.

    Lỗi đã thực sự xảy ra trên file NEWARK: cả 159 tem xuống 'QR bổ sung' mà
    TỔNG SỐ tem vẫn đủ, nên phép đếm không phát hiện được gì. Vì vậy bài này
    khoá NƠI tem nằm, không chỉ khoá số lượng.
    """
    rows = [
        _row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', setup_id=201, setup_minutes=20),
        _row(102, 'PO-6126-KM-002-OP01', 'CẮT LASER', part_code='KM-002',
             part_name='Chân ghế B', part_id=2, part_sort=1),
    ]
    wb, placed, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    assert EXTRA_SHEET_TITLE not in _saved(wb).sheetnames, (
        'mọi Operation đều có block trong file gốc, không được sinh sheet phụ')
    sheets = {p['operation_id']: p['sheet'] for p in placed}
    assert sheets[101] == 'Chân ghế A' and sheets[201] == 'Chân ghế A'
    assert sheets[102] == 'Chân ghế B'


def test_ma_op_khong_mang_tien_to_po_van_khop_duoc():
    """Template đặt mã tự do (không có tiền tố PO) vẫn phải khớp block."""
    rows = [_row(101, 'KM-001-OP01', 'CẮT LASER')]
    wb, placed, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    assert EXTRA_SHEET_TITLE not in _saved(wb).sheetnames
    assert placed[0]['sheet'] == 'Chân ghế A'


def test_operation_khong_co_trong_file_goc_van_duoc_tem():
    """OP thêm tay sau khi nhập vẫn phải có tem -- gom vào sheet phụ.

    Bỏ qua lặng lẽ thì người cầm tờ giấy thiếu đúng tem họ cần mà không biết.
    """
    rows = [
        _row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER'),
        _row(103, 'PO-6126-KM-009-OP01', 'CÔNG ĐOẠN THÊM TAY', part_code='KM-009',
             part_name='Part thêm tay', part_id=9, part_sort=5, setup_id=203,
             setup_minutes=15),
    ]
    wb, placed, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    assert {p['operation_id'] for p in placed} == {101, 103, 203}
    saved = _saved(wb)
    assert EXTRA_SHEET_TITLE in saved.sheetnames
    leftover = {p['sheet'] for p in placed if p['operation_id'] in (103, 203)}
    assert leftover == {EXTRA_SHEET_TITLE}


def test_xuat_lai_lan_hai_khong_chong_tem_cu():
    """Xuất lại từ file đã xuất không được nhân đôi sheet phụ."""
    rows = [_row(103, 'PO-6126-KM-009-OP01', 'THÊM TAY', part_code='KM-009',
                 part_name='Part thêm tay', part_id=9)]
    wb, _, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    buffer = BytesIO(); wb.save(buffer)
    wb2, placed2, _, _ = _stamp_source_workbook(buffer.getvalue(), PO, rows)
    titles = _saved(wb2).sheetnames
    assert titles.count(EXTRA_SHEET_TITLE) == 1
    assert len(placed2) == 1
