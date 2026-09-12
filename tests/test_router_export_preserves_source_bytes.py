"""Xuất router GIỮ NGUYÊN file gốc, chỉ thêm ảnh QR và xoá chữ marker.

BỐI CẢNH (bug EXCEL-EXPORT-ERR522). Cách xuất cũ mở workbook gốc bằng openpyxl
rồi ``wb.save()``. openpyxl khi save XOÁ mọi cached value của ô công thức và bật
``fullCalcOnLoad`` -> mở file phải recalc. Biểu mẫu NEWARK có sẵn công thức tự
tham chiếu (nhãn ``=$A$9`` nhắc lại giữa các block); vô hại khi còn cached value
+ không recalc, nhưng recalc lại thì thành ``Err:522`` (vòng tham chiếu) lan khắp
tờ -- đúng "file có QR mà nội dung lỗi".

Cách xuất mới KHÔNG save qua openpyxl: chỉ vá OOXML thêm ảnh QR và XOÁ ĐÚNG chữ
'QRCODE' ở ô marker (chỉ value, giữ style/merge). Bài này khoá cả hai:
  * calcPr + mọi công thức/cached value/sharedStrings/styles KHÔNG đổi -> hết 522;
  * ô marker hết chữ QRCODE, ảnh QR neo đúng ô, style/merge còn nguyên.
Nếu ai đó quay lại openpyxl full-save, các bài này đỏ.
"""
import re
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from mesflow.web.router_export import (
    _compute_qr_placements, _graft_qr_into_workbook, QR_MARKER_TEXT)
from mesflow.web.excel_io import _parse_go_router_template
from mesflow.db.repositories.master_data import operation_code_suffix
from test_router_qrcode_form_export import _marked_form

pytest.importorskip('PIL', reason='Pillow là dependency của tính năng xuất QR')

REAL_FIXTURE = Path(__file__).resolve().parent / 'fixtures/router-newark-arm-chair.xlsx'
PO = {'id': 1, 'code': 'PO-NEWARK', 'product': 'NEWARK', 'planned_quantity': 100,
      'source_template_id': 7}


def _immutable_parts(names):
    """Part KHÔNG bao giờ được đổi: sharedStrings/styles/workbook mang định dạng,
    chuỗi và calcPr -- xoá chữ marker chỉ đụng ô trong worksheet, không đụng đây."""
    return [n for n in names
            if n in ('xl/workbook.xml', 'xl/sharedStrings.xml', 'xl/styles.xml')]


def _rows_from_source(source_bytes):
    parsed = _parse_go_router_template(
        load_workbook(BytesIO(source_bytes), data_only=True), 'x.xlsx')
    part_code_by_key = {p['key']: p['code'] for p in parsed['parts']}
    rows = []
    next_id = 1000
    for op in parsed['operations']:
        part_code = part_code_by_key[op['part_key']]
        suffix = operation_code_suffix(part_code, op['code'])
        next_id += 1
        rows.append({'id': next_id, 'code': f"{PO['code']}-{suffix}", 'name': op['name'],
                     'part_code': part_code, 'op_qr': f'WF|OPID|{next_id}',
                     'setup_id': None, 'setup_qr': None})
    return rows


def _export(source_bytes):
    warnings = []
    placed, matched, leftovers, clear_cells = _compute_qr_placements(
        source_bytes, PO, _rows_from_source(source_bytes), warnings)
    output = _graft_qr_into_workbook(source_bytes, placed, clear_cells)
    return output, placed, matched, leftovers, warnings


@pytest.fixture(scope='module')
def real_bytes():
    assert REAL_FIXTURE.is_file(), f'thiếu fixture {REAL_FIXTURE}'
    return REAL_FIXTURE.read_bytes()


@pytest.fixture(scope='module')
def marked_bytes(real_bytes):
    # File thật + ô QRCODE trong mỗi block -> đường MARKER được kiểm.
    return _marked_form(real_bytes)[0]


def test_sharedstrings_styles_workbook_giu_nguyen_tung_byte(marked_bytes):
    """calcPr/định dạng/chuỗi không đổi một byte -> gốc rễ chống Err:522."""
    output, placed, _m, _l, _w = _export(marked_bytes)
    assert placed, 'phải có tem để bài này kiểm được gì'
    src = zipfile.ZipFile(BytesIO(marked_bytes)); out = zipfile.ZipFile(BytesIO(output))
    changed = [n for n in _immutable_parts(src.namelist())
               if n in out.namelist() and src.read(n) != out.read(n)]
    assert changed == [], f'part định dạng/chuỗi/workbook bị đổi: {changed}'


