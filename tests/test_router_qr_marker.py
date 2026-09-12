"""Template đặt sẵn ô ``QRCODE`` thì tem phải dán đúng vào ô đó.

BỐI CẢNH. Cách đặt tem hiện tại là hệ thống tự tìm một làn trống bên phải vùng
dữ liệu. Nó an toàn nhưng là PHỎNG ĐOÁN: phần mềm không biết tờ giấy in ra
trông thế nào, còn người vẽ biểu mẫu thì biết. Template thế hệ sau sẽ chừa sẵn
một ô ghi đúng chữ ``QRCODE`` trong từng block Operation, và hệ thống chỉ việc
dán tem của ĐÚNG Operation đó vào đúng ô ấy — không cần sửa code cho mỗi mẫu
giấy mới.

File router thật hiện tại CHƯA có marker, nên toàn bộ bài ở đây chạy trên
workbook tổng hợp. Điều đó cũng chính là lý do bài cuối cùng tồn tại: template
chưa có marker phải tiếp tục đi đường cũ, không được vỡ.

Cái được khoá:
  * marker trong block nào -> tem của Operation ấy, theo canonical operation.id;
  * marker nằm trong vùng SETUP của block -> tem SETUP, không phải tem OP cha;
  * có marker thì KHÔNG chạy heuristic làn trống cho tem đó;
  * marker mồ côi / trùng -> dừng hẳn, nêu sheet + ô + lý do;
  * ngoài ảnh QR và chính ô marker, workbook không đổi gì.
"""
import pytest
from io import BytesIO

from openpyxl import Workbook, load_workbook

from mesflow.web.router_export import (
    QR_MARKER_TEXT, RouterMarkerError, _stamp_source_workbook)

pytest.importorskip('PIL', reason='Pillow là dependency của tính năng xuất QR')

PO = {'id': 1, 'code': 'PO-6126', 'product': 'GHẾ', 'planned_quantity': 110,
      'source_template_id': 7}
BLOCK_HEIGHT = 12
FIRST_BLOCK_ROW = 8


def _sheet(wb, title, drawing_code, blocks):
    """Một sheet Part. ``blocks`` = [(tên OP, phút setup, marker_op, marker_setup)].

    ``marker_op`` / ``marker_setup`` là cột (số) để đặt chữ QRCODE, hoặc None.
    """
    ws = wb.create_sheet(title)
    ws['A2'] = 'PO NUMBER:'; ws['C2'] = 6126
    ws['A5'] = 'MÃ BẢN VẼ:'; ws['C5'] = drawing_code
    row = FIRST_BLOCK_ROW
    for index, (name, minutes, marker_op, marker_setup) in enumerate(blocks, start=1):
        ws.cell(row=row, column=1, value=f'OPERATION # {index:02d}- {name}')
        ws.cell(row=row + 1, column=1, value='Part Number ( Mã bản vẽ )')
        ws.cell(row=row + 1, column=2, value=drawing_code)
        ws.cell(row=row + 2, column=1, value='Ngày/Tháng/Năm')
        ws.cell(row=row + 2, column=12, value='Thời gian Setup ( phút )')
        ws.cell(row=row + 3, column=1, value='SETUP')
        ws.cell(row=row + 3, column=12, value=minutes)
        # Vùng SETUP của block là hai dòng +2..+4; marker setup đặt ở +3.
        if marker_setup:
            ws.cell(row=row + 3, column=marker_setup, value=QR_MARKER_TEXT)
        ws.cell(row=row + 5, column=1, value='Ngày/Tháng/Năm')
        ws.cell(row=row + 5, column=12, value='Thời gian gia công / sản phẩm (s)')
        ws.cell(row=row + 6, column=1, value='Thời gian gia công')
        ws.cell(row=row + 6, column=12, value=100)
        # Marker của OP sản xuất nằm NGOÀI vùng setup -> đặt ở dòng +6.
        if marker_op:
            ws.cell(row=row + 6, column=marker_op, value=QR_MARKER_TEXT)
        for offset, label in enumerate(('Hàng đạt:', 'Hàng lỗi:', 'Nhân viên SX:'), start=7):
            ws.cell(row=row + offset, column=1, value=label)
        row += BLOCK_HEIGHT
    return ws


