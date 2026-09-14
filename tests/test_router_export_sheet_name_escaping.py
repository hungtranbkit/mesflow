"""Tên sheet có `&`, `<`, `"` không được làm tem QR biến mất trong im lặng.

LỖI THẬT (XL-01, audit 2026-09-14). Trong `xl/workbook.xml`, một tờ tên
``Khung & Chan`` được ghi là ``name="Khung &amp;amp; Chan"``. `_worksheet_file_map`
đọc tên bằng regex và KHÔNG giải mã thực thể XML, trong khi mọi chỗ tra cứu
dùng `ws.title` của openpyxl -- vốn đã giải mã. Hai chuỗi không bằng nhau, tra
cứu trượt, và cả hai chỗ dùng đều `continue` lặng lẽ.

Hậu quả đúng là thứ tệ nhất trong nhóm này: KHÔNG có lỗi, KHÔNG có cảnh báo,
số tem báo cho người dùng vẫn đếm đủ (`X-MESFlow-Router-Labels`, toast "Đã xuất
file kèm N tem QR"), nhưng trong file giao ra cả một Part không có tem nào --
và chữ `QRCODE` vẫn còn nguyên trên giấy vì lượt xoá marker trượt y hệt.

Tên sheet chứa `&`, `<`, `"` là tên HỢP LỆ của Excel (`Khung & Chân`,
`Ghế "Newark"`, `Bản vẽ <A>`), nên đây không phải ca hiếm. File thật NEWARK vô
tình không có tên nào như vậy, nên bộ test cũ không chạm tới.

Bài này kiểm trên FILE ĐÃ XUẤT, không kiểm cấu trúc trung gian: lỗi chỉ nhìn
thấy khi mở file ra.
"""
from __future__ import annotations

import re
import zipfile
from io import BytesIO

import pytest

pytest.importorskip('PIL', reason='Pillow là dependency của xuất QR')
from openpyxl import Workbook, load_workbook  # noqa: E402

from mesflow.web import router_export as RE  # noqa: E402

#: Tên hợp lệ của Excel mà XML phải mã hoá. Excel cấm : \ / ? * [ ] -- không cấm
#: & < > ". Dấu `>` không bắt buộc phải mã hoá nhưng openpyxl vẫn mã hoá `<`.
TRICKY = ['Khung & Chan', 'Ghe "Newark"', 'Ban <A>', 'A & B < C']
PLAIN = 'Binh thuong'

BLOCK_HEIGHT = 12
MARKER_COLUMN = 5      # E


def _router(sheets):
    """Workbook GO ROUTER tối giản, mỗi tờ một Part một block, có ô QRCODE."""
    wb = Workbook()
    wb.remove(wb.active)
    for index, title in enumerate(sheets):
        ws = wb.create_sheet(title)
        code = f'KM-{index:03d}'
        ws['A2'] = 'PO NUMBER:'
        ws['C2'] = 'PO-ESCAPE'
        ws['A3'] = 'QTY:'
        ws['C3'] = 10
        ws['A4'] = 'TÊN BẢN VẼ:'
        ws['C4'] = title
        ws['A5'] = 'MÃ BẢN VẼ:'
        ws['C5'] = code
        row = 8
        ws.cell(row=row, column=1, value='OPERATION # 01- CAT')
        ws.cell(row=row + 1, column=1, value='Part Number ( Mã bản vẽ )')
        ws.cell(row=row + 1, column=2, value=code)
        ws.cell(row=row + 2, column=12, value='Thời gian Setup ( phút )')
        ws.cell(row=row + 3, column=1, value='SETUP')
        ws.cell(row=row + 3, column=12, value=0)
        ws.cell(row=row + 5, column=12, value='Thời gian gia công / sản phẩm (s)')
        ws.cell(row=row + 6, column=1, value='Thời gian gia công')
        ws.cell(row=row + 6, column=12, value=60)
        ws.cell(row=row + 7, column=MARKER_COLUMN, value=RE.QR_MARKER_TEXT)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _images_per_sheet(xlsx_bytes):
    """{tên sheet -> số ảnh neo trên tờ đó}, đọc từ FILE ĐÃ LƯU."""
    z = zipfile.ZipFile(BytesIO(xlsx_bytes))
    wb_xml = z.read('xl/workbook.xml').decode('utf-8')
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    target = {}
    for rel in re.findall(r'<Relationship\b[^>]*/?>', rels):
        rid = re.search(r'Id="([^"]+)"', rel)
        tgt = re.search(r'Target="([^"]+)"', rel)
        if rid and tgt:
            target[rid.group(1)] = tgt.group(1).rsplit('/', 1)[-1]
    out = {}
    for tag in re.findall(r'<sheet\b[^>]*/?>', wb_xml):
        name = re.search(r'name="([^"]+)"', tag)
        rid = re.search(r'r:id="([^"]+)"', tag)
        if not (name and rid):
            continue
        import html as _html
        title = _html.unescape(name.group(1))
        base = target.get(rid.group(1), '')
        count = 0
        rel_path = f'xl/worksheets/_rels/{base}.rels'
        if rel_path in z.namelist():
            found = re.search(r'Target="([^"]*drawing\d+\.xml)"',
                              z.read(rel_path).decode('utf-8'))
            if found:
                draw = 'xl/drawings/' + found.group(1).rsplit('/', 1)[-1]
                if draw in z.namelist():
                    count = z.read(draw).decode('utf-8', 'ignore').count('<xdr:pic>')
        out[title] = count
    return out