def test_khong_bat_fullcalconload_va_moi_cong_thuc_cached_giu_nguyen(marked_bytes):
    """Không bật recalc-khi-mở và giữ nguyên MỌI ô công thức + cached value.

    Đây là nguyên nhân trực tiếp của bug: openpyxl-save xoá cached + bật
    fullCalcOnLoad. Bài kiểm trên chính XML.
    """
    output, _placed, _m, _l, _w = _export(marked_bytes)
    src = zipfile.ZipFile(BytesIO(marked_bytes)); out = zipfile.ZipFile(BytesIO(output))
    out_wb = out.read('xl/workbook.xml').decode('utf-8')
    assert 'fullCalcOnLoad="1"' not in out_wb
    # Mọi ô CÔNG THỨC-kèm-cached-value trong nguồn còn nguyên trong bản xuất.
    checked = 0
    for name in src.namelist():
        if not name.startswith('xl/worksheets/sheet'):
            continue
        src_xml = src.read(name).decode('utf-8')
        out_xml = out.read(name).decode('utf-8')
        for m in re.finditer(r'<c r="([A-Z]+\d+)"[^>]*>(?:(?!</c>).)*?<f\b'
                             r'(?:(?!</c>).)*?<v>[^<]+</v>(?:(?!</c>).)*?</c>',
                             src_xml, flags=re.S):
            cell = m.group(0)
            assert cell in out_xml, f'{name}!{m.group(1)}: công thức/cached value đổi'
            checked += 1
    assert checked > 0, 'fixture không có ô công thức-kèm-cached-value để kiểm'


def test_o_marker_het_chu_qrcode_nhung_giu_style_va_merge(marked_bytes):
    """Sau xuất: KHÔNG ô nào còn chữ QRCODE; ô marker giữ style; merge nguyên."""
    output, placed, _m, _l, _w = _export(marked_bytes)
    marker_items = [p for p in placed if p['placement'] == 'marker']
    assert marker_items, 'phải có tem dán theo marker'

    src = load_workbook(BytesIO(marked_bytes))
    out = load_workbook(BytesIO(output))
    # 1) Không còn chữ QRCODE ở bất kỳ ô nào của bản xuất.
    left = [(ws.title, c.coordinate) for ws in out.worksheets
            for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.strip().upper() == QR_MARKER_TEXT]
    assert left == [], f'vẫn còn chữ {QR_MARKER_TEXT}: {left[:5]}'
    # 2) Từng ô marker: value bị xoá, nhưng STYLE giữ nguyên và MERGE không đổi.
    for item in marker_items:
        sheet = item['sheet']; coord = item['marker_cell']
        assert out[sheet][coord].value is None, f'{sheet}!{coord} chưa xoá chữ'
        assert out[sheet][coord].style == src[sheet][coord].style, \
            f'{sheet}!{coord} đổi style'
    for name in src.sheetnames:
        assert {str(r) for r in out[name].merged_cells.ranges} == \
            {str(r) for r in src[name].merged_cells.ranges}, f'{name}: merge đổi'


def test_anh_qr_neo_dung_o_marker_tren_file_xuat(marked_bytes):
    """Ảnh QR neo đúng ô marker (góc trên-trái vùng), đủ số tem."""
    output, placed, _m, _l, _w = _export(marked_bytes)
    marker_items = [p for p in placed if p['placement'] == 'marker']
    out = load_workbook(BytesIO(output))
    anchored = {(ws.title, im.anchor._from.col, im.anchor._from.row)
                for ws in out.worksheets for im in ws._images
                if im.anchor.__class__.__name__ == 'OneCellAnchor'}
    for item in marker_items:
        assert (item['sheet'], item['col0'], item['row0']) in anchored, \
            f"thiếu tem neo ở {item['sheet']}!{item['marker_cell']}"


def test_chi_doi_media_drawing_worksheet_khong_dong_khac(marked_bytes):
    """Bản xuất chỉ khác nguồn ở: ảnh QR, drawing, và worksheet (xoá chữ marker)."""
    output, placed, _m, _l, _w = _export(marked_bytes)
    src = zipfile.ZipFile(BytesIO(marked_bytes)); out = zipfile.ZipFile(BytesIO(output))
    added = sorted(set(out.namelist()) - set(src.namelist()))
    assert len([n for n in added if n.startswith('xl/media/')]) == len(placed)
    changed = [n for n in src.namelist()
               if n in out.namelist() and src.read(n) != out.read(n)]
    for n in added + changed:
        assert (n.startswith('xl/media/') or n.startswith('xl/drawings/')
                or n.startswith('xl/worksheets/') or n == '[Content_Types].xml'), \
            f'đổi part ngoài phạm vi: {n}'
    from PIL import Image
    for n in added:
        if n.startswith('xl/media/'):
            Image.open(BytesIO(out.read(n))).verify()


def test_khong_co_qrcode_van_xuat_duoc_giu_nguyen_noi_dung(real_bytes):
    """File thật CHƯA có ô QRCODE (NONE mode): không có gì để xoá -> mọi
    worksheet/sharedStrings/styles/workbook giữ nguyên byte, tem đi làn trống."""
    output, placed, matched, _l, _w = _export(real_bytes)
    assert matched > 0 and placed
    src = zipfile.ZipFile(BytesIO(real_bytes)); out = zipfile.ZipFile(BytesIO(output))
    content = [n for n in src.namelist()
               if n.startswith('xl/worksheets/sheet') or n in _immutable_parts(src.namelist())]
    changed = [n for n in content if n in out.namelist() and src.read(n) != out.read(n)]
    assert changed == [], f'NONE mode không được đổi part nội dung: {changed}'