def _workbook(sheets):
    wb = Workbook(); wb.remove(wb.active)
    for title, code, blocks in sheets:
        _sheet(wb, title, code, blocks)
    buffer = BytesIO(); wb.save(buffer)
    return buffer.getvalue()


def _row(op_id, code, name, *, part_code, part_name, setup_id=None, part_id=1,
         part_sort=0, sort_order=0):
    return {
        'id': op_id, 'code': code, 'name': name, 'sort_order': sort_order,
        'standard_seconds_per_unit': 100, 'requires_setup': bool(setup_id),
        'expected_setup_minutes': 20 if setup_id else None,
        'part_id': part_id, 'part_code': part_code, 'part_name': part_name,
        'part_sort': part_sort, 'op_qr': f'WF|OPID|{op_id}',
        'setup_id': setup_id, 'setup_code': f'{code}-SU' if setup_id else None,
        'setup_name': f'Setup {name}' if setup_id else None,
        'setup_minutes': 20 if setup_id else None,
        'setup_qr': f'WF|OPID|{setup_id}' if setup_id else None,
    }


# Hai Part, ba OP sản xuất, một trong số đó có SETUP -- đúng hình dạng
# contract yêu cầu thử.
TWO_PART_SHEETS = [
    ('Chân ghế A', 'KM-001', [('CẮT LASER', 20, 14, 16), ('LÀM NGUỘI', 0, 14, None)]),
    ('Chân ghế B', 'KM-002', [('HÀN ROBOT', 0, 14, None)]),
]
TWO_PART_ROWS = [
    _row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
         part_name='Chân ghế A', setup_id=201),
    _row(102, 'PO-6126-KM-001-OP02', 'LÀM NGUỘI', part_code='KM-001',
         part_name='Chân ghế A', sort_order=1),
    _row(103, 'PO-6126-KM-002-OP01', 'HÀN ROBOT', part_code='KM-002',
         part_name='Chân ghế B', part_id=2, part_sort=1),
]


def _stamp(sheets, rows):
    return _stamp_source_workbook(_workbook(sheets), PO, rows)


def _by_operation(placed):
    return {item['operation_id']: item for item in placed}


# --- dán đúng ô marker ----------------------------------------------------

def test_moi_op_duoc_dan_vao_dung_o_marker_cua_no():
    _, placed, matched, unmatched = _stamp(TWO_PART_SHEETS, TWO_PART_ROWS)
    assert matched == 3 and unmatched == []
    items = _by_operation(placed)
    # Block 1 ở dòng 8 -> marker OP ở dòng 14 (8+6), cột 14 = N.
    assert items[101]['anchor'] == 'N14'
    assert items[101]['placement'] == 'marker'
    assert items[101]['marker_cell'] == 'N14'
    # Block 2 ở dòng 20 -> marker OP ở dòng 26.
    assert items[102]['anchor'] == 'N26'
    # Part khác, block 1 của nó cũng ở dòng 8.
    assert items[103]['anchor'] == 'N14'
    assert items[103]['sheet'] == 'Chân ghế B'


def test_payload_van_la_danh_tinh_canonical_cua_dung_operation():
    _, placed, _, _ = _stamp(TWO_PART_SHEETS, TWO_PART_ROWS)
    items = _by_operation(placed)
    for operation_id in (101, 102, 103, 201):
        assert items[operation_id]['payload'] == f'WF|OPID|{operation_id}'
    payloads = [item['payload'] for item in placed]
    assert len(payloads) == len(set(payloads))


