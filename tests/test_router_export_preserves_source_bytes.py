"""Xuất router GIỮ NGUYÊN file gốc byte-for-byte, chỉ thêm ảnh QR.

BỐI CẢNH (bug EXCEL-EXPORT-ERR522). Cách xuất cũ mở workbook gốc bằng openpyxl
rồi ``wb.save()``. openpyxl khi save XOÁ mọi cached value của ô công thức và bật
``fullCalcOnLoad`` -> mở file phải recalc. Biểu mẫu NEWARK có sẵn những công
thức tự tham chiếu (nhãn ``=$A$9`` nhắc lại giữa các block); chúng vô hại khi có
cached value và không recalc, nhưng recalc lại với iterative calc tắt thì thành
``Err:522`` (vòng tham chiếu) lan khắp tờ -- đúng "file có QR mà nội dung lỗi".

Cách xuất mới KHÔNG save qua openpyxl: chỉ vá OOXML thêm ảnh QR, giữ nguyên mọi
worksheet/sharedStrings/styles/workbook. Bài này khoá đúng điều đó: nếu ai đó
quay lại openpyxl full-save, các part mang nội dung sẽ đổi và bài này đỏ.
"""
import re
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from mesflow.web.router_export import (
    _compute_qr_placements, _graft_qr_into_workbook)
from mesflow.web.excel_io import _parse_go_router_template
from mesflow.db.repositories.master_data import operation_code_suffix
from test_router_qrcode_form_export import _marked_form

pytest.importorskip('PIL', reason='Pillow là dependency của tính năng xuất QR')

REAL_FIXTURE = Path(__file__).resolve().parent / 'fixtures/router-newark-arm-chair.xlsx'
PO = {'id': 1, 'code': 'PO-NEWARK', 'product': 'NEWARK', 'planned_quantity': 100,
      'source_template_id': 7}

#: Part mang nội dung của một workbook: đổi một byte ở đây là đổi công thức /
#: cached value / định dạng / nhãn -- đúng thứ phải giữ nguyên.
def _content_parts(names):
    return [n for n in names
            if n.startswith('xl/worksheets/sheet')
            or n in ('xl/workbook.xml', 'xl/sharedStrings.xml', 'xl/styles.xml')]


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
    placed, matched, leftovers = _compute_qr_placements(
        source_bytes, PO, _rows_from_source(source_bytes), warnings)
    output = _graft_qr_into_workbook(source_bytes, placed)
    return output, placed, matched, leftovers, warnings


@pytest.fixture(scope='module')
def real_bytes():
    assert REAL_FIXTURE.is_file(), f'thiếu fixture {REAL_FIXTURE}'
    return REAL_FIXTURE.read_bytes()


@pytest.fixture(scope='module')
def marked_bytes(real_bytes):
    # File thật + ô QRCODE trong mỗi block -> đường MARKER được kiểm.
    return _marked_form(real_bytes)[0]


def test_moi_part_mang_noi_dung_giu_nguyen_tung_byte(marked_bytes):
    """Mọi worksheet/sharedStrings/styles/workbook KHÔNG đổi một byte."""
    output, placed, matched, _leftovers, _warnings = _export(marked_bytes)
    assert placed, 'phải có ít nhất một tem để bài này kiểm được gì'
    src = zipfile.ZipFile(BytesIO(marked_bytes))
    out = zipfile.ZipFile(BytesIO(output))
    changed = [n for n in _content_parts(src.namelist())
               if n in out.namelist() and src.read(n) != out.read(n)]
    assert changed == [], f'part mang nội dung bị đổi: {changed}'


def test_khong_bat_fullcalconload_va_khong_xoa_cached_value(marked_bytes):
    """Không bật recalc-khi-mở và không xoá cached value -> không Err:522.

    Đây là hai thứ openpyxl-save làm và là nguyên nhân trực tiếp của bug. Bài
    kiểm trên chính XML: calcPr của workbook.xml y hệt nguồn, và một ô công thức
    có cached value trong nguồn vẫn còn nguyên cached value đó trong bản xuất.
    """
    output, _placed, _m, _l, _w = _export(marked_bytes)
    src = zipfile.ZipFile(BytesIO(marked_bytes)); out = zipfile.ZipFile(BytesIO(output))
    src_wb = src.read('xl/workbook.xml').decode('utf-8')
    out_wb = out.read('xl/workbook.xml').decode('utf-8')
    src_calc = re.search(r'<calcPr[^>]*/>', src_wb)
    out_calc = re.search(r'<calcPr[^>]*/>', out_wb)
    assert (src_calc and src_calc.group(0)) == (out_calc and out_calc.group(0))
    assert 'fullCalcOnLoad="1"' not in out_wb
    # Một ô công thức CÓ cached value trong nguồn -> còn nguyên trong bản xuất.
    found = False
    for name in _content_parts(src.namelist()):
        if not name.startswith('xl/worksheets/sheet'):
            continue
        xml = src.read(name).decode('utf-8')
        if re.search(r'<f\b[^>]*>[^<]+</f><v>[^<]+</v>', xml):
            assert out.read(name) == src.read(name)
            found = True
            break
    assert found, 'fixture không có ô công thức-kèm-cached-value để kiểm'


def test_them_dung_so_anh_qr_va_khong_dong_khac(marked_bytes):
    """Bản xuất chỉ khác nguồn ở: ảnh QR mới + drawing chứa chúng. Không hơn."""
    output, placed, _m, _l, _w = _export(marked_bytes)
    src = zipfile.ZipFile(BytesIO(marked_bytes)); out = zipfile.ZipFile(BytesIO(output))
    added = sorted(set(out.namelist()) - set(src.namelist()))
    media_added = [n for n in added if n.startswith('xl/media/')]
    assert len(media_added) == len(placed), 'số ảnh thêm phải bằng số tem'
    # Mọi part mới hoặc đổi đều phải là media/drawing (không đụng part nội dung).
    changed = [n for n in src.namelist()
               if n in out.namelist() and src.read(n) != out.read(n)]
    for n in added + changed:
        assert (n.startswith('xl/media/') or n.startswith('xl/drawings/')
                or n == '[Content_Types].xml'), f'đổi part ngoài phạm vi ảnh: {n}'
    # Ảnh QR mở được và là PNG thật.
    from PIL import Image
    for n in media_added:
        Image.open(BytesIO(out.read(n))).verify()


def test_khong_co_qrcode_van_xuat_duoc_khong_lam_hong_file(real_bytes):
    """File thật CHƯA có ô QRCODE (marker_mode NONE): vẫn xuất, vẫn giữ nguyên
    nội dung, tem đi làn trống -- không throw, không đổi part nội dung."""
    output, placed, matched, _l, _w = _export(real_bytes)
    assert matched > 0 and placed, 'file thật phải khớp và đặt được tem'
    src = zipfile.ZipFile(BytesIO(real_bytes)); out = zipfile.ZipFile(BytesIO(output))
    changed = [n for n in _content_parts(src.namelist())
               if n in out.namelist() and src.read(n) != out.read(n)]
    assert changed == [], f'part mang nội dung bị đổi: {changed}'
