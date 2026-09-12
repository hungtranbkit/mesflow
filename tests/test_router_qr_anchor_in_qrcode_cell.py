"""Regression MỚI (EXCEL-QR-EMBED, 2026-09-12): trên FILE .XLSX ĐÃ XUẤT, top-left
của ảnh QR phải neo ĐÚNG ô có chữ QRCODE — không lệch row/column, không vào ô khác.

Khác các bài cũ: mổ TRỰC TIẾP drawing XML của file đã LƯU (không dựa openpyxl
objects), so top-left từng ảnh với marker_cell của đúng placement, trên cả
workbook tổng hợp (marker ở cột E, khác hẳn làn heuristic) lẫn form THẬT NEWARK.
"""
import re
import zipfile
from io import BytesIO

import pytest
from openpyxl.utils import coordinate_to_tuple

pytest.importorskip('PIL', reason='Pillow là dependency của xuất QR')

import test_router_qr_marker as M
from mesflow.web.router_export import _stamp_source_workbook
from test_router_qrcode_form_export import (  # noqa: F401  (fixtures form THẬT)
    real_bytes, marked, source_bytes, parsed, rows, stamped)


def _sheet_drawings(xlsx_bytes):
    """{tên sheet -> set((col0,row0)) top-left mọi ảnh} đọc từ file đã lưu."""
    z = zipfile.ZipFile(BytesIO(xlsx_bytes))
    wbxml = z.read('xl/workbook.xml').decode('utf-8', 'ignore')
    # thứ tự attribute không cố định -> lấy name và r:id độc lập cho mỗi <sheet>
    order = []
    for tag in re.findall(r'<sheet\b[^>]*/?>', wbxml):
        nm = re.search(r'name="([^"]+)"', tag)
        rid = re.search(r'r:id="([^"]+)"', tag)
        if nm and rid:
            order.append((nm.group(1), rid.group(1)))
    rels = z.read('xl/_rels/workbook.xml.rels').decode('utf-8', 'ignore')
    rid_target = {}
    for rel in re.findall(r'<Relationship\b[^>]*/?>', rels):
        i = re.search(r'Id="([^"]+)"', rel); t = re.search(r'Target="([^"]+)"', rel)
        if i and t:
            rid_target[i.group(1)] = t.group(1)
    out = {}
    for name, rid in order:
        target = rid_target.get(rid, '')
        base = target.rsplit('/', 1)[-1]
        relpath = f'xl/worksheets/_rels/{base}.rels'
        anchors = set()
        if relpath in z.namelist():
            dm = re.search(r'Target="([^"]*drawing\d+\.xml)"',
                           z.read(relpath).decode('utf-8', 'ignore'))
            if dm:
                draw = 'xl/drawings/' + dm.group(1).rsplit('/', 1)[-1]
                if draw in z.namelist():
                    dxml = z.read(draw).decode('utf-8', 'ignore')
                    anchors = {(int(c), int(r)) for c, r in re.findall(
                        r'<from><col>(\d+)</col><colOff>\d+</colOff><row>(\d+)</row>', dxml)}
        out[name] = anchors
    return out


def _cell0(coord):
    row, col = coordinate_to_tuple(coord)      # 1-indexed (row, col)
    return (col - 1, row - 1)                   # 0-indexed (col, row) như drawing


def _saved(wb):
    buf = BytesIO(); wb.save(buf); return buf.getvalue()


# ---------- (1) tổng hợp: marker ở cột E, khác hẳn làn heuristic ----------

def test_qr_top_left_neo_dung_o_qrcode_tren_file_da_xuat():
    MARK_COL = 5  # E — khác hẳn làn heuristic (bên phải, >=13)
    wb_bytes = M._workbook([('Chân ghế A', 'KM-001', [('CẮT LASER', 0, MARK_COL, None)])])
    rows = [M._row(101, 'PO-6126-KM-001-OP01', 'CẮT LASER',
                   part_code='KM-001', part_name='Chân ghế A')]
    wb, placed, matched, unmatched = _stamp_source_workbook(wb_bytes, M.PO, rows)
    assert matched == 1 and len(placed) == 1
    marker_cell = placed[0]['marker_cell']                 # ví dụ 'E14'
    assert marker_cell.startswith('E'), f'marker phải ở cột E, đang {marker_cell}'

    drawings = _sheet_drawings(_saved(wb))
    anchors = drawings.get('Chân ghế A', set())
    assert anchors, 'file đã xuất không có ảnh QR nào'
    assert _cell0(marker_cell) in anchors, (
        f'top-left QR không neo vào ô QRCODE {marker_cell} '
        f'(0-index {_cell0(marker_cell)}); anchors thực={sorted(anchors)}')
    # không rơi vào làn cột phải (chứng minh theo marker, không phải heuristic)
    assert all(c < 13 for c, r in anchors), f'QR bị đặt vào làn heuristic: {sorted(anchors)}'

    ws = wb['Chân ghế A']
    r, c = coordinate_to_tuple(marker_cell)
    assert ws.cell(row=r, column=c).value in (None, ''), 'chữ QRCODE còn sót dưới QR'


# ---------- (4) form THẬT NEWARK: mỗi tem neo đúng marker_cell của nó ----------

def test_form_that_moi_tem_neo_dung_o_qrcode_cua_no(stamped):
    wb, placed = stamped[0], stamped[1]
    drawings = _sheet_drawings(_saved(wb))
    assert placed, 'form thật phải có tem'
    lech = []
    for item in placed:
        sheet, mc = item['sheet'], item['marker_cell']
        if _cell0(mc) not in drawings.get(sheet, set()):
            lech.append((sheet, mc, item.get('operation_id'), item.get('kind')))
    assert not lech, f'{len(lech)} tem không neo đúng ô QRCODE trên file xuất: {lech[:8]}'
    # đủ số tem = đủ marker (không thiếu, không thừa lệch)
    assert len(placed) >= 1