def test_marker_trong_vung_setup_cho_ra_tem_setup_khong_phai_tem_op_cha():
    """Marker nằm ở dòng SETUP -> tem của OP SETUP, không phải của OP sản xuất."""
    _, placed, _, _ = _stamp(TWO_PART_SHEETS, TWO_PART_ROWS)
    items = _by_operation(placed)
    setup = items[201]
    assert setup['kind'] == 'SETUP'
    assert setup['placement'] == 'marker'
    # Marker setup đặt ở cột 16 (P), dòng 8+3 = 11.
    assert setup['marker_cell'] == 'P11'
    assert setup['payload'] == 'WF|OPID|201'
    # Và tem OP cha vẫn đi vào marker riêng của nó, không lẫn.
    assert items[101]['marker_cell'] == 'N14'


def test_op_khong_co_setup_thi_khong_sinh_tem_setup():
    _, placed, _, _ = _stamp(TWO_PART_SHEETS, TWO_PART_ROWS)
    kinds = {(item['operation_id'], item['kind']) for item in placed}
    assert (201, 'SETUP') in kinds
    assert sum(1 for item in placed if item['kind'] == 'SETUP') == 1
    assert len(placed) == 4      # 3 OP + 1 SETUP


def test_co_marker_thi_khong_chay_heuristic_lan_trong():
    """Marker thắng tuyệt đối: không tem nào của OP đó đi theo làn trống."""
    _, placed, _, _ = _stamp(TWO_PART_SHEETS, TWO_PART_ROWS)
    assert all(item['placement'] == 'marker' for item in placed
               if item['operation_id'] in (101, 102, 103, 201))


def test_chu_marker_bi_xoa_de_khong_in_ra_giay():
    """Ô marker là chỗ DUY NHẤT được đổi nội dung -- và phải sạch chữ."""
    wb, placed, _, _ = _stamp(TWO_PART_SHEETS, TWO_PART_ROWS)
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    saved = load_workbook(buffer)
    for name in saved.sheetnames:
        values = {c.value for row in saved[name].iter_rows() for c in row}
        assert QR_MARKER_TEXT not in values, f'{name}: còn sót chữ {QR_MARKER_TEXT}'


def test_ngoai_anh_va_o_marker_workbook_khong_doi_gi():
    source = _workbook(TWO_PART_SHEETS)
    wb, placed, _, _ = _stamp_source_workbook(source, PO, TWO_PART_ROWS)
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    exported = load_workbook(buffer)
    original = load_workbook(BytesIO(source))

    assert exported.sheetnames == original.sheetnames
    marker_cells = {(item['sheet'], item['marker_cell']) for item in placed}
    for name in original.sheetnames:
        before, after = original[name], exported[name]
        assert {str(r) for r in before.merged_cells.ranges} == {
            str(r) for r in after.merged_cells.ranges}
        assert {k: v.width for k, v in before.column_dimensions.items()} == {
            k: v.width for k, v in after.column_dimensions.items()}
        assert {k: v.height for k, v in before.row_dimensions.items()} == {
            k: v.height for k, v in after.row_dimensions.items()}
        assert before.freeze_panes == after.freeze_panes
        assert before.page_setup.fitToWidth == after.page_setup.fitToWidth
        for row in before.iter_rows():
            for cell in row:
                if cell.value in (None, ''):
                    continue
                if (name, cell.coordinate) in marker_cells:
                    # Đúng một loại ô được phép đổi: chính ô đặt sẵn.
                    assert after[cell.coordinate].value is None
                    continue
                assert after[cell.coordinate].value == cell.value, (
                    f'{name}!{cell.coordinate} bị đổi ngoài ý muốn')
    added = sum(len(exported[n]._images) - len(original[n]._images)
                for n in original.sheetnames)
    assert added == len(placed)


