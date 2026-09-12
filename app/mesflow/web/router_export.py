"""Xuất lại file Lộ trình sản xuất (GO ROUTER) kèm tem QR cho từng Operation.

LÝ DO TỒN TẠI. Xưởng làm việc trên tờ router in ra, không trên màn hình. Tờ đó
đi từ Excel vào MESFlow lúc nhập Template; cái thiếu là đường ngược lại — in nó
ra kèm QR để người đứng máy quét đúng công đoạn đang làm, và quét tem SETUP
riêng khi phải set máy.

BA QUYẾT ĐỊNH ĐÁNG GHI:

1. Xuất theo PRODUCTION ORDER, không theo Template. QR phải địa chỉ tới
   ``operations.id`` — danh tính duy nhất không đổi tên được — mà id đó chỉ tồn
   tại sau khi PO được tạo. ``template_operations`` không có thứ để quét.

2. Payload lấy từ ``printable_qr_payload_sql()`` chứ không tự ghép chuỗi. Hàm
   đó là nơi duy nhất trả lời "tem MỚI được phép mang payload nào": tem cũ còn
   dán ngoài xưởng thì giữ nguyên, tem mơ hồ (mã trong QR đã thuộc về Operation
   khác) thì chuyển sang địa chỉ theo id. Tự ghép ``WF|OP|<mã>`` ở đây là dựng
   lại đúng lỗi mơ hồ mà hàm kia sinh ra để chặn.

3. Giữ workbook GỐC khi còn. Mỗi lần nhập Template, file được lưu lại nguyên
   bytes (``template_import_blobs``, content-addressed). Xuất = mở lại chính
   file đó rồi ĐÓNG THÊM QR vào, nên công thức, định dạng, logo, khung in của
   xưởng không mất gì. Không còn file gốc mới dựng workbook tương đương.

QR đặt ở LÀN RIÊNG bên phải vùng dữ liệu (cột đầu tiên sau cột cuối cùng có
chữ), không đè lên Part Number, thời gian setup, thời gian gia công, số lượng
hay tên người thực hiện — xem ``_qr_lane_column()``.
"""
from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from flask import Blueprint, jsonify, request, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XlsxImage
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from mesflow.db.connection import fetch_all, fetch_one
from mesflow.db.repositories.master_data import operation_code_suffix
from mesflow.db.repositories.template_imports import TemplateImportRepository
from mesflow.domain.policy import PRODUCTION_TYPE, SETUP_TYPE, type_is_sql
from mesflow.domain.qr_identity import printable_qr_payload_sql
from mesflow.web.auth import roles_required
from mesflow.web.errors import api_error_response

bp = Blueprint('router_export', __name__, url_prefix='/api/production-orders')

#: Nhãn in cạnh mỗi tem. Tiếng Việt, đúng chữ xưởng đọc trên giấy.
QR_OP_LABEL = 'QR OP'
QR_SETUP_LABEL = 'QR Setup'

#: Cạnh ảnh QR nhắm tới, tính bằng pixel ở 96 DPI (96 px = 1 inch = 2,54 cm).
#: Cỡ thật được làm tròn XUỐNG bội số nguyên của số module để không phải nội
#: suy; xem _qr_png(). Máy quét cầm tay đọc thoải mái từ ~1,8 cm trở lên.
QR_PIXELS = 96
#: Bề rộng cột của làn QR, tính theo đơn vị "số ký tự" của Excel (~7 px/ký tự).
QR_COLUMN_WIDTH = 15
#: Số cột cách giữa tem OP và tem SETUP, để hai ảnh không chạm nhau.
QR_COLUMN_GAP = 2


