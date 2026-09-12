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
    QR_OP_LABEL, QR_SETUP_LABEL, RouterSourceUnavailable, _place_qr,
    _qr_lane_column, _qr_png, _router_filename, _stamp_source_workbook)

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


def test_dong_tem_khong_cham_vao_bat_ky_o_nao():
    """Sau khi đóng tem, TOÀN BỘ ô của sheet phải y hệt trước đó.

    Không chỉ "không đè chữ": không một cell nào được ghi, kể cả ô trống, và
    bề rộng cột / chiều cao dòng cũng không đổi.
    """
    ws = _sheet_with_text(13)
    ws.cell(row=10, column=12, value='Thời gian Setup ( phút )')
    ws.cell(row=11, column=12, value=20)
    snapshot = {(c.row, c.column): c.value for r in ws.iter_rows() for c in r}
    widths = {k: v.width for k, v in ws.column_dimensions.items()}
    heights = {k: v.height for k, v in ws.row_dimensions.items()}

    column = _qr_lane_column(ws)
    _place_qr(ws, 'WF|OPID|1', QR_OP_LABEL, row=8, column=column)
    _place_qr(ws, 'WF|OPID|2', QR_SETUP_LABEL, row=8, column=column + 2)

    assert {(c.row, c.column): c.value for r in ws.iter_rows() for c in r} == snapshot
    assert {k: v.width for k, v in ws.column_dimensions.items()} == widths
    assert {k: v.height for k, v in ws.row_dimensions.items()} == heights
    assert len(ws._images) == 2
    import re as _re
    from openpyxl.utils import column_index_from_string
    for image in ws._images:
        letter = _re.match(r'([A-Z]+)', str(image.anchor)).group(1)
        assert column_index_from_string(letter) >= column


def test_khong_co_cho_dat_tem_thi_bao_loi_chu_khong_sua_cau_truc():
    """Hết chỗ trống -> LỖI kèm sheet + Operation, không tự chèn cột lấy chỗ."""
    from mesflow.web.router_export import RouterPlacementError, _assert_lane_is_free
    ws = _sheet_with_text(13)
    with pytest.raises(RouterPlacementError) as excinfo:
        _assert_lane_is_free(ws, 10, 4, sheet='Chân ghế A', operation='KM-001-OP01')
    error = excinfo.value
    assert error.reason == 'NO_FREE_COLUMN'
    assert error.sheet == 'Chân ghế A' and error.operation == 'KM-001-OP01'
    assert 'Chân ghế A' in str(error) and 'KM-001-OP01' in str(error)


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
    assert _saved(wb).sheetnames == ['Chân ghế A', 'Chân ghế B']


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


def test_nhan_tem_duoc_nuong_vao_anh_chu_khong_ghi_vao_o():
    """Nhãn "QR OP"/"QR Setup" phải nằm TRONG ảnh, không phải trong cell.

    Ghi chữ vào ô -- kể cả ô đang trống -- là sửa nội dung biểu mẫu của khách.
    Ảnh có nhãn thì cao hơn ảnh trần đúng bằng dải chữ, và sheet không nhận
    thêm một ký tự nào.
    """
    from mesflow.web.router_export import QR_LABEL_STRIP
    plain = Image.open(BytesIO(_qr_png('WF|OPID|1').getvalue()))
    labelled = Image.open(BytesIO(_qr_png('WF|OPID|1', QR_OP_LABEL).getvalue()))
    assert labelled.height == plain.height + QR_LABEL_STRIP
    assert labelled.width == plain.width
    # Dải nhãn phải có mực thật, không phải một dải trắng.
    strip = labelled.crop((0, plain.height, labelled.width, labelled.height))
    assert any(pixel == 0 for pixel in strip.convert('L').getdata()), 'nhãn trống trơn'

    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', setup_id=201, setup_minutes=20)]
    wb, _, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    values = {c.value for r in _saved(wb)['Chân ghế A'].iter_rows() for c in r}
    assert QR_OP_LABEL not in values and QR_SETUP_LABEL not in values


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
    """Workbook gốc tối giản đúng bố cục xưởng: Part A có hai OP, Part B một OP."""
    wb = Workbook(); wb.remove(wb.active)
    layout = (('Chân ghế A', 'KM-001', [('CẮT LASER', 20), ('LÀM NGUỘI', 0)]),
              ('Chân ghế B', 'KM-002', [('CẮT LASER', 20)]))
    for title, code, blocks in layout:
        ws = wb.create_sheet(title)
        ws['A2'] = 'PO NUMBER:'; ws['C2'] = 6126
        ws['A5'] = 'MÃ BẢN VẼ:'; ws['C5'] = code
        row = 8
        for index, (name, minutes) in enumerate(blocks, start=1):
            ws.cell(row=row, column=1, value=f'OPERATION # {index:02d}- {name}')
            ws.cell(row=row + 1, column=1, value='Part Number ( Mã bản vẽ )')
            ws.cell(row=row + 1, column=2, value=code)
            ws.cell(row=row + 2, column=1, value='Ngày/Tháng/Năm')
            ws.cell(row=row + 2, column=12, value='Thời gian Setup ( phút )')
            ws.cell(row=row + 3, column=1, value='SETUP')
            ws.cell(row=row + 3, column=12, value=minutes)
            row += 12
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
    assert _saved(wb).sheetnames == ['Chân ghế A', 'Chân ghế B'], (
        'không sheet nào được thêm vào file gốc')
    sheets = {p['operation_id']: p['sheet'] for p in placed}
    assert sheets[101] == 'Chân ghế A' and sheets[201] == 'Chân ghế A'
    assert sheets[102] == 'Chân ghế B'