def test_marker_trong_o_merged_neo_ve_goc_tren_trai_va_khong_doi_merge():
    wb = Workbook(); wb.remove(wb.active)
    _sheet(wb, 'Chân ghế A', 'KM-001', [('CẮT LASER', 0, 14, None)])
    ws = wb['Chân ghế A']
    ws.merge_cells(start_row=14, start_column=14, end_row=15, end_column=16)
    buffer = BytesIO(); wb.save(buffer)
    source = buffer.getvalue()

    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A')]
    exported, placed, _, _ = _stamp_source_workbook(source, PO, rows)
    assert placed[0]['anchor'] == 'N14'      # góc trên-trái của vùng merge
    out = BytesIO(); exported.save(out); out.seek(0)
    saved = load_workbook(out)
    assert {str(r) for r in saved['Chân ghế A'].merged_cells.ranges} == {'N14:P15'}


# --- marker hỏng thì DỪNG, không đoán -------------------------------------

def test_marker_ngoai_moi_block_bi_tu_choi():
    wb = Workbook(); wb.remove(wb.active)
    ws = _sheet(wb, 'Chân ghế A', 'KM-001', [('CẮT LASER', 0, None, None)])
    ws.cell(row=3, column=14, value=QR_MARKER_TEXT)   # trên cả block đầu tiên
    buffer = BytesIO(); wb.save(buffer)
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A')]
    with pytest.raises(RouterMarkerError) as excinfo:
        _stamp_source_workbook(buffer.getvalue(), PO, rows)
    error = excinfo.value
    assert error.reason == 'MARKER_OUTSIDE_BLOCK'
    assert error.sheet == 'Chân ghế A' and error.cell == 'N3'
    assert 'N3' in str(error)


def test_hai_marker_cung_loai_trong_mot_block_bi_tu_choi():
    wb = Workbook(); wb.remove(wb.active)
    ws = _sheet(wb, 'Chân ghế A', 'KM-001', [('CẮT LASER', 0, 14, None)])
    ws.cell(row=14, column=16, value=QR_MARKER_TEXT)   # marker OP thứ hai
    buffer = BytesIO(); wb.save(buffer)
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A')]
    with pytest.raises(RouterMarkerError) as excinfo:
        _stamp_source_workbook(buffer.getvalue(), PO, rows)
    error = excinfo.value
    assert error.reason == 'DUPLICATE_MARKER'
    assert error.sheet == 'Chân ghế A'
    assert 'P14' in str(error) and 'N14' in str(error)


def test_marker_hong_chan_ca_lan_xuat_chu_khong_dan_nua_chung():
    """Block 2 hỏng thì block 1 cũng không được dán -- quét marker TRƯỚC khi dán."""
    wb = Workbook(); wb.remove(wb.active)
    ws = _sheet(wb, 'Chân ghế A', 'KM-001',
                [('CẮT LASER', 0, 14, None), ('LÀM NGUỘI', 0, 14, None)])
    ws.cell(row=26, column=16, value=QR_MARKER_TEXT)   # block 2 có marker trùng
    buffer = BytesIO(); wb.save(buffer)
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A'),
            _row(102, 'PO-6126-KM-001-OP02', 'LÀM NGUỘI', part_code='KM-001',
                 part_name='Chân ghế A', sort_order=1)]
    with pytest.raises(RouterMarkerError):
        _stamp_source_workbook(buffer.getvalue(), PO, rows)


# --- template CŨ (chưa có marker) vẫn chạy y như trước --------------------

def test_template_khong_co_marker_van_dung_cach_dat_cu():
    """Hồi quy quan trọng nhất: file đang dùng để test 296 không được vỡ."""
    sheets = [('Chân ghế A', 'KM-001', [('CẮT LASER', 20, None, None)])]
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A', setup_id=201)]
    wb, placed, matched, unmatched = _stamp_source_workbook(_workbook(sheets), PO, rows)
    assert matched == 1 and unmatched == []
    assert {item['placement'] for item in placed} == {'lane'}
    assert {item['operation_id'] for item in placed} == {101, 201}
    # Làn cũ: sau cột dữ liệu cuối cùng (L = 12), tức N trở đi.
    for item in placed:
        assert item['marker_cell'] == ''
        assert item['anchor'][0] >= 'M'