def _qr_png(payload: str) -> BytesIO:
    """Ảnh PNG của một payload, cỡ cố định để in ra luôn quét được.

    ``box_size`` tính ngược từ QR_PIXELS thay vì đặt cứng: một payload dài hơn
    cần nhiều module hơn, và nếu giữ nguyên box_size thì ảnh phình to ra khỏi
    làn QR. Cố định CẠNH ẢNH, để thư viện tự chọn số module.
    """
    import qrcode

    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload)
    qr.make(fit=True)
    modules = qr.modules_count + 2 * qr.border
    # Sàn 3 px/module: payload dài làm số module tăng, và nếu để box_size rơi
    # xuống 2 thì tem in ra bé hơn ~1,5 cm — cỡ mà máy quét bắt đầu phụ thuộc
    # chất lượng máy in. Thà tem to hơn ô một chút còn hơn tem không quét được.
    qr.box_size = max(3, QR_PIXELS // modules)
    image = qr.make_image(fill_color='black', back_color='white')
    out = BytesIO()
    image.save(out, format='PNG')
    out.seek(0)
    return out


def _place_qr(ws, payload: str, label: str, *, row: int, column: int):
    """Đóng một tem vào ô (row, column) kèm nhãn ngay phía trên."""
    letter = get_column_letter(column)
    heading = ws.cell(row=row, column=column)
    heading.value = label
    heading.font = Font(bold=True, size=9)
    heading.alignment = Alignment(horizontal='center')
    # GIỮ NGUYÊN cỡ pixel gốc của ảnh. Ép width/height về một con số khác là
    # bắt Excel nội suy lại một ảnh 1-bit theo tỉ lệ không nguyên: cạnh module
    # nhoè ra và tem in xong quét chập chờn. Ảnh đã được sinh đúng cỡ cần in.
    image = XlsxImage(_qr_png(payload))
    ws.add_image(image, f'{letter}{row + 1}')
    ws.column_dimensions[letter].width = QR_COLUMN_WIDTH
    return f'{letter}{row + 1}'


def _qr_lane_column(ws) -> int:
    """Cột đầu tiên NẰM NGOÀI vùng có chữ của sheet.

    Đây là toàn bộ lời hứa "QR không đè chữ", và nó được giữ bằng cấu trúc chứ
    không bằng mắt: làn QR bắt đầu sau ô có nội dung xa nhất về bên phải, nên
    không có ô dữ liệu nào — Part Number, thời gian setup, thời gian gia công,
    số lượng, người thực hiện — có thể nằm dưới một tem.

    ``ws.max_column`` của openpyxl tính cả ô đã từng có định dạng rồi bị xoá
    chữ, nên quét lại giá trị thật: bám theo max_column làm làn QR trôi xa vô
    ích, và với sheet có định dạng thừa thì tem rơi ra ngoài khổ giấy.
    """
    rightmost = 0
    for row in ws.iter_rows():
        for cell in row:
            if cell.value not in (None, ''):
                rightmost = max(rightmost, cell.column)
    return max(rightmost, 1) + 1


def _load_po_operations(po_id: int):
    """Operation sản xuất của PO, mỗi dòng kèm tem SETUP liên kết (nếu có).

    Một truy vấn, LEFT JOIN sang chính bảng operations theo
    ``parent_operation_id``: quan hệ cha–con của SETUP là cột đó, không phải
    quy ước đặt tên mã.

    "Mọi Operation của PO" ở đây nghĩa là mọi Operation QUÉT ĐƯỢC, tức
    ``policy.LABELLED_TYPES`` = PRODUCTION + SETUP. REWORK cố ý không có tem:
    ``lock_startable_operation()`` từ chối mở session trên bàn sửa hàng, nên in
    tem cho nó là đưa ra xưởng một mã QR mà kiosk sẽ từ chối -- xem chú thích
    của LABELLED_TYPES trong domain/policy.py. Đây là chính sách chung của hệ
    thống, không phải lựa chọn riêng của màn xuất file.
    """
    is_production = type_is_sql(PRODUCTION_TYPE, 'o')
    is_setup = type_is_sql(SETUP_TYPE, 's')
    return fetch_all(f"""
        SELECT o.id, o.code, o.name, o.sort_order,
               o.standard_seconds_per_unit, o.requires_setup, o.expected_setup_minutes,
               p.id part_id, p.code part_code, p.name part_name, p.sort_order part_sort,
               ({printable_qr_payload_sql('o')}) op_qr,
               s.id setup_id, s.code setup_code, s.name setup_name,
               s.expected_setup_minutes setup_minutes,
               ({printable_qr_payload_sql('s')}) setup_qr
        FROM operations o
        JOIN parts p ON p.id = o.part_id
        LEFT JOIN operations s ON s.parent_operation_id = o.id AND {is_setup}
        WHERE o.production_order_id = %s AND {is_production}
        ORDER BY p.sort_order, p.id, o.sort_order, o.id
    """, (int(po_id),))


def _archived_source_workbook(template_id):
    """Bytes của workbook gốc đã nhập gần nhất cho Template này, nếu còn."""
    if not template_id:
        return None
    from pathlib import Path

    for event in TemplateImportRepository().list(template_id=int(template_id), limit=50):
        if event['outcome'] == 'FAILED':
            # File bị từ chối không phải bản dựng nên Template hiện tại.
            continue
        found = TemplateImportRepository().file_for(event['id'])
        if not found:
            continue
        path = Path(found['storage_path'])
        if path.is_file():
            return path.read_bytes()
    return None


def _index_source_blocks(source_bytes, po_code):
    """Bản đồ (mã Part, hậu tố mã OP) -> (tên sheet, dòng) của workbook gốc.

    Dựng bằng CHÍNH hàm parse của luồng nhập, nên vị trí block ở đây và
    Operation trong CSDL sinh ra từ cùng một cách đọc. Khoá là cặp
    (part_code, hậu tố) — đúng danh tính mà importer dùng — chứ không phải mã
    OP toàn cục: hai sheet khác nhau hoàn toàn có thể cùng có 'OPERATION # 01',
    và ghép nhầm hai cái đó là đúng lỗi "QR của sheet này dán sang sheet kia".
    """
    from mesflow.web.excel_io import _parse_go_router_template

    parsed = _parse_go_router_template(load_workbook(BytesIO(source_bytes), data_only=True),
                                       f'{po_code}.xlsx')
    if not parsed:
        return {}
    part_code_by_key = {p['key']: p['code'] for p in parsed['parts']}
    blocks = {}
    for op in parsed['operations']:
        part_code = part_code_by_key.get(op['part_key'])
        key = (str(part_code or '').upper(),
               str(operation_code_suffix(part_code, op['code']) or '').upper())
        blocks[key] = (op.get('_excel_sheet') or '', int(op.get('_excel_row') or 0))
    return blocks


#: Tên sheet gom tem của những Operation không có block trong workbook gốc.
EXTRA_SHEET_TITLE = 'QR bổ sung'


def _append_leftover_sheet(wb, leftovers):
    """Sheet phụ cho Operation không tìm thấy block trong workbook gốc.

    Lời hứa của tính năng là "mọi Operation quét được của PO đều có tem trong
    file xuất ra". Workbook gốc chỉ chứa những gì có lúc nhập, nên một OP thêm
    tay sau đó -- hoặc một Part sửa tên sheet -- sẽ không khớp block nào. Bỏ
    qua lặng lẽ thì người cầm tờ giấy thiếu đúng tem họ cần mà không biết.
    """
    ws = wb.create_sheet(EXTRA_SHEET_TITLE)
    ws['A1'] = 'Tem QR của Operation không có trong file gốc'
    ws['A1'].font = Font(bold=True, size=13)
    ws['A2'] = ('Những Operation này được thêm sau khi nhập file, nên không có block '
                'tương ứng trong workbook gốc.')
    ws.column_dimensions['A'].width = 26
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 30
    placed = []
    excel_row = 4
    for row in leftovers:
        ws.cell(row=excel_row, column=1, value=str(row['part_code'] or '')).font = Font(bold=True)
        ws.cell(row=excel_row, column=2, value=row['name'])
        ws.cell(row=excel_row, column=3, value=row['code'])
        column = 5
        anchor = _place_qr(ws, row['op_qr'], QR_OP_LABEL, row=excel_row, column=column)
        placed.append({'operation_id': row['id'], 'sheet': ws.title, 'anchor': anchor,
                       'payload': row['op_qr'], 'kind': 'OP'})
        if row['setup_id']:
            setup_anchor = _place_qr(ws, row['setup_qr'], QR_SETUP_LABEL,
                                     row=excel_row, column=column + QR_COLUMN_GAP)
            placed.append({'operation_id': row['setup_id'], 'sheet': ws.title,
                           'anchor': setup_anchor, 'payload': row['setup_qr'],
                           'kind': 'SETUP'})
        excel_row += 8
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    return placed


def _operation_match_keys(row, po_prefix):
    """Mọi cách một Operation thật có thể khớp với một block trong file gốc.

    Mã Operation thật do master_data dựng là ``f"{mã PO}-{hậu tố}"``, còn chỉ
    mục block thì khoá theo HẬU TỐ. Bỏ quên bước gỡ tiền tố PO là lỗi đã thực
    sự xảy ra: mọi tem của file NEWARK (159 cái) rơi hết xuống sheet phụ thay
    vì nằm đúng block của nó, mà tổng số tem vẫn đủ nên nhìn qua tưởng xong.
    """
    part_code = str(row['part_code'] or '').upper()
    code = str(row['code'] or '').upper()
    candidates = []
    if po_prefix and code.startswith(po_prefix):
        stripped = code[len(po_prefix):]
        candidates.append(stripped)
        # Hậu tố có thể đã gập mã Part vào; thử cả bản đã bỏ phần Part đó.
        if part_code and stripped.startswith(f'{part_code}-'):
            candidates.append(stripped[len(part_code) + 1:])
    candidates.append(code)
    candidates.append(str(operation_code_suffix(row['part_code'], row['code']) or '').upper())
    return [(part_code, c) for c in candidates if c]


def _match_block(blocks, row, po_prefix):
    for key in _operation_match_keys(row, po_prefix):
        if key in blocks:
            return blocks[key]
    return None


def _stamp_source_workbook(source_bytes, po, rows):
    """Mở lại workbook gốc và đóng QR vào đúng block của từng Operation."""
    blocks = _index_source_blocks(source_bytes, po['code'])
    if not blocks:
        return None, []
    # keep_vba=False, nhưng KHÔNG data_only: data_only=True sẽ ghi đè công thức
    # bằng giá trị đã cache và tờ router xuất ra mất hết công thức tính giờ.
    wb = load_workbook(BytesIO(source_bytes))
    if EXTRA_SHEET_TITLE in wb.sheetnames:
        # Xuất lại từ một file đã từng xuất: dựng lại sheet phụ từ đầu thay vì
        # chồng tem lên tem cũ.
        wb.remove(wb[EXTRA_SHEET_TITLE])
    lanes = {}
    placed = []
    leftovers = []
    po_prefix = f"{str(po['code'] or '').upper()}-"
    for row in rows:
        block = _match_block(blocks, row, po_prefix)
        sheet_name = block[0] if block else ''
        if not block or sheet_name not in wb.sheetnames:
            leftovers.append(row)
            continue
        sheet_name, excel_row = block
        ws = wb[sheet_name]
        if sheet_name not in lanes:
            lanes[sheet_name] = _qr_lane_column(ws)
        column = lanes[sheet_name]
        anchor = _place_qr(ws, row['op_qr'], QR_OP_LABEL, row=excel_row, column=column)
        placed.append({'operation_id': row['id'], 'sheet': sheet_name, 'anchor': anchor,
                       'payload': row['op_qr'], 'kind': 'OP'})
        if row['setup_id']:
            setup_column = column + QR_COLUMN_GAP
            setup_anchor = _place_qr(ws, row['setup_qr'], QR_SETUP_LABEL,
                                     row=excel_row, column=setup_column)
            placed.append({'operation_id': row['setup_id'], 'sheet': sheet_name,
                           'anchor': setup_anchor, 'payload': row['setup_qr'], 'kind': 'SETUP'})
    for sheet_name, column in lanes.items():
        ws = wb[sheet_name]
        # Khổ in phải ôm được làn QR vừa thêm, nếu không tem rơi sang trang 2.
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.print_area = (f'A1:{get_column_letter(column + QR_COLUMN_GAP + 1)}'
                         f'{max(ws.max_row, 1)}')
    if leftovers:
        placed.extend(_append_leftover_sheet(wb, leftovers))
    return wb, placed


def _generate_router_workbook(po, rows):
    """Workbook router tương đương, cho PO không còn (hoặc chưa từng có) file gốc.

    Giữ đúng bộ nhãn của tờ giấy xưởng đang dùng, để người cầm hai tờ đọc thấy
    như nhau và file xuất ra vẫn nhập lại được bằng chính parser GO ROUTER.
    """
    wb = Workbook()
    wb.remove(wb.active)
    placed = []
    by_part = {}
    for row in rows:
        by_part.setdefault((row['part_sort'], row['part_id'],
                            row['part_code'], row['part_name']), []).append(row)
    for (_, _, part_code, part_name), part_rows in sorted(by_part.items()):
        # Tên sheet Excel: tối đa 31 ký tự và không chứa : \ / ? * [ ]
        title = str(part_name or part_code or 'Part')[:31]
        for bad in ':\\/?*[]':
            title = title.replace(bad, '-')
        ws = wb.create_sheet(title or 'Part')
        ws['A1'] = 'GO ROUTER # LỘ TRÌNH SẢN XUẤT'
        ws['A1'].font = Font(bold=True, size=13)
        ws['A2'] = 'PO NUMBER:'; ws['C2'] = po['code']
        ws['A3'] = 'QTY:'; ws['C3'] = po.get('planned_quantity') or 0
        ws['A4'] = 'TÊN BẢN VẼ:'; ws['C4'] = part_name
        ws['A5'] = 'MÃ BẢN VẼ:'; ws['C5'] = part_code
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['C'].width = 26
        ws.column_dimensions['L'].width = 22
        excel_row = 8
        for index, row in enumerate(part_rows, start=1):
            ws.cell(row=excel_row, column=1,
                    value=f'OPERATION # {index:02d}- {row["name"]}').font = Font(bold=True)
            ws.cell(row=excel_row + 1, column=1, value='Part Number ( Mã bản vẽ )')
            ws.cell(row=excel_row + 1, column=2, value=part_code)
            ws.cell(row=excel_row + 2, column=1, value='Ngày/Tháng/Năm')
            ws.cell(row=excel_row + 2, column=12, value='Thời gian Setup ( phút )')
            ws.cell(row=excel_row + 3, column=1, value='SETUP')
            ws.cell(row=excel_row + 3, column=12,
                    value=int(row['setup_minutes'] or 0) if row['setup_id'] else 0)
            ws.cell(row=excel_row + 4, column=1, value='Nhân viên Setup')
            ws.cell(row=excel_row + 5, column=1, value='Ngày/Tháng/Năm')
            ws.cell(row=excel_row + 5, column=12, value='Thời gian gia công / sản phẩm (s)')
            ws.cell(row=excel_row + 6, column=1, value='Thời gian gia công')
            ws.cell(row=excel_row + 6, column=12,
                    value=float(row['standard_seconds_per_unit'] or 0))
            for offset, label in enumerate(('Hàng đạt:', 'Hàng lỗi:', 'Tổng số lượng sản xuất:',
                                            'Nhân viên SX:', 'Nhân viên QC:'), start=7):
                ws.cell(row=excel_row + offset, column=1, value=label)
            excel_row += 12
        column = _qr_lane_column(ws)
        excel_row = 8
        for row in part_rows:
            anchor = _place_qr(ws, row['op_qr'], QR_OP_LABEL, row=excel_row, column=column)
            placed.append({'operation_id': row['id'], 'sheet': ws.title, 'anchor': anchor,
                           'payload': row['op_qr'], 'kind': 'OP'})
            if row['setup_id']:
                setup_anchor = _place_qr(ws, row['setup_qr'], QR_SETUP_LABEL,
                                         row=excel_row, column=column + QR_COLUMN_GAP)
                placed.append({'operation_id': row['setup_id'], 'sheet': ws.title,
                               'anchor': setup_anchor, 'payload': row['setup_qr'],
                               'kind': 'SETUP'})
            excel_row += 12
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
    return wb, placed


def build_router_workbook(po_id: int):
    """(workbook, danh sách tem đã đóng, có-dùng-file-gốc-không) cho một PO."""
    po = fetch_one('SELECT id,code,product,planned_quantity,source_template_id '
                   'FROM production_orders WHERE id=%s', (int(po_id),))
    if not po:
        return None, [], False
    rows = _load_po_operations(po_id)
    source_bytes = _archived_source_workbook(po.get('source_template_id'))
    if source_bytes:
        wb, placed = _stamp_source_workbook(source_bytes, po, rows)
        if wb is not None and placed:
            return wb, placed, True
    wb, placed = _generate_router_workbook(po, rows)
    return wb, placed, False


def _content_disposition(filename: str) -> str:
    """RFC 5987 cho tên file tiếng Việt có dấu."""
    ascii_fallback = filename.encode('ascii', 'replace').decode('ascii')
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@bp.get('/<int:po_id>/router.xlsx')
@roles_required('admin', 'manager')
def export_production_order_router(po_id: int):
    try:
        wb, placed, from_source = build_router_workbook(po_id)
        if wb is None:
            return jsonify(ok=False, message='Không tìm thấy Production Order.'), 404
        if not placed:
            return jsonify(ok=False, message=(
                'Production Order này chưa có Operation nào để in tem QR.')), 400
        po = fetch_one('SELECT code FROM production_orders WHERE id=%s', (int(po_id),))
        out = BytesIO()
        wb.save(out)
        out.seek(0)
        filename = f'Lộ trình sản xuất {po["code"]} - QR.xlsx'
        response = send_file(
            out, as_attachment=True, download_name=filename, max_age=0,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response.headers['Content-Disposition'] = _content_disposition(filename)
        # Để màn hình nói được "đã in từ file gốc" hay "dựng lại từ dữ liệu".
        response.headers['X-MESFlow-Router-Source'] = 'workbook' if from_source else 'generated'
        response.headers['X-MESFlow-Router-Labels'] = str(len(placed))
        return response
    except Exception as exc:
        return api_error_response(exc, logger_name=__name__)


@bp.get('/<int:po_id>/router-labels')
@roles_required('admin', 'manager')
def preview_router_labels(po_id: int):
    """Danh sách tem sẽ in ra — để kiểm tra mà không phải mở file Excel."""
    try:
        wb, placed, from_source = build_router_workbook(po_id)
        if wb is None:
            return jsonify(ok=False, message='Không tìm thấy Production Order.'), 404
        return jsonify(ok=True, source='workbook' if from_source else 'generated',
                       labels=placed, count=len(placed))
    except Exception as exc:
        return api_error_response(exc, logger_name=__name__)