def test_ma_op_khong_mang_tien_to_po_van_khop_duoc():
    """Template đặt mã tự do (không có tiền tố PO) vẫn phải khớp block."""
    rows = [_row(101, 'KM-001-OP01', 'CẮT LASER')]
    wb, placed, _, _ = _stamp_source_workbook(_source_bytes(), PO, rows)
    assert _saved(wb).sheetnames == ['Chân ghế A', 'Chân ghế B']
    assert placed[0]['sheet'] == 'Chân ghế A'


def test_operation_khong_co_trong_file_goc_bi_tra_ve_de_bao_loi():
    """OP thêm tay sau khi nhập KHÔNG được âm thầm bỏ qua, cũng không gom sheet phụ.

    Xuất thiếu mà vẫn ra file là thứ người cầm tờ giấy không phát hiện được: họ
    ra xưởng, tới công đoạn đó, và không có tem để quét. Hàm này trả nguyên dòng
    chưa khớp về cho người gọi để nó dựng câu lỗi chỉ đúng Part/Operation.
    """
    rows = [
        _row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER'),
        _row(103, 'PO-6126-KM-009-OP01', 'CÔNG ĐOẠN THÊM TAY', part_code='KM-009',
             part_name='Part thêm tay', part_id=9, part_sort=5, setup_id=203,
             setup_minutes=15),
    ]
    wb, placed, matched, unmatched = _stamp_source_workbook(_source_bytes(), PO, rows)
    assert matched == 1
    assert [row['code'] for row in unmatched] == ['PO-6126-KM-009-OP01']
    # Không có sheet nào được thêm vào để che chỗ thiếu.
    assert _saved(wb).sheetnames == ['Chân ghế A', 'Chân ghế B']
    assert {p['operation_id'] for p in placed} == {101}


def test_khong_con_sheet_bo_sung_trong_ma_nguon():
    """Hợp đồng: không có đường nào tạo sheet gom tem cho phần không khớp."""
    import mesflow.web.router_export as module
    assert not hasattr(module, 'EXTRA_SHEET_TITLE')
    assert not hasattr(module, '_append_leftover_sheet')
    source = Path(module.__file__).read_text(encoding='utf-8')
    assert 'QR bổ sung' not in source
    assert 'create_sheet' not in source, 'không được thêm sheet nào vào file gốc'


# --- tên file theo PO -----------------------------------------------------

@pytest.mark.parametrize('po_code,expected', [
    ('PO-6126', 'Router_PO-6126_QR.xlsx'),
    ('PO 6126', 'Router_PO-6126_QR.xlsx'),
    ('PO/6126', 'Router_PO-6126_QR.xlsx'),
    ('NEWARK_2026.1', 'Router_NEWARK_2026.1_QR.xlsx'),
])
def test_ten_file_mang_ma_po_va_da_lam_sach(po_code, expected):
    assert _router_filename(po_code) == expected


@pytest.mark.parametrize('nasty', ['PO"; rm -rf /', 'PO\r\nX-Injected: 1', '../../etc/passwd'])
def test_ten_file_khong_cho_ky_tu_nguy_hiem_lot_vao_header(nasty):
    """Tên file đi thẳng vào Content-Disposition -- không được có dấu nháy/xuống dòng."""
    name = _router_filename(nasty)
    assert not set(name) & set('"\r\n/\\')
    assert name.startswith('Router_') and name.endswith('_QR.xlsx')