def test_mot_block_co_marker_op_nhung_khong_co_marker_setup():
    """Trộn được ở mức từng tem: OP theo marker, SETUP rơi về làn cũ."""
    sheets = [('Chân ghế A', 'KM-001', [('CẮT LASER', 20, 14, None)])]
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A', setup_id=201)]
    _, placed, _, _ = _stamp_source_workbook(_workbook(sheets), PO, rows)
    items = _by_operation(placed)
    assert items[101]['placement'] == 'marker'
    assert items[201]['placement'] == 'lane'


# --- P0: tem phải NẰM TRONG ô marker, không chỉ neo vào nó ----------------
#
# Lỗi thật user gặp trên file export: tem được tạo và neo ĐÚNG ô QRCODE, nhưng
# giữ nguyên cỡ gốc ~75x89 px trong khi một ô mặc định chỉ 64x20 px. Nhìn trên
# file thì tem tràn qua bốn dòng và nằm lệch hẳn ra ngoài ô -- "QR không nằm
# trong ô QRCODE". Đếm số ảnh không bắt được lỗi này; phải đo VÙNG.

def _region_of(image):
    """(col, row, width_px, height_px) của một ảnh đã neo kiểu OneCellAnchor."""
    anchor = image.anchor
    marker = anchor._from
    return marker.col, marker.row, image.width, image.height


def test_tem_nam_gon_trong_o_marker_thuong():
    """Ô marker thường: tem phải vừa trong ô, không tràn ra ngoài."""
    from openpyxl.utils.units import EMU_to_pixels
    wb = Workbook(); wb.remove(wb.active)
    ws = _sheet(wb, 'Chân ghế A', 'KM-001', [('CẮT LASER', 0, 14, None)])
    # Ô marker rộng rãi để tem có chỗ: 120px x 120px.
    ws.column_dimensions['N'].width = 16
    ws.row_dimensions[14].height = 90
    buffer = BytesIO(); wb.save(buffer)
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A')]
    wb2, placed, _, _ = _stamp_source_workbook(buffer.getvalue(), PO, rows)

    item = placed[0]
    assert item['placement'] == 'marker' and item['marker_cell'] == 'N14'
    image = wb2['Chân ghế A']._images[-1]
    col, row, width, height = _region_of(image)
    # Neo đúng ô marker (0-based trong anchor).
    assert (col, row) == (13, 13), f'neo sai ô: {(col, row)}'
    # Và VỪA trong ô -- đây là phần trước đây sai.
    from mesflow.web.router_export import _column_width_px, _row_height_px
    cell_w = _column_width_px(wb2['Chân ghế A'], 14)
    cell_h = _row_height_px(wb2['Chân ghế A'], 14)
    assert width <= cell_w and height <= cell_h, (
        f'tem {width}x{height} tràn ra ngoài ô {cell_w}x{cell_h}')
    assert width == height, 'QR méo là QR không quét được'


def test_tem_can_giua_trong_merged_range():
    wb = Workbook(); wb.remove(wb.active)
    ws = _sheet(wb, 'Chân ghế A', 'KM-001', [('CẮT LASER', 0, None, None)])
    ws.merge_cells('N14:P17')
    ws['N14'] = QR_MARKER_TEXT
    buffer = BytesIO(); wb.save(buffer)
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A')]
    wb2, placed, _, _ = _stamp_source_workbook(buffer.getvalue(), PO, rows)

    item = placed[0]
    assert item['region'] == 'N14:P17'
    from mesflow.web.router_export import _region_size_px
    sheet = wb2['Chân ghế A']
    region_w, region_h = _region_size_px(sheet, (14, 14, 17, 16))
    image = sheet._images[-1]
    col, row, width, height = _region_of(image)
    assert (col, row) == (13, 13), 'phải neo ở góc trên-trái của merged range'
    assert width <= region_w and height <= region_h
    assert width == height
    # Căn giữa: lề hai bên chênh nhau không quá 1px.
    from openpyxl.utils.units import EMU_to_pixels
    offset_x = EMU_to_pixels(image.anchor._from.colOff)
    offset_y = EMU_to_pixels(image.anchor._from.rowOff)
    assert abs((region_w - width) / 2 - offset_x) <= 1, 'chưa căn giữa ngang'
    assert abs((region_h - height) / 2 - offset_y) <= 1, 'chưa căn giữa dọc'
    # Merge không bị đụng.
    assert 'N14:P17' in {str(r) for r in sheet.merged_cells.ranges}


