"""Xuất lại file Lộ trình sản xuất (GO ROUTER) kèm tem QR cho từng Operation.

LÝ DO TỒN TẠI. Xưởng làm việc trên tờ router in ra, không trên màn hình. Tờ đó
đi từ Excel vào MESFlow lúc nhập Template; cái thiếu là đường ngược lại — in nó
ra kèm QR để người đứng máy quét đúng công đoạn đang làm, và quét tem SETUP
riêng khi phải set máy.

BA QUYẾT ĐỊNH ĐÁNG GHI:

1. Xuất theo PRODUCTION ORDER, không theo Template và không theo từng Part.
   Người dùng chọn MỘT PO và nhận MỘT workbook đại diện toàn bộ Router của PO
   đó: mọi Part của PO nằm trong cùng một file, mỗi Part giữ đúng sheet của nó
   trong file nguồn. QR phải địa chỉ tới ``operations.id`` — danh tính duy nhất
   không đổi tên được — mà id đó chỉ tồn tại sau khi PO được tạo;
   ``template_operations`` không có thứ để quét.

   MỘT PO CHỈ CÓ MỘT FILE NGUỒN, theo đúng kiến trúc hiện tại chứ không phải do
   quy ước thêm vào: ``production_orders.source_template_id`` trỏ tới đúng một
   Template, và mỗi lần nhập lại Template thì ``import_template_workbook()``
   XOÁ toàn bộ ``template_parts``/``template_operations`` rồi dựng lại từ file
   vừa nhập. Nên không tồn tại trạng thái "PO ghép từ nhiều workbook", và không
   có gì phải trộn sheet từ nhiều nguồn. Part/Operation thêm tay sau khi nhập
   thì không khớp được block nào -- và đó là LỖI CỨNG (xem mục 3), không phải
   một nguồn thứ hai.

2. Payload lấy từ ``printable_qr_payload_sql()`` chứ không tự ghép chuỗi. Hàm
   đó là nơi duy nhất trả lời "tem MỚI được phép mang payload nào": tem cũ còn
   dán ngoài xưởng thì giữ nguyên, tem mơ hồ (mã trong QR đã thuộc về Operation
   khác) thì chuyển sang địa chỉ theo id. Tự ghép ``WF|OP|<mã>`` ở đây là dựng
   lại đúng lỗi mơ hồ mà hàm kia sinh ra để chặn.

3. Nguồn DUY NHẤT là workbook gốc. Mỗi lần nhập Template, file được lưu lại
   nguyên bytes (``template_import_blobs``, đánh địa chỉ theo sha256, trên
   volume uploads đã backup). Xuất = mở lại chính file đó rồi ĐÓNG THÊM QR vào,
   nên sheet, tên sheet, merge, độ rộng cột, chiều cao dòng, logo/ảnh, khung in
   và công thức của xưởng còn nguyên.

   KHÔNG có nhánh dựng workbook mới, và cũng KHÔNG có sheet "bổ sung" gom
   những gì không khớp. Tờ router là biểu mẫu của khách; một file "tương đương"
   trông giống nhưng không phải cái xưởng đang dùng, còn một file thiếu tem thì
   người cầm nó chỉ phát hiện khi đã đứng trước máy và không có gì để quét.
   Thiếu file gốc, file gốc không đọc được thành block, không khớp được
   Operation nào, hoặc CÒN BẤT KỲ Operation nào chưa khớp -> báo lỗi kèm đúng
   Part/Operation cần sửa (``RouterSourceUnavailable``, HTTP 409), chứ không
   lặng lẽ xuất ra một tờ giấy khác hay một tờ giấy thiếu.

QR đặt ở LÀN RIÊNG bên phải vùng dữ liệu (cột đầu tiên sau cột cuối cùng có
chữ), không đè lên Part Number, thời gian setup, thời gian gia công, số lượng
hay tên người thực hiện — xem ``_qr_lane_column()``.
"""
from __future__ import annotations

import re
from io import BytesIO
from urllib.parse import quote

from flask import Blueprint, jsonify, request, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XlsxImage
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
#: Chiều cao dải chữ nướng dưới mỗi tem, tính bằng pixel.
QR_LABEL_STRIP = 14
#: Số cột cách giữa tem OP và tem SETUP, để hai ảnh không chạm nhau.
QR_COLUMN_GAP = 2