# --------------------------------------------------------------------------
def test_the_map_key_is_the_decoded_sheet_title():
    """Gốc của lỗi, ở mức nhỏ nhất: khoá bảng phải bằng đúng ws.title."""
    data = _router(TRICKY + [PLAIN])
    z = zipfile.ZipFile(BytesIO(data))
    parts = {n: z.read(n) for n in z.namelist()}
    mapping = RE._worksheet_file_map(parts)
    for title in load_workbook(BytesIO(data)).sheetnames:
        assert title in mapping, f'{title!r} không tra được; khoá đang có: {list(mapping)}'


def test_no_sheet_silently_loses_its_qr(tmp_path):
    """Bài chính: một tờ tên có `&` phải có tem đúng như tờ tên thường."""
    source = _router([PLAIN] + TRICKY)
    placed, matched, leftovers, clear_cells = RE._compute_qr_placements(
        source, {'code': 'PO-ESCAPE', 'planned_quantity': 10}, _rows(source), [])
    assert len(placed) == len(TRICKY) + 1, placed

    out = RE._graft_qr_into_workbook(source, placed, clear_cells)
    per_sheet = _images_per_sheet(out)
    for title in [PLAIN] + TRICKY:
        assert per_sheet.get(title) == 1, (
            f'sheet {title!r} có {per_sheet.get(title)} ảnh, phải có 1 -- '
            f'toàn bộ: {per_sheet}')


def test_the_qrcode_word_is_removed_from_a_tricky_sheet_too():
    """Lượt xoá marker trượt theo cùng một cách, nên phải có bài riêng:
    chữ QRCODE còn lại trên giấy là dấu hiệu người dùng nhìn thấy được."""
    source = _router(TRICKY)
    placed, _matched, _left, clear_cells = RE._compute_qr_placements(
        source, {'code': 'PO-ESCAPE', 'planned_quantity': 10}, _rows(source), [])
    out = RE._graft_qr_into_workbook(source, placed, clear_cells)
    workbook = load_workbook(BytesIO(out))
    for title in TRICKY:
        values = [c.value for row in workbook[title].iter_rows() for c in row]
        assert RE.QR_MARKER_TEXT not in values, f'sheet {title!r} vẫn còn chữ QRCODE'


def test_a_sheet_that_cannot_be_written_is_an_error_not_a_shrug():
    """Chỗ này trước đây là `continue`. Một placement không ghi được là bản
    xuất HỎNG -- phải đỏ, chứ không phải giao ra tờ giấy thiếu tem."""
    source = _router([PLAIN])
    placed, _m, _l, clear_cells = RE._compute_qr_placements(
        source, {'code': 'PO-ESCAPE', 'planned_quantity': 10}, _rows(source), [])
    ghost = [dict(item, sheet='Sheet không tồn tại') for item in placed]
    with pytest.raises(RE.RouterPlacementError) as excinfo:
        RE._graft_qr_into_workbook(source, ghost, {})
    assert excinfo.value.reason == 'SHEET_PART_NOT_FOUND'
    assert 'Sheet không tồn tại' in str(excinfo.value)


# --------------------------------------------------------------------------
def _rows(source_bytes):
    """Các hàng Operation như _load_po_operations() sẽ trả về, dựng từ chính
    workbook nguồn để mã Part/Operation luôn khớp với những gì parser đọc."""
    from mesflow.web.excel_io import _parse_go_router_template
    parsed = _parse_go_router_template(
        load_workbook(BytesIO(source_bytes), data_only=True), 'escape.xlsx')
    part_code = {p['key']: p['code'] for p in parsed['parts']}
    rows = []
    for index, op in enumerate(parsed['operations'], start=1):
        code = part_code[op['part_key']]
        rows.append({
            'id': 1000 + index, 'code': f"PO-ESCAPE-{op['code']}", 'name': op['name'],
            'operation_type': 'PRODUCTION', 'part_code': code, 'part_name': code,
            'op_qr': f'WF|OPID|{1000 + index}', 'setup_id': None, 'setup_qr': None,
            'sort_order': index, 'part_sort_order': index,
        })
    return rows