def test_chu_marker_bi_xoa_ca_khi_nam_trong_merged_range():
    wb = Workbook(); wb.remove(wb.active)
    ws = _sheet(wb, 'Chân ghế A', 'KM-001', [('CẮT LASER', 0, None, None)])
    ws.merge_cells('N14:P17')
    ws['N14'] = QR_MARKER_TEXT
    buffer = BytesIO(); wb.save(buffer)
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A')]
    wb2, _, _, _ = _stamp_source_workbook(buffer.getvalue(), PO, rows)
    values = {c.value for r in wb2['Chân ghế A'].iter_rows() for c in r}
    assert QR_MARKER_TEXT not in values


def test_khong_doi_kich_thuoc_o_de_nhet_tem():
    """Tem phải vừa theo ô, không phải ô nới ra theo tem."""
    wb = Workbook(); wb.remove(wb.active)
    ws = _sheet(wb, 'Chân ghế A', 'KM-001', [('CẮT LASER', 0, 14, None)])
    ws.column_dimensions['N'].width = 16
    ws.row_dimensions[14].height = 90
    buffer = BytesIO(); wb.save(buffer)
    source = load_workbook(BytesIO(buffer.getvalue()))
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A')]
    wb2, _, _, _ = _stamp_source_workbook(buffer.getvalue(), PO, rows)
    before, after = source['Chân ghế A'], wb2['Chân ghế A']
    assert {k: v.width for k, v in before.column_dimensions.items()} == {
        k: v.width for k, v in after.column_dimensions.items()}
    assert {k: v.height for k, v in before.row_dimensions.items()} == {
        k: v.height for k, v in after.row_dimensions.items()}


def test_nhieu_op_moi_tem_vao_dung_marker_cua_no():
    """Hai block, hai marker -- không được hoán đổi."""
    wb = Workbook(); wb.remove(wb.active)
    _sheet(wb, 'Chân ghế A', 'KM-001',
           [('CẮT LASER', 0, 14, None), ('LÀM NGUỘI', 0, 14, None)])
    buffer = BytesIO(); wb.save(buffer)
    rows = [
        _row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
             part_name='Chân ghế A'),
        _row(102, 'PO-6126-KM-001-OP02', 'LÀM NGUỘI', part_code='KM-001',
             part_name='Chân ghế A', sort_order=1),
    ]
    _, placed, _, _ = _stamp_source_workbook(buffer.getvalue(), PO, rows)
    by_operation = {p['operation_id']: p['marker_cell'] for p in placed}
    assert by_operation[101] == 'N14'
    assert by_operation[102] == 'N26'


def test_tem_qua_nho_duoc_bao_lai_chu_khong_im_lang():
    """Ô marker bé thì tem bé -- và điều đó phải nói ra, không in ra tem mù.

    Không nới ô để lấy chỗ (cấu trúc file là của khách), nhưng cũng không lặng
    lẽ xuất một tem 14px mà máy quét không đọc nổi.
    """
    wb = Workbook(); wb.remove(wb.active)
    _sheet(wb, 'Chân ghế A', 'KM-001', [('CẮT LASER', 0, 14, None)])
    buffer = BytesIO(); wb.save(buffer)
    rows = [_row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER', part_code='KM-001',
                 part_name='Chân ghế A')]
    _, placed, _, _ = _stamp_source_workbook(buffer.getvalue(), PO, rows)
    assert placed[0]['too_small'] is True
    assert placed[0]['size_px'] < 48