def _qr_png(payload: str, label: str = '') -> BytesIO:
    """Ảnh PNG của một payload, có sẵn nhãn in bên dưới.

    Nhãn ("QR OP" / "QR Setup") được VẼ VÀO ẢNH chứ không ghi vào ô Excel. Ô
    trong tờ router là biểu mẫu của khách; ghi chữ vào đó -- kể cả một ô đang
    trống -- là sửa nội dung file. Nướng nhãn vào ảnh giữ đúng cả hai điều: thợ
    vẫn đọc được tem nào là tem nào, còn workbook thì chỉ nhận thêm đúng một
    drawing và không một cell nào đổi.

    ``box_size`` tính ngược từ QR_PIXELS thay vì đặt cứng: payload dài hơn cần
    nhiều module hơn, giữ nguyên box_size thì ảnh phình ra khỏi vùng trống.
    """
    import qrcode
    from PIL import Image, ImageDraw

    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(payload)
    qr.make(fit=True)
    modules = qr.modules_count + 2 * qr.border
    # Sàn 3 px/module: payload dài làm số module tăng, và nếu để box_size rơi
    # xuống 2 thì tem in ra bé hơn ~1,5 cm -- cỡ mà máy quét bắt đầu phụ thuộc
    # chất lượng máy in. Thà tem to hơn một chút còn hơn tem không quét được.
    qr.box_size = max(3, QR_PIXELS // modules)
    code = qr.make_image(fill_color='black', back_color='white').convert('1')
    if not label:
        out = BytesIO(); code.save(out, format='PNG'); out.seek(0)
        return out
    canvas = Image.new('1', (code.width, code.height + QR_LABEL_STRIP), 1)
    canvas.paste(code, (0, 0))
    draw = ImageDraw.Draw(canvas)
    # Font mặc định của Pillow: có sẵn ở mọi môi trường, không kéo theo phụ
    # thuộc phông chữ hệ thống. Nhãn chỉ là chữ ASCII ngắn nên đủ đọc.
    try:
        width = int(draw.textlength(label))
    except AttributeError:  # Pillow rất cũ
        width = len(label) * 6
    draw.text((max((code.width - width) // 2, 0), code.height + 1), label, fill=0)
    out = BytesIO(); canvas.save(out, format='PNG'); out.seek(0)
    return out


def _place_qr(ws, payload: str, label: str, *, row: int, column: int):
    """Neo một tem vào ô (row, column). KHÔNG chạm vào bất cứ thứ gì khác.

    Không ghi cell, không đổi bề rộng cột, không đổi chiều cao dòng, không sửa
    khổ in. Sau lời gọi này, khác biệt duy nhất của sheet so với file gốc là
    một drawing mới -- đó chính là hợp đồng "giữ nguyên cấu trúc file nguồn".
    """
    letter = get_column_letter(column)
    anchor = f'{letter}{row}'
    # GIỮ NGUYÊN cỡ pixel gốc của ảnh. Ép width/height về một con số khác là
    # bắt Excel nội suy lại một ảnh 1-bit theo tỉ lệ không nguyên: cạnh module
    # nhoè ra và tem in xong quét chập chờn.
    ws.add_image(XlsxImage(_qr_png(payload, label)), anchor)
    return anchor


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

    Phạm vi là MỘT Production Order và chỉ một: ``o.production_order_id`` lọc
    Operation, và cả hai JOIN đều ràng ``production_order_id`` khớp nhau, nên
    một Part bị gán sai PO hay một dòng SETUP trỏ sang PO khác cũng không kéo
    được Operation lạ vào tờ giấy. Tờ router in ra đại diện đúng một PO.

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
        JOIN parts p ON p.id = o.part_id AND p.production_order_id = o.production_order_id
        LEFT JOIN operations s ON s.parent_operation_id = o.id AND {is_setup}
                              AND s.production_order_id = o.production_order_id
        WHERE o.production_order_id = %s AND {is_production}
        ORDER BY p.sort_order, p.id, o.sort_order, o.id
    """, (int(po_id),))


def _archived_source(template_id):
    """File Excel đã nhập GẦN NHẤT của Template này, kèm danh tính của nó.

    Kho file (``template_import_blobs``, migration 0046) lưu nguyên bytes,
    đánh địa chỉ theo sha256, trên cùng volume uploads đã được backup -- không
    phải file tạm, nên bản gốc vẫn còn sau khi container được dựng lại.

    Chọn lần nhập THÀNH CÔNG gần nhất, vì đó là file đang quyết định nội dung
    Template hiện tại: nhập lại một file mới làm bản cũ hết hiệu lực ngay, và
    sha256 trả về cùng ở đây để người xuất biết mình vừa in từ bản nào.
    """
    if not template_id:
        return None
    from pathlib import Path

    repository = TemplateImportRepository()
    for event in repository.list(template_id=int(template_id), limit=50):
        if event['outcome'] == 'FAILED':
            # File bị từ chối không phải bản dựng nên Template hiện tại.
            continue
        found = repository.file_for(event['id'])
        if not found:
            continue
        path = Path(found['storage_path'])
        if not path.is_file():
            continue
        return {
            'data': path.read_bytes(),
            'filename': found['original_filename'] or event['original_filename'],
            'sha256': event['sha256'],
            'import_id': event['id'],
            'imported_at': str(event['created_at']),
            'outcome': event['outcome'],
        }
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


class RouterPlacementError(Exception):
    """Không có chỗ đặt tem mà không che nội dung của tờ giấy.

    Cố ý KHÔNG tự chèn thêm cột/dòng để lấy chỗ: làm thế là sửa cấu trúc biểu
    mẫu của khách -- đúng thứ mà cả tính năng này tồn tại để không đụng vào.
    """

    def __init__(self, message, *, sheet, operation, reason):
        super().__init__(message)
        self.sheet = sheet
        self.operation = operation
        self.reason = reason


def _existing_drawing_columns(ws):
    """Cột mà ảnh CÓ SẴN của khách (logo, hình sản phẩm) đang chiếm.

    openpyxl giữ neo ảnh gốc dưới dạng đối tượng anchor có toạ độ 0-based;
    ảnh do chính ta vừa thêm thì neo là chuỗi ô. Chỉ quan tâm loại thứ nhất.
    """
    occupied = set()
    for image in ws._images:
        anchor = getattr(image, 'anchor', None)
        marker = getattr(anchor, '_from', None)
        if marker is None:
            continue
        start = marker.col + 1
        end = getattr(getattr(anchor, 'to', None), 'col', marker.col) + 1
        occupied.update(range(start, max(end, start) + 1))
    return occupied


def _assert_lane_is_free(ws, column, span, *, sheet, operation):
    """Làn tem phải trống cả chữ lẫn ảnh, nếu không thì DỪNG và nói rõ vì sao."""
    blocked_by_text = max(
        (cell.column for row in ws.iter_rows() for cell in row
         if cell.value not in (None, '')), default=0)
    if column <= blocked_by_text:
        raise RouterPlacementError(
            f"Sheet '{sheet}': không còn vùng trống bên phải để đặt tem cho Operation "
            f'{operation} mà không che chữ. Hãy chừa trống vài cột bên phải khối dữ '
            'liệu trong file Lộ trình sản xuất rồi nhập lại.',
            sheet=sheet, operation=operation, reason='NO_FREE_COLUMN')
    drawings = _existing_drawing_columns(ws)
    clash = drawings.intersection(range(column, column + span))
    if clash:
        raise RouterPlacementError(
            f"Sheet '{sheet}': vùng định đặt tem cho Operation {operation} đang có "
            f'hình/logo của file gốc (cột {sorted(clash)[0]}). Hãy chừa trống vài cột '
            'bên phải khối dữ liệu trong file Lộ trình sản xuất rồi nhập lại.',
            sheet=sheet, operation=operation, reason='DRAWING_IN_THE_WAY')


def _stamp_source_workbook(source_bytes, po, rows):
    """Mở lại workbook gốc và đóng QR vào đúng block của từng Operation."""
    blocks = _index_source_blocks(source_bytes, po['code'])
    if not blocks:
        return None, [], 0, []
    # keep_vba=False, nhưng KHÔNG data_only: data_only=True sẽ ghi đè công thức
    # bằng giá trị đã cache và tờ router xuất ra mất hết công thức tính giờ.
    wb = load_workbook(BytesIO(source_bytes))
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
        # Kiểm TRƯỚC khi đặt: một tem đã dán lên rồi thì không gỡ ra được nữa.
        _assert_lane_is_free(ws, column, QR_COLUMN_GAP + 2,
                             sheet=sheet_name, operation=row['code'])
        anchor = _place_qr(ws, row['op_qr'], QR_OP_LABEL, row=excel_row, column=column)
        placed.append({'operation_id': row['id'], 'sheet': sheet_name, 'anchor': anchor,
                       'payload': row['op_qr'], 'kind': 'OP'})
        if row['setup_id']:
            setup_column = column + QR_COLUMN_GAP
            setup_anchor = _place_qr(ws, row['setup_qr'], QR_SETUP_LABEL,
                                     row=excel_row, column=setup_column)
            placed.append({'operation_id': row['setup_id'], 'sheet': sheet_name,
                           'anchor': setup_anchor, 'payload': row['setup_qr'], 'kind': 'SETUP'})
    # Operation nào không tìm được block thì trả NGUYÊN dòng về cho người gọi:
    # nó phải biết Part nào, OP nào, để câu lỗi chỉ đúng chỗ cần sửa.
    matched = len(rows) - len(leftovers)
    return wb, placed, matched, leftovers


class RouterSourceUnavailable(Exception):
    """Không có file gốc đủ tin cậy để đóng tem lên.

    Cố ý là LỖI chứ không phải rơi về một workbook tự dựng. Tờ router là biểu
    mẫu của khách (khung in, logo, ô ký, công thức tính giờ); một file "tương
    đương" trông giống nhưng không phải cái xưởng đang dùng, và người cầm tờ
    giấy không có cách nào biết mình đang cầm bản nào. Thà không xuất được và
    nói rõ phải nhập lại Template nguồn.
    """

    def __init__(self, message, *, reason):
        super().__init__(message)
        self.reason = reason


def build_router_workbook(po_id: int):
    """(po, workbook, tem đã đóng, thông tin nguồn) cho một PO.

    Chỉ có MỘT đường: mở lại workbook đã nhập của Template sinh ra PO này rồi
    đóng tem lên đó. Không có nhánh dựng mới.
    """
    po = fetch_one('SELECT id,code,product,planned_quantity,source_template_id '
                   'FROM production_orders WHERE id=%s', (int(po_id),))
    if not po:
        return None, None, [], None
    rows = _load_po_operations(po_id)
    if not rows:
        raise RouterSourceUnavailable(
            'Production Order này chưa có Operation nào để in tem QR.',
            reason='NO_OPERATIONS')
    source = _archived_source(po.get('source_template_id'))
    if not source:
        raise RouterSourceUnavailable(
            'Không còn file Excel gốc của Template đã tạo PO này, nên không thể xuất '
            'đúng biểu mẫu Lộ trình sản xuất. Hãy nhập lại file Excel Router của '
            'Template nguồn (Template → Công cụ → Nhập từ Excel), rồi xuất lại.',
            reason='NO_SOURCE_WORKBOOK')
    wb, placed, matched, unmatched = _stamp_source_workbook(source['data'], po, rows)
    if wb is None:
        raise RouterSourceUnavailable(
            f"File Excel gốc đang lưu ({source['filename']}) không đọc được thành các "
            'block "OPERATION # ..." nên không biết chèn tem vào đâu. Hãy nhập lại '
            'đúng file Lộ trình sản xuất của Template nguồn rồi xuất lại.',
            reason='SOURCE_NOT_A_ROUTER')
    if not matched:
        raise RouterSourceUnavailable(
            f"Không khớp được Operation nào của PO với file Excel gốc đang lưu "
            f"({source['filename']}). Rất có thể file đang lưu không phải file đã tạo "
            'ra PO này. Hãy nhập lại đúng file Lộ trình sản xuất của Template nguồn '
            'rồi xuất lại.',
            reason='NO_BLOCK_MATCHED')
    if unmatched:
        # Xuất THIẾU mà vẫn ra file là thứ người cầm tờ giấy không phát hiện
        # được: họ ra xưởng, tới công đoạn đó, và không có tem để quét. Thà
        # chặn lại và nói đúng Part/Operation nào chưa có trong file gốc.
        listed = '; '.join(
            f"Part {row['part_code']} · {row['name']} ({row['code']})"
            for row in unmatched[:10])
        more = f' và {len(unmatched) - 10} Operation khác' if len(unmatched) > 10 else ''
        raise RouterSourceUnavailable(
            f'{len(unmatched)} Operation của PO này không có trong file Excel gốc đang '
            f'lưu ({source["filename"]}), nên không thể in tem cho chúng: {listed}{more}. '
            'Những Operation này được thêm sau khi nhập file. Hãy cập nhật file Lộ trình '
            'sản xuất của Template nguồn rồi nhập lại, sau đó xuất lại.',
            reason='UNMATCHED_OPERATIONS')
    return po, wb, placed, {**source, 'matched': matched, 'unmatched': []}


def _router_filename(po_code: str) -> str:
    """``Router_<POCODE>_QR.xlsx`` — mã PO đã lọc sạch ký tự không an toàn.

    Tên file đi vào header HTTP và vào thư mục Download của người dùng, nên chỉ
    giữ chữ/số/gạch: dấu ngoặc kép hay xuống dòng lọt vào Content-Disposition
    là một lỗ tiêm header, còn dấu / thì thành đường dẫn.
    """
    safe = re.sub(r'[^A-Za-z0-9._-]+', '-', str(po_code or '')).strip('-.')
    return f'Router_{safe or "PO"}_QR.xlsx'


def _content_disposition(filename: str) -> str:
    """RFC 5987 cho tên file tiếng Việt có dấu."""
    ascii_fallback = filename.encode('ascii', 'replace').decode('ascii')
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@bp.get('/<int:po_id>/router.xlsx')
@roles_required('admin', 'manager')
def export_production_order_router(po_id: int):
    try:
        po, wb, placed, source = build_router_workbook(po_id)
        if wb is None:
            return jsonify(ok=False, message='Không tìm thấy Production Order.'), 404
        out = BytesIO()
        wb.save(out)
        out.seek(0)
        filename = _router_filename(po['code'])
        response = send_file(
            out, as_attachment=True, download_name=filename, max_age=0,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response.headers['Content-Disposition'] = _content_disposition(filename)
        # Danh tính CHÍNH XÁC của bản gốc vừa đóng tem lên: người nhận biết tờ
        # giấy trên tay dựng từ lần nhập nào, và hash nào.
        response.headers['X-MESFlow-Router-Source'] = 'workbook'
        response.headers['X-MESFlow-Router-Source-Sha256'] = source['sha256']
        response.headers['X-MESFlow-Router-Source-Import'] = str(source['import_id'])
        response.headers['X-MESFlow-Router-Labels'] = str(len(placed))
        response.headers['X-MESFlow-Router-Matched'] = str(source['matched'])
        response.headers['X-MESFlow-Router-Unmatched'] = str(len(source['unmatched']))
        return response
    except RouterSourceUnavailable as exc:
        # 409: yêu cầu hợp lệ, nhưng trạng thái dữ liệu chưa cho phép xuất. Kèm
        # `reason` để giao diện tắt nút và chỉ đúng việc phải làm.
        return jsonify(ok=False, message=str(exc), reason=exc.reason), 409
    except Exception as exc:
        return api_error_response(exc, logger_name=__name__)


@bp.get('/<int:po_id>/router-labels')
@roles_required('admin', 'manager')
def preview_router_labels(po_id: int):
    """Danh sách tem sẽ in ra — để kiểm tra mà không phải mở file Excel."""
    try:
        po, wb, placed, source = build_router_workbook(po_id)
        if wb is None:
            return jsonify(ok=False, message='Không tìm thấy Production Order.'), 404
        return jsonify(ok=True, source='workbook', labels=placed, count=len(placed),
                       source_file={'filename': source['filename'],
                                    'sha256': source['sha256'],
                                    'import_id': source['import_id'],
                                    'imported_at': source['imported_at']},
                       matched=source['matched'], unmatched=source['unmatched'])
    except RouterSourceUnavailable as exc:
        return jsonify(ok=False, message=str(exc), reason=exc.reason), 409
    except Exception as exc:
        return api_error_response(exc, logger_name=__name__)
