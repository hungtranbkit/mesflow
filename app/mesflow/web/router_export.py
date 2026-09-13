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


#: Lề chừa quanh tem bên trong ô marker, tính bằng pixel.
QR_MARKER_MARGIN_PX = 3
#: Dưới cỡ này thì tem in ra bắt đầu phụ thuộc máy in (~1,3 cm ở 96 DPI).
QR_MIN_READABLE_PX = 48

#: Bề rộng cột mặc định của Excel quy ra pixel, và hệ số đổi "số ký tự" -> px.
#: Excel lưu bề rộng cột theo số ký tự của phông mặc định, chiều cao dòng theo
#: point. Muốn biết một ô rộng bao nhiêu pixel thì phải đổi cả hai.
DEFAULT_COLUMN_WIDTH_CHARS = 8.43
DEFAULT_ROW_HEIGHT_POINTS = 15.0


def _column_width_px(ws, column):
    dimension = ws.column_dimensions.get(get_column_letter(column))
    width = getattr(dimension, 'width', None) or DEFAULT_COLUMN_WIDTH_CHARS
    # Công thức Excel dùng cho phông mặc định: 7 px mỗi ký tự + 5 px đệm.
    return int(round(width * 7)) + 5


def _row_height_px(ws, row):
    dimension = ws.row_dimensions.get(row)
    points = getattr(dimension, 'height', None) or DEFAULT_ROW_HEIGHT_POINTS
    return int(round(points * 96.0 / 72.0))


def _marker_region(ws, row, column):
    """Vùng ô mà marker chiếm: chính nó, hoặc cả merged range chứa nó.

    Trả (min_row, min_col, max_row, max_col). Chỉ ĐỌC merge, không tạo, không gỡ.
    """
    for merged in ws.merged_cells.ranges:
        if (merged.min_row <= row <= merged.max_row
                and merged.min_col <= column <= merged.max_col):
            return merged.min_row, merged.min_col, merged.max_row, merged.max_col
    return row, column, row, column


def _region_size_px(ws, region):
    min_row, min_col, max_row, max_col = region
    width = sum(_column_width_px(ws, c) for c in range(min_col, max_col + 1))
    height = sum(_row_height_px(ws, r) for r in range(min_row, max_row + 1))
    return width, height


def _fit_text_block(text, target_w, target_h):
    """Ảnh 1-bit của ``text`` co/giãn VỪA KHUNG (target_w x target_h).

    Tự xuống tối đa 2 dòng (cắt tại dấu phân cách gần giữa) để tận dụng khung mà
    vẫn ĐỌC TRỌN chuỗi -- không bao giờ cắt chữ ra ngoài khung. Chọn cách bày
    (1 dòng hay 2 dòng) cho cỡ chữ lớn nhất. Dùng cho nhãn payload dưới tem QR.
    """
    from PIL import Image, ImageDraw

    resample = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS')
    no_dither = getattr(getattr(Image, 'Dither', Image), 'NONE', 0)
    measure = ImageDraw.Draw(Image.new('L', (8, 8)))

    def width_of(s):
        try:
            return max(int(measure.textlength(s)), 1)
        except AttributeError:  # Pillow rất cũ
            return max(len(s) * 6, 1)

    def block(lines):
        widths = [width_of(s) for s in lines]
        w, h = max(widths), 11 * len(lines)
        img = Image.new('L', (w, h), 255)
        draw = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            draw.text((max((w - widths[i]) // 2, 0), i * 11), line, fill=0)
        return img, w, h

    candidates = [[text]]
    if len(text) > 3:
        mid = len(text) // 2
        cut = mid
        best = None
        for i in range(1, len(text)):
            if text[i] in '|-_ /' and (best is None or abs(i - mid) < abs(best - mid)):
                best = i
        if best is not None:
            cut = best + 1
        candidates.append([text[:cut], text[cut:]])

    best_img, best_scale = None, -1.0
    for lines in candidates:
        img, w, h = block(lines)
        scale = min(target_w / w, target_h / h)   # lấp đầy khung, cho phép phóng to
        if scale > best_scale:
            new_w, new_h = max(int(w * scale), 1), max(int(h * scale), 1)
            best_img = (img.resize((new_w, new_h), resample)
                        if (new_w, new_h) != (w, h) else img)
            best_scale = scale
    return best_img.convert('1', dither=no_dither)


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
    # Nhãn dưới tem là CHÍNH chuỗi payload của QR (OP hiện payload OP, Setup hiện
    # payload Setup) và phải ĐỌC ĐƯỢC TRỌN VẸN, không bị cắt. Dành một DẢI NHÃN
    # rộng bằng QR và cao ~nửa QR; chuỗi dài tự xuống 2 dòng và co vừa dải đó
    # (xem _fit_text_block). Dải nhãn đủ lớn để vẫn đọc được kể cả sau khi tem
    # thu vào ô marker -- anchor giữ ĐÚNG TỈ LỆ ảnh nên nhãn không bị bóp dẹt
    # (xem _compute_qr_placements).
    side = code.width
    band_h = max(int(side * 0.5), 16)
    text_img = _fit_text_block(label, side, max(band_h - 2, 1))
    canvas = Image.new('1', (side, code.height + band_h), 1)
    canvas.paste(code, (0, 0))
    canvas.paste(text_img, (max((side - text_img.width) // 2, 0),
                            code.height + max((band_h - text_img.height) // 2, 0)))
    out = BytesIO(); canvas.save(out, format='PNG'); out.seek(0)
    return out


def _place_qr(ws, payload: str, label: str, *, row: int, column: int, fit_region=None):
    """Neo một tem. KHÔNG chạm vào bất cứ thứ gì khác của sheet.

    Không ghi cell, không đổi bề rộng cột, không đổi chiều cao dòng, không sửa
    khổ in. Khác biệt duy nhất so với file gốc là một drawing mới.

    ``fit_region`` là vùng ô của marker. Có nó thì tem được THU VỪA và CĂN GIỮA
    trong đúng vùng đó. Đây chính là chỗ đã hỏng: trước đây ảnh được neo đúng ô
    marker nhưng giữ nguyên cỡ gốc ~75x89 px, trong khi một ô mặc định chỉ
    64x20 px -- tem tràn qua bốn dòng và nằm lệch hẳn ra ngoài ô, nên nhìn trên
    file thì "QR không nằm trong ô QRCODE" dù anchor đúng.

    Không có ``fit_region`` (đường làn trống cho file chưa có marker) thì giữ
    nguyên cỡ gốc như cũ.
    """
    letter = get_column_letter(column)
    anchor = f'{letter}{row}'
    image = XlsxImage(_qr_png(payload, label))
    if fit_region is None:
        # Đường cũ: cỡ pixel gốc, không nội suy.
        ws.add_image(image, anchor)
        return anchor

    from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.utils.units import pixels_to_EMU

    region_width, region_height = _region_size_px(ws, fit_region)
    side = min(region_width, region_height) - 2 * QR_MARKER_MARGIN_PX
    side = max(side, 1)
    # Vuông: QR méo là QR không quét được.
    offset_x = max((region_width - side) // 2, 0)
    offset_y = max((region_height - side) // 2, 0)
    marker = AnchorMarker(col=fit_region[1] - 1, colOff=pixels_to_EMU(offset_x),
                          row=fit_region[0] - 1, rowOff=pixels_to_EMU(offset_y))
    image.anchor = OneCellAnchor(
        _from=marker,
        ext=XDRPositiveSize2D(pixels_to_EMU(side), pixels_to_EMU(side)))
    image.width = image.height = side
    ws.add_image(image, image.anchor)
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
    """Bản đồ block của workbook gốc.

    Trả về ``(blocks, starts)``: ``blocks`` là (mã Part, hậu tố mã OP) ->
    (tên sheet, dòng tiêu đề); ``starts`` là tên sheet -> danh sách dòng tiêu đề
    đã sắp xếp, dùng để suy ra BIÊN của mỗi block (một block chạy tới ngay trước
    block kế tiếp) khi đi tìm marker.

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
        return {}, {}, {}
    part_code_by_key = {p['key']: p['code'] for p in parsed['parts']}
    blocks = {}
    starts = {}
    for op in parsed['operations']:
        part_code = part_code_by_key.get(op['part_key'])
        key = (str(part_code or '').upper(),
               str(operation_code_suffix(part_code, op['code']) or '').upper())
        sheet = op.get('_excel_sheet') or ''
        excel_row = int(op.get('_excel_row') or 0)
        blocks[key] = (sheet, excel_row)
        starts.setdefault(sheet, []).append(excel_row)
    for sheet in starts:
        starts[sheet].sort()
    # Part -> sheet của nó. OP do người dùng thêm sau này phải rơi vào ĐÚNG tờ
    # của Part mình, chứ không phải một tờ nào đó còn chỗ.
    sheet_of_part = {}
    for op in parsed['operations']:
        part_code = str(part_code_by_key.get(op['part_key']) or '').upper()
        sheet_of_part.setdefault(part_code, op.get('_excel_sheet') or '')
    return blocks, starts, sheet_of_part


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


#: Chữ đặt sẵn trong template để nói "dán QR vào ĐÚNG ô này".
#:
#: Template router thế hệ sau sẽ chừa sẵn ô chứa đúng chữ này, thay vì để hệ
#: thống tự đoán chỗ trống. Nhờ vậy người vẽ biểu mẫu quyết định tem nằm ở đâu
#: -- họ đang cầm tờ giấy, họ biết chỗ nào in ra đẹp -- còn phần mềm không phải
#: đoán. File hiện tại chưa có marker nên vẫn đi đường cũ (xem _qr_lane_column).
QR_MARKER_TEXT = 'QRCODE'


class RouterMarkerError(Exception):
    """Marker QRCODE có nhưng không nói rõ được nó thuộc về Operation nào.

    Đoán bừa ở đây nghĩa là dán tem của công đoạn này lên ô của công đoạn khác,
    và cái sai đó chỉ lộ ra khi thợ quét nhầm việc. Thà dừng và chỉ đúng sheet +
    ô + lý do.
    """

    def __init__(self, message, *, sheet, cell='', context='', reason='', operation=''):
        super().__init__(message)
        self.sheet = sheet
        self.cell = cell
        self.context = context
        self.reason = reason
        self.operation = operation


def _merged_anchor(ws, row, column):
    """Ô neo thật của một ô: góc trên-trái của vùng merge nếu nó nằm trong merge.

    Không gỡ merge, không tạo merge -- chỉ đọc. Neo ảnh vào ô giữa một vùng đã
    merge thì Excel đẩy ảnh về vị trí khó đoán, nên phải quy về góc trên-trái.
    """
    for merged in ws.merged_cells.ranges:
        if (merged.min_row <= row <= merged.max_row
                and merged.min_col <= column <= merged.max_col):
            return merged.min_row, merged.min_col
    return row, column


def _label_text(ws, values_ws, row, column):
    """Chữ NGƯỜI ĐỌC thấy ở một ô, kể cả khi ô đó là công thức.

    Biểu mẫu router thật chỉ ghi nhãn bằng chữ ở block ĐẦU TIÊN của tờ đầu
    tiên; mọi block sau đó nhắc lại nhãn bằng công thức (``=$L$10``), và các tờ
    khác nhắc lại bằng công thức liên sheet. Đọc thẳng từ workbook mở kiểu giữ
    công thức thì những ô ấy chỉ ra ``=$L$10`` -- không có chữ 'Thời gian
    Setup', nên không phân biệt nổi marker SETUP với marker OP. Giá trị Excel
    đã cache mới là chữ thật.
    """
    from mesflow.web.excel_io import _deaccent

    if values_ws is not None:
        cached = _deaccent(values_ws.cell(row=row, column=column).value)
        if cached:
            return cached
    return _deaccent(ws.cell(row=row, column=column).value)


def _setup_region(ws, start_row, end_row, values_ws=None):
    """Khoảng dòng thuộc phần SETUP bên trong một block Operation.

    Bố cục tờ router đặt nhãn 'Thời gian Setup ( phút )' rồi tới số phút, sau đó
    mới tới 'Thời gian gia công / sản phẩm'. Phần nằm giữa hai nhãn đó là vùng
    nói về việc set máy -- marker rơi vào đấy thuộc về OP SETUP, không phải OP
    sản xuất. Trả (0, -1) khi block không khai báo setup, tức là không có vùng nào.
    """
    setup_label = cycle_label = None
    for row in range(start_row, end_row + 1):
        for cell in ws[row]:
            text = _label_text(ws, values_ws, cell.row, cell.column)
            if not text:
                continue
            if setup_label is None and 'thoi gian setup' in text:
                setup_label = row
            if cycle_label is None and 'thoi gian gia cong / san pham' in text:
                cycle_label = row
    if setup_label is None:
        return 0, -1
    return setup_label, (cycle_label - 1) if cycle_label and cycle_label > setup_label else end_row


def _scan_markers(ws, starts, values_ws=None):
    """Marker QRCODE trên một sheet, gán về block và phân loại OP / SETUP.

    Trả ``{dòng tiêu đề block: {'OP': (row, col), 'SETUP': (row, col)}}``.

    Hai thứ bị CHẶN ngay tại đây, vì cả hai đều dẫn tới dán tem sai chỗ mà
    không ai biết: marker nằm ngoài mọi block (không suy được nó thuộc công
    đoạn nào), và hai marker cùng loại trong một block (không biết cái nào là
    cái thật).
    """
    if not starts:
        starts = []
    found = {}
    bounds = []
    for index, start in enumerate(starts):
        end = starts[index + 1] - 1 if index + 1 < len(starts) else ws.max_row
        bounds.append((start, end))
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str) or cell.value.strip().upper() != QR_MARKER_TEXT:
                continue
            owner = next((b for b in bounds if b[0] <= cell.row <= b[1]), None)
            if owner is None:
                raise RouterMarkerError(
                    f"Sheet '{ws.title}' ô {cell.coordinate}: có chữ {QR_MARKER_TEXT} nhưng "
                    'không nằm trong block OPERATION nào, nên không biết dán QR của công '
                    'đoạn nào vào đây. Đặt marker bên trong đúng block của Operation.',
                    sheet=ws.title, cell=cell.coordinate, reason='MARKER_OUTSIDE_BLOCK')
            start, end = owner
            setup_from, setup_to = _setup_region(ws, start, end, values_ws)
            kind = 'SETUP' if setup_from <= cell.row <= setup_to else 'OP'
            slot = found.setdefault(start, {})
            if kind in slot:
                previous = slot[kind]
                raise RouterMarkerError(
                    f"Sheet '{ws.title}': block dòng {start} có hai ô {QR_MARKER_TEXT} cho "
                    f'cùng một tem {kind} (ô {previous[2]} và ô {cell.coordinate}). Mỗi '
                    'Operation chỉ được có một chỗ dán, nếu không sẽ không biết tem thật '
                    'nằm ở đâu.',
                    sheet=ws.title, cell=cell.coordinate, context=f'block dòng {start}',
                    reason='DUPLICATE_MARKER')
            slot[kind] = (cell.row, cell.column, cell.coordinate)
    return found


def _extend_print_area(print_area, last_row):
    """Nới vùng in xuống tới dòng cuối của block vừa thêm.

    Chỉ kéo DÀI biên dưới; cột và góc trên giữ nguyên. Block mới mà nằm ngoài
    print area thì nó đơn giản là không in ra, và người nhận tờ giấy không hề
    biết mình thiếu một công đoạn.
    """
    import re as _re

    areas = print_area if isinstance(print_area, (list, tuple)) else [print_area]
    out = []
    for area in areas:
        text = str(area)
        match = _re.match(r"^(?:'?[^'!]+'?!)?\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)$", text)
        if not match:
            out.append(text)
            continue
        left, top, right, bottom = match.groups()
        prefix = text[:match.start(1)]
        out.append(f'{prefix}{left}{top}:${right}${max(int(bottom), int(last_row))}')
    return out if len(out) > 1 else out[0]


class RouterBlockTemplateError(Exception):
    """Không suy được block mẫu an toàn để dựng block cho OP người dùng thêm."""

    def __init__(self, message, *, sheet, part='', operation='', reason=''):
        super().__init__(message)
        self.sheet = sheet
        self.part = part
        self.operation = operation
        self.reason = reason


def _block_bounds(starts, sheet_rows, index):
    """(đầu, cuối) của block thứ ``index`` trong một sheet."""
    start = starts[index]
    end = starts[index + 1] - 1 if index + 1 < len(starts) else sheet_rows
    return start, end


def _block_pitch(starts, sheet_rows):
    """Khoảng cách giữa hai block liên tiếp — nhịp bố cục của chính tờ đó.

    Dùng nhịp chứ không dùng ``max_row``: một block thường có vài dòng trống ở
    cuối (chỗ ký, chỗ ghi tay), và ``max_row`` dừng ở ô CÓ CHỮ cuối cùng. Lấy
    theo max_row thì block mới bị kéo lên sát block trước, phá mất khoảng cách
    mà biểu mẫu cố ý chừa ra — in ra là dính vào nhau.

    Chỉ có một block thì không suy được nhịp; khi đó dùng tới hết phần có chữ.
    """
    if len(starts) >= 2:
        return starts[-1] - starts[-2]
    return max(sheet_rows - starts[-1] + 1, 1)


def _clone_block(ws, template_start, template_end, destination_start):
    """Sao một block Operation xuống ``destination_start``, giữ nguyên hình dạng.

    Chép giá trị, style (font/fill/viền/căn lề/định dạng số), chiều cao dòng và
    các vùng merge — dịch theo độ lệch dòng. Công thức được dịch tham chiếu bằng
    Translator của openpyxl, nên một ô ``=L14*C3/3600`` ở block mẫu trỏ đúng ô
    tương ứng của block mới thay vì vẫn trỏ về block cũ.

    KHÔNG tự thiết kế gì: mọi thứ block mới có đều đến từ block mẫu của chính
    sheet đó.
    """
    from copy import copy

    from openpyxl.formula.translate import Translator
    from openpyxl.utils import get_column_letter

    offset = destination_start - template_start
    for source_row in range(template_start, template_end + 1):
        target_row = source_row + offset
        height = ws.row_dimensions[source_row].height
        if height is not None:
            ws.row_dimensions[target_row].height = height
        for cell in ws[source_row]:
            target = ws.cell(row=target_row, column=cell.column)
            value = cell.value
            if isinstance(value, str) and value.startswith('='):
                value = Translator(
                    value, origin=f'{get_column_letter(cell.column)}{source_row}'
                ).translate_formula(f'{get_column_letter(cell.column)}{target_row}')
            target.value = value
            if cell.has_style:
                target._style = copy(cell._style)
    for merged in list(ws.merged_cells.ranges):
        if template_start <= merged.min_row and merged.max_row <= template_end:
            ws.merge_cells(start_row=merged.min_row + offset, start_column=merged.min_col,
                           end_row=merged.max_row + offset, end_column=merged.max_col)


def _rewrite_block_fields(ws, start, end, *, sequence, row, values_ws=None,
                          values_offset=0):
    """Thay đúng những ô NÓI VỀ Operation trong một block vừa sao chép.

    Tìm theo NHÃN như lúc đọc file, không theo offset cứng: block mẫu của mỗi
    template có thể xếp khác nhau, và thứ duy nhất ổn định là cái nhãn nằm cạnh
    con số.

    Block vừa sao chép chưa có giá trị cache, nên nhãn được tra ở ĐÚNG ô tương
    ứng của block mẫu (``values_offset`` dòng phía trên). Cần thế vì trên biểu
    mẫu thật, nhãn của mọi block trừ block đầu đều là công thức nhắc lại.
    """
    title = ws.cell(row=start, column=1)
    title.value = f'OPERATION # {sequence:02d}- {row["name"]}'
    for excel_row in range(start, end + 1):
        for cell in ws[excel_row]:
            text = _label_text(ws, values_ws, cell.row - values_offset, cell.column)
            if not text:
                continue
            if 'thoi gian setup' in text:
                _set_value_below(ws, cell, int(row['setup_minutes'] or 0)
                                 if row['setup_id'] else 0)
            elif 'thoi gian gia cong / san pham' in text:
                _set_value_below(ws, cell, float(row['standard_seconds_per_unit'] or 0))
            elif 'part number' in text:
                ws.cell(row=cell.row, column=cell.column + 1).value = row['part_code']


def _set_value_below(ws, label_cell, value):
    """Số nằm ngay dưới nhãn, cùng cột -- đúng cách parser đọc nó lên."""
    ws.cell(row=label_cell.row + 1, column=label_cell.column).value = value


def _stamp_source_workbook(source_bytes, po, rows, warnings=None):
    """Mở lại workbook gốc và đóng QR vào đúng block của từng Operation.

    HAI CHẾ ĐỘ ĐẶT TEM, marker thắng tuyệt đối:

      * template có ô ghi ``QRCODE`` trong block -> dán đúng ô đó. Người vẽ biểu
        mẫu đã nói chỗ, phần mềm không đoán nữa.
      * không có marker -> giữ nguyên cách cũ: làn trống bên phải vùng dữ liệu.

    Chế độ quyết định theo CẢ WORKBOOK, không theo từng ô. Một tờ router là một
    biểu mẫu: hoặc người vẽ đã chừa ô QRCODE, hoặc chưa.

    Workbook đã có marker mà một block THIẾU ô QRCODE -> KHÔNG chặn cả file nữa
    (luật user chốt: thiếu ô ở bất kỳ block nào chỉ CẢNH BÁO). Các block có ô
    QRCODE vẫn được dán đúng ô; block thiếu thì bỏ qua tem của block đó và ghi
    một cảnh báo (sheet/dòng/Operation/loại tem) vào ``warnings`` để route trả
    ra. KHÔNG rơi về làn tự đoán cho block thiếu -- "đặt tùy ý cột/dòng" là thứ
    hợp đồng cấm; thà bỏ trống tem đó và nói rõ còn hơn đặt sai chỗ lặng lẽ.

    Lưu ý: đây CHỈ là ô QRCODE bị thiếu. Marker HỎNG (mồ côi ngoài block,
    trùng loại trong một block) vẫn DỪNG cả lần xuất -- đó là template vẽ sai,
    không phải vẽ sót.

    ``warnings`` (tuỳ chọn): list mà người gọi truyền vào để nhận các cảnh báo
    thiếu-marker; giữ nguyên bộ giá trị trả về 4 phần tử để không vỡ call-site.
    """
    if warnings is None:
        warnings = []
    blocks, starts, sheet_of_part = _index_source_blocks(source_bytes, po['code'])
    if not blocks:
        return None, [], 0, []
    # keep_vba=False, nhưng KHÔNG data_only: data_only=True sẽ ghi đè công thức
    # bằng giá trị đã cache và tờ router xuất ra mất hết công thức tính giờ.
    wb = load_workbook(BytesIO(source_bytes))
    # Bản đọc GIÁ TRỊ của cùng file, chỉ để nhận ra CHỮ trên nhãn. Không bao giờ
    # ghi vào bản này: data_only=True thay công thức bằng giá trị đã cache, lưu
    # lại là tờ router mất hết công thức tính giờ.
    values = load_workbook(BytesIO(source_bytes), data_only=True)

    def values_sheet(name):
        return values[name] if name in values.sheetnames else None

    lanes = {}
    placed = []
    leftovers = []
    po_prefix = f"{str(po['code'] or '').upper()}-"

    def lane_for(ws, sheet_name):
        if sheet_name not in lanes:
            lanes[sheet_name] = _qr_lane_column(ws)
        return lanes[sheet_name]

    # Hai loại "không khớp block" KHÁC HẲN nhau, và gộp chúng lại là sai:
    #
    #   * Part của OP có tờ trong template -> đây là OP người dùng thêm vào sau
    #     khi nhập, việc hoàn toàn hợp lệ. Dựng thêm một block cho nó TRONG ĐÚNG
    #     tờ đó, sao từ block mẫu của chính tờ ấy.
    #   * Part không có tờ nào -> ánh xạ đã hỏng (file đang lưu không phải file
    #     sinh ra PO này). Không đoán, trả về cho người gọi báo lỗi.
    appended = {}

    def ensure_block(row):
        """Trả (sheet, dòng tiêu đề) cho một OP chưa có block, hoặc None."""
        part_code = str(row['part_code'] or '').upper()
        sheet_name = sheet_of_part.get(part_code)
        if not sheet_name or sheet_name not in wb.sheetnames:
            return None
        ws = wb[sheet_name]
        sheet_starts = starts.get(sheet_name) or []
        if not sheet_starts:
            raise RouterBlockTemplateError(
                f"Sheet '{sheet_name}' không có block OPERATION nào để lấy làm mẫu, nên "
                f"không dựng được block cho Operation {row['code']} (Part {row['part_code']}) "
                'mà người dùng thêm sau khi nhập. Hãy bổ sung công đoạn này vào file Lộ '
                'trình sản xuất của Template nguồn rồi nhập lại.',
                sheet=sheet_name, part=row['part_code'], operation=row['code'],
                reason='NO_TEMPLATE_BLOCK')
        # Block CUỐI của tờ làm mẫu: biên dưới của nó là biên tờ, nên hình dạng
        # chắc chắn đầy đủ, và chèn tiếp ngay sau nó là chỗ template dành cho
        # công đoạn thêm.
        last_index = len(sheet_starts) - 1
        sheet_rows = appended.get(sheet_name, ws.max_row)
        pitch = _block_pitch(sheet_starts, sheet_rows)
        template_start = sheet_starts[last_index]
        template_end = template_start + pitch - 1
        if template_end < template_start:
            raise RouterBlockTemplateError(
                f"Sheet '{sheet_name}': không xác định được ranh giới block mẫu để dựng "
                f"block cho Operation {row['code']}.",
                sheet=sheet_name, part=row['part_code'], operation=row['code'],
                reason='UNCLEAR_BLOCK_BOUNDS')
        height = pitch
        destination = template_start + pitch
        _clone_block(ws, template_start, template_end, destination)
        _rewrite_block_fields(ws, destination, destination + height - 1,
                              sequence=len(sheet_starts) + 1, row=row,
                              values_ws=values_sheet(sheet_name),
                              values_offset=destination - template_start)
        sheet_starts.append(destination)
        appended[sheet_name] = destination + height - 1
        # Block mới phải in được: nới print area nếu template có đặt.
        if ws.print_area:
            ws.print_area = _extend_print_area(ws.print_area, appended[sheet_name])
        # Marker nằm trong block mẫu đã được sao sang block mới -> quét lại tờ này.
        return sheet_name, destination

    # LƯỢT 1 -- dựng đủ block trước. Phải xong hết rồi mới quét marker: một
    # block nhân bản mang theo marker của block mẫu, và nếu quét trước thì
    # marker đó chưa tồn tại. Ngược lại, nếu vừa dán vừa nhân bản thì block mẫu
    # có thể đã bị xoá chữ marker trước khi được sao -- đúng lỗi đã gặp.
    assignments = []
    for row in rows:
        block = _match_block(blocks, row, po_prefix)
        if not block or block[0] not in wb.sheetnames:
            block = ensure_block(row)
        if not block:
            leftovers.append(row)
            continue
        assignments.append((row, block))

    # Quét marker trên MỌI sheet trước khi dán bất cứ thứ gì: marker hỏng
    # (mồ côi / trùng) phải chặn cả lần xuất, chứ không phải chặn khi đã dán
    # được nửa chừng.
    markers = {name: _scan_markers(wb[name], starts.get(name, []), values_sheet(name))
               for name in wb.sheetnames}
    # Có marker hay không là câu hỏi của CẢ workbook, không phải của từng ô.
    # Một tờ router là MỘT biểu mẫu: người vẽ nó hoặc đã chừa ô QRCODE, hoặc
    # chưa. Nếu hỏi theo từng chỗ dán thì một biểu mẫu chừa thiếu vài ô sẽ lặng
    # lẽ có vài tem rơi vào làn tự đoán -- đúng cái "đặt tùy ý cột/dòng khác"
    # mà hợp đồng cấm, và không ai nhìn ra cho tới khi cầm tờ giấy in.
    marker_mode = 'MARKER' if any(markers.values()) else 'NONE'

    # LƯỢT 2 -- dán tem.
    used = set()
    cleared = []
    for row, block in assignments:
        sheet_name, excel_row = block
        ws = wb[sheet_name]
        slots = markers.get(sheet_name, {}).get(excel_row, {})

        def stamp(kind, payload, label, operation_id, fallback_column):
            marker = slots.get(kind)
            if marker:
                marker_row, marker_col, coordinate = marker
                # Vùng của marker: chính ô đó, hoặc cả merged range chứa nó. Tem
                # được thu vừa và căn giữa TRONG vùng này -- xem _place_qr.
                region = _marker_region(ws, marker_row, marker_col)
                # Ô marker là chỗ DUY NHẤT được phép đổi nội dung: nó là chỗ đặt
                # sẵn, và để nguyên chữ 'QRCODE' thì tờ giấy in ra có chữ đó nằm
                # dưới tem. openpyxl chỉ cho ghi ô góc trên-trái của merged
                # range; ô marker trong merge luôn CHÍNH LÀ ô đó.
                ws.cell(row=region[0], column=region[1]).value = None
                if (marker_row, marker_col) != (region[0], region[1]):
                    ws.cell(row=marker_row, column=marker_col).value = None
                anchor = _place_qr(ws, payload, label, row=region[0], column=region[1],
                                   fit_region=region)
                width, height = _region_size_px(ws, region)
                side = min(width, height) - 2 * QR_MARKER_MARGIN_PX
                placed.append({'operation_id': operation_id, 'sheet': sheet_name,
                               'anchor': anchor, 'payload': payload, 'kind': kind,
                               'placement': 'marker', 'marker_cell': coordinate,
                               'region': f'{get_column_letter(region[1])}{region[0]}:'
                                         f'{get_column_letter(region[3])}{region[2]}',
                               'size_px': max(side, 1),
                               'too_small': side < QR_MIN_READABLE_PX})
                return
            if marker_mode == 'MARKER':
                # Biểu mẫu đã chừa ô QRCODE ở chỗ khác, nghĩa là người vẽ nó
                # quyết định chỗ dán. Thiếu một ô ở block này là biểu mẫu vẽ
                # SÓT -- không phải lời mời phần mềm tự chọn cột. Luật user chốt:
                # thiếu ô QRCODE ở bất kỳ block nào CHỈ CẢNH BÁO, KHÔNG chặn cả
                # file. Bỏ qua tem của riêng block này (không rơi về làn tự
                # đoán -- "đặt tùy ý cột/dòng" là thứ hợp đồng cấm), các block
                # có ô QRCODE vẫn được dán, và ghi rõ chỗ thiếu để người sửa
                # biểu mẫu tới thẳng nơi cần bổ sung ô QRCODE.
                warnings.append({
                    'reason': 'MISSING_MARKER',
                    'sheet': sheet_name,
                    'block_row': excel_row,
                    'operation': row['code'],
                    'kind': kind,
                    'message': (
                        f"Sheet '{sheet_name}': block dòng {excel_row} "
                        f"(Operation {row['code']}) chưa có ô {QR_MARKER_TEXT} cho "
                        f'tem {kind}, trong khi các block khác của file này đã có. '
                        f'Tem {kind} của block này được BỎ QUA; các block có ô '
                        f'{QR_MARKER_TEXT} vẫn được dán bình thường. Thêm ô '
                        f'{QR_MARKER_TEXT} vào đúng block này rồi nhập lại Template '
                        'nguồn nếu muốn in tem cho công đoạn này.'),
                })
                return
            column = fallback_column()
            _assert_lane_is_free(ws, column, QR_COLUMN_GAP + 2,
                                 sheet=sheet_name, operation=row['code'])
            anchor = _place_qr(ws, payload, label, row=excel_row, column=column)
            placed.append({'operation_id': operation_id, 'sheet': sheet_name,
                           'anchor': anchor, 'payload': payload, 'kind': kind,
                           'placement': 'lane', 'marker_cell': ''})

        stamp('OP', row['op_qr'], QR_OP_LABEL, row['id'],
              lambda: lane_for(ws, sheet_name))
        used.add((sheet_name, excel_row, 'OP'))
        if row['setup_id']:
            stamp('SETUP', row['setup_qr'], QR_SETUP_LABEL, row['setup_id'],
                  lambda: lane_for(ws, sheet_name) + QR_COLUMN_GAP)
            used.add((sheet_name, excel_row, 'SETUP'))

    # Marker CÒN THỪA -- chỗ chừa cho tem SETUP ở block mà Operation không khai
    # báo setup -- phải được xoá chữ. 'QRCODE' là chữ đặt chỗ, không phải nội
    # dung của biểu mẫu: để nguyên thì tờ giấy in ra có chữ QRCODE lù lù giữa
    # block. Không dán gì vào đó, chỉ xoá chữ.
    for sheet_name, slots_by_block in markers.items():
        ws = wb[sheet_name]
        for block_row, slots in slots_by_block.items():
            for kind, (marker_row, marker_col, _coordinate) in slots.items():
                if (sheet_name, block_row, kind) in used:
                    continue
                region = _marker_region(ws, marker_row, marker_col)
                ws.cell(row=region[0], column=region[1]).value = None
                if (marker_row, marker_col) != (region[0], region[1]):
                    ws.cell(row=marker_row, column=marker_col).value = None
                cleared.append({'sheet': sheet_name, 'block_row': block_row,
                                'kind': kind, 'marker_cell': _coordinate})
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


# EMU (English Metric Units) trên mỗi pixel ở 96 DPI -- đơn vị neo drawing OOXML.
QR_EMU_PER_PX = 9525

_DRAWING_REL_TYPE = ('http://schemas.openxmlformats.org/officeDocument/2006/'
                     'relationships/drawing')
_IMAGE_REL_TYPE = ('http://schemas.openxmlformats.org/officeDocument/2006/'
                   'relationships/image')


def _compute_qr_placements(source_bytes, po, rows, warnings):
    """Tính chỗ đặt tem QR trên workbook gốc mà KHÔNG sửa file.

    ĐỌC-để-tính, KHÔNG BAO GIỜ save workbook. Load lại rồi save qua openpyxl sẽ
    ghi lại toàn bộ công thức, XOÁ cached value và bật ``fullCalcOnLoad`` -> khi
    mở file phải recalc, và những công thức tự tham chiếu vốn có sẵn trong biểu
    mẫu (ví dụ nhãn ``=$A$9`` nhắc lại giữa các block) hoá thành ``Err:522``
    (vòng tham chiếu) lan khắp tờ. Vì thế ở đây chỉ ĐO hình học để biết chèn tem
    vào đâu; việc chèn do :func:`_graft_qr_into_workbook` làm bằng vá OOXML tối
    thiểu, giữ nguyên mọi cell/công thức/cached value của file gốc.

    Trả ``(placed, matched, leftovers, clear_cells)``. Mỗi placement mang sẵn
    ảnh PNG và toạ độ neo (EMU) để dựng drawing; ``clear_cells`` là {sheet: {ô
    marker}} để :func:`_graft_qr_into_workbook` XOÁ CHỮ 'QRCODE' (chỉ value, giữ
    style/merge) trước khi dán ảnh. Giữ luật đã chốt: block thiếu ô QRCODE trong
    workbook đã có marker -> cảnh báo, vẫn xuất. KHÔNG dựng thêm block (clone) vì
    clone là sửa file; OP người dùng thêm sau khi nhập -> cảnh báo, không in tem.
    """
    from PIL import Image

    blocks, starts, sheet_of_part = _index_source_blocks(source_bytes, po['code'])
    if not blocks:
        return None, 0, [], {}
    # Chỉ để đo bề rộng cột / chiều cao dòng / merge -- workbook này KHÔNG bao
    # giờ được save.
    wb = load_workbook(BytesIO(source_bytes))
    values = load_workbook(BytesIO(source_bytes), data_only=True)

    def values_sheet(name):
        return values[name] if name in values.sheetnames else None

    markers = {name: _scan_markers(wb[name], starts.get(name, []), values_sheet(name))
               for name in wb.sheetnames}
    marker_mode = 'MARKER' if any(markers.values()) else 'NONE'
    # Mọi ô có chữ QRCODE phải được XOÁ CHỮ trước khi dán ảnh: 'QRCODE' là chữ
    # đặt chỗ, để nguyên thì tờ in ra có chữ đó nằm dưới/ló ra cạnh tem. Chỉ xoá
    # VALUE của đúng ô marker (giữ style/merge/border/kích thước); ô nào không
    # dán ảnh (slot SETUP thừa) cũng xoá để không còn chữ QRCODE lù lù giữa tờ.
    clear_cells = {}
    for sheet_name, blocks_slots in markers.items():
        coords = {coord for slots in blocks_slots.values()
                  for (_r, _c, coord) in slots.values()}
        if coords:
            clear_cells[sheet_name] = coords
    po_prefix = f"{str(po['code'] or '').upper()}-"
    placed = []
    leftovers = []
    lanes = {}

    def lane_for(ws, sheet_name):
        if sheet_name not in lanes:
            lanes[sheet_name] = _qr_lane_column(ws)
        return lanes[sheet_name]

    assignments = []
    for row in rows:
        block = _match_block(blocks, row, po_prefix)
        if not block or block[0] not in wb.sheetnames:
            part_code = str(row['part_code'] or '').upper()
            added_sheet = sheet_of_part.get(part_code)
            if added_sheet:
                # Part CÓ tờ trong template -> OP thêm sau khi nhập. Trước đây
                # dựng thêm block; giữ nguyên file gốc thì không dựng được, nên
                # nói rõ và vẫn xuất.
                warnings.append({
                    'reason': 'ADDED_OP_NO_BLOCK', 'sheet': added_sheet,
                    'block_row': 0, 'operation': row['code'], 'kind': 'OP',
                    'message': (
                        f"Operation {row['code']} (Part {row['part_code']}) được thêm "
                        'sau khi nhập, chưa có block trong file Excel gốc. Ở chế độ giữ '
                        'nguyên file gốc, MESFlow không dựng thêm block nên KHÔNG in được '
                        'tem cho công đoạn này. Bổ sung công đoạn vào Template nguồn rồi '
                        'nhập lại nếu muốn in tem.')})
                continue
            leftovers.append(row)
            continue
        assignments.append((row, block))

    for row, block in assignments:
        sheet_name, excel_row = block
        ws = wb[sheet_name]
        slots = markers.get(sheet_name, {}).get(excel_row, {})

        def emit(kind, payload, operation_id, fallback_column):
            marker = slots.get(kind)
            if marker:
                marker_row, marker_col, coordinate = marker
                region = _marker_region(ws, marker_row, marker_col)
                region_w, region_h = _region_size_px(ws, region)
                side = max(min(region_w, region_h) - 2 * QR_MARKER_MARGIN_PX, 1)
                offset_x = max((region_w - side) // 2, 0)
                offset_y = max((region_h - side) // 2, 0)
                # CHỈ ảnh QR VUÔNG side x side, KHÔNG nhãn chữ dưới tem (payload
                # vẫn nằm trong QR). Không dải nhãn -> ext vuông như QR.
                png = _qr_png(payload).getvalue()
                placed.append({
                    'operation_id': operation_id, 'sheet': sheet_name, 'kind': kind,
                    'payload': payload, 'placement': 'marker', 'marker_cell': coordinate,
                    'anchor': f'{get_column_letter(region[1])}{region[0]}',
                    'region': f'{get_column_letter(region[1])}{region[0]}:'
                              f'{get_column_letter(region[3])}{region[2]}',
                    'size_px': max(side, 1), 'too_small': side < QR_MIN_READABLE_PX,
                    'png': png,
                    'col0': region[1] - 1, 'row0': region[0] - 1,
                    'colOff': offset_x * QR_EMU_PER_PX, 'rowOff': offset_y * QR_EMU_PER_PX,
                    'cx': side * QR_EMU_PER_PX, 'cy': side * QR_EMU_PER_PX})
                return
            if marker_mode == 'MARKER':
                # Block thiếu ô QRCODE trong biểu mẫu đã có marker: chỉ CẢNH BÁO,
                # bỏ qua tem của block này, KHÔNG rơi về làn tự đoán.
                warnings.append({
                    'reason': 'MISSING_MARKER', 'sheet': sheet_name,
                    'block_row': excel_row, 'operation': row['code'], 'kind': kind,
                    'message': (
                        f"Sheet '{sheet_name}': block dòng {excel_row} "
                        f"(Operation {row['code']}) chưa có ô {QR_MARKER_TEXT} cho tem "
                        f'{kind}, trong khi các block khác của file này đã có. Tem {kind} '
                        f'của block này được BỎ QUA; các block có ô {QR_MARKER_TEXT} vẫn '
                        f'được dán bình thường. Thêm ô {QR_MARKER_TEXT} vào đúng block này '
                        'rồi nhập lại Template nguồn nếu muốn in tem cho công đoạn này.')})
                return
            # Biểu mẫu CHƯA có ô QRCODE nào (marker_mode NONE): giữ cách cũ --
            # làn trống bên phải, cỡ ảnh gốc.
            column = fallback_column()
            _assert_lane_is_free(ws, column, QR_COLUMN_GAP + 2,
                                 sheet=sheet_name, operation=row['code'])
            png = _qr_png(payload).getvalue()
            image = Image.open(BytesIO(png))
            width_px, height_px = image.width, image.height
            placed.append({
                'operation_id': operation_id, 'sheet': sheet_name, 'kind': kind,
                'payload': payload, 'placement': 'lane', 'marker_cell': '',
                'anchor': f'{get_column_letter(column)}{excel_row}',
                'png': png, 'col0': column - 1, 'row0': excel_row - 1,
                'colOff': 0, 'rowOff': 0,
                'cx': width_px * QR_EMU_PER_PX, 'cy': height_px * QR_EMU_PER_PX})

        # CHỈ chèn ảnh QR, KHÔNG in chữ/payload dưới tem: payload đã nằm trong
        # chính mã QR; tờ router chỉ nhận thêm ảnh, không có dòng chữ lem xuống.
        emit('OP', row['op_qr'], row['id'],
             lambda: lane_for(ws, sheet_name))
        if row['setup_id']:
            emit('SETUP', row['setup_qr'], row['setup_id'],
                 lambda: lane_for(ws, sheet_name) + QR_COLUMN_GAP)

    matched = len(rows) - len(leftovers)
    return placed, matched, leftovers, clear_cells


def _public_labels(placed):
    """``placed`` nhưng bỏ dữ liệu chỉ dùng để dựng drawing (PNG bytes, toạ độ
    EMU) -- phần còn lại là JSON được, đúng các trường màn xem trước vẫn dùng."""
    drop = {'png', 'col0', 'row0', 'colOff', 'rowOff', 'cx', 'cy'}
    return [{k: v for k, v in item.items() if k not in drop} for item in placed]


def _worksheet_file_map(parts):
    """{tên sheet -> đường dẫn part của sheet} đọc từ workbook.xml + rels."""
    wb_xml = parts['xl/workbook.xml'].decode('utf-8')
    rels_xml = parts['xl/_rels/workbook.xml.rels'].decode('utf-8')
    rel_target = {}
    for m in re.finditer(r'<Relationship\b[^>]*/>', rels_xml):
        t = m.group(0)
        rid = re.search(r'Id="([^"]+)"', t)
        tgt = re.search(r'Target="([^"]+)"', t)
        if rid and tgt:
            rel_target[rid.group(1)] = _norm_target('xl/workbook.xml', tgt.group(1))
    name_to_file = {}
    for m in re.finditer(r'<sheet\b[^>]*/>', wb_xml):
        t = m.group(0)
        name = re.search(r'name="([^"]+)"', t)
        rid = re.search(r'r:id="([^"]+)"', t)
        if name and rid and rid.group(1) in rel_target:
            name_to_file[name.group(1)] = rel_target[rid.group(1)]
    return name_to_file


def _norm_target(base_part, target):
    """Giải đường dẫn Target (tương đối/tuyệt đối) của một Relationship về
    đường dẫn part trong gói zip."""
    target = target.lstrip('/')
    if target.startswith('xl/'):
        return target
    segments = base_part.split('/')[:-1]
    for seg in target.split('/'):
        if seg == '..':
            segments = segments[:-1]
        elif seg not in ('', '.'):
            segments.append(seg)
    return '/'.join(segments)


def _next_rid(rels_xml):
    used = [int(m.group(1)) for m in re.finditer(r'Id="rId(\d+)"', rels_xml)]
    return f'rId{(max(used) if used else 0) + 1}'


def _one_cell_anchor(placement, rel_id, cnvpr_id):
    """XML ``<xdr:oneCellAnchor>`` neo một ảnh QR vào một ô, cỡ cố định.

    Neo góc trên-trái vào (col0,row0) + offset (EMU) và giãn đúng cx/cy -- khớp
    cách openpyxl dựng cho marker placement, nhưng ở đây ta tự viết để KHÔNG phải
    save lại workbook.
    """
    return (
        '<xdr:oneCellAnchor>'
        f'<xdr:from><xdr:col>{placement["col0"]}</xdr:col>'
        f'<xdr:colOff>{placement["colOff"]}</xdr:colOff>'
        f'<xdr:row>{placement["row0"]}</xdr:row>'
        f'<xdr:rowOff>{placement["rowOff"]}</xdr:rowOff></xdr:from>'
        f'<xdr:ext cx="{placement["cx"]}" cy="{placement["cy"]}"/>'
        '<xdr:pic><xdr:nvPicPr>'
        f'<xdr:cNvPr id="{cnvpr_id}" name="QR {cnvpr_id}"/><xdr:cNvPicPr/></xdr:nvPicPr>'
        f'<xdr:blipFill><a:blip r:embed="{rel_id}"/>'
        '<a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
        '<xdr:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{placement["cx"]}" cy="{placement["cy"]}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic>'
        '<xdr:clientData/></xdr:oneCellAnchor>')


def _clear_marker_value(sheet_xml, coord):
    """Xoá VALUE của đúng ô ``coord`` trong XML sheet, GIỮ NGUYÊN mọi thứ khác.

    Chỉ bỏ ``t=`` và nội dung (``<v>``/``<is>``/``<f>``) của một ô, giữ lại thuộc
    tính style ``s=`` -> ô thành rỗng nhưng style/viền/định dạng còn nguyên. Merge
    (``<mergeCell>``), bề rộng cột, chiều cao dòng nằm ở chỗ khác nên không đụng.
    """
    def repl(match):
        attrs = match.group(1)
        style = re.search(r'\ss="\d+"', attrs)
        return f'<c r="{coord}"{style.group(0) if style else ""}/>'

    pattern = re.compile(
        r'<c r="%s"([^>]*?)(?:/>|>.*?</c>)' % re.escape(coord), re.S)
    return pattern.sub(repl, sheet_xml, count=1)


def _graft_qr_into_workbook(source_bytes, placed, clear_cells=None):
    """Chèn ảnh QR vào workbook gốc bằng vá OOXML tối thiểu, giữ nguyên mọi thứ
    khác BYTE-FOR-BYTE (trừ đúng ô marker được xoá chữ 'QRCODE').

    KHÔNG đi qua openpyxl load/save (việc đó ghi lại toàn bộ công thức, xoá cached
    value, bật fullCalcOnLoad -> Err:522). Chỉ thêm/đổi đúng các part cần cho ảnh:
    thêm ảnh vào ``xl/media``; nối ``<xdr:oneCellAnchor>`` vào drawing của từng
    sheet (dùng drawing sẵn có, hoặc tạo mới nếu sheet chưa có), thêm quan hệ ảnh,
    khai báo content-type khi cần; và XOÁ CHỮ ở đúng ô marker QRCODE (chỉ value,
    giữ style/merge) trước khi dán. Công thức/cached value/calcPr của mọi ô khác
    không đổi một byte.
    """
    import zipfile

    clear_cells = clear_cells or {}
    if not placed and not clear_cells:
        return source_bytes
    zin = zipfile.ZipFile(BytesIO(source_bytes))
    parts = {name: zin.read(name) for name in zin.namelist()}
    name_to_file = _worksheet_file_map(parts)

    # LƯỢT 0 -- xoá chữ 'QRCODE' ở đúng ô marker (chỉ value). Làm trước khi dán
    # ảnh; ảnh sẽ neo đè lên chính ô đó.
    for sheet_name, coords in clear_cells.items():
        sheet_file = name_to_file.get(sheet_name)
        if not sheet_file or sheet_file not in parts:
            continue
        sheet_xml = parts[sheet_file].decode('utf-8')
        for coord in coords:
            sheet_xml = _clear_marker_value(sheet_xml, coord)
        parts[sheet_file] = sheet_xml.encode('utf-8')

    def _max_num(pattern):
        nums = [int(m.group(1)) for name in parts
                for m in [re.match(pattern, name)] if m]
        return max(nums) if nums else 0

    next_media = _max_num(r'xl/media/image(\d+)\.\w+$') + 1
    next_drawing = _max_num(r'xl/drawings/drawing(\d+)\.xml$') + 1
    content_types = parts['[Content_Types].xml'].decode('utf-8')

    empty_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
                  '<Relationships xmlns="http://schemas.openxmlformats.org/'
                  'package/2006/relationships"></Relationships>')

    by_sheet = {}
    for item in placed:
        by_sheet.setdefault(item['sheet'], []).append(item)

    for sheet_name, items in by_sheet.items():
        sheet_file = name_to_file.get(sheet_name)
        if not sheet_file or sheet_file not in parts:
            continue
        base = sheet_file.rsplit('/', 1)[-1]
        sheet_rels_path = f'xl/worksheets/_rels/{base}.rels'
        drawing_path = None
        if sheet_rels_path in parts:
            for m in re.finditer(r'<Relationship\b[^>]*/>',
                                 parts[sheet_rels_path].decode('utf-8')):
                if _DRAWING_REL_TYPE in m.group(0):
                    tgt = re.search(r'Target="([^"]+)"', m.group(0)).group(1)
                    drawing_path = _norm_target(sheet_file, tgt)
                    break
        if drawing_path is None:
            # Sheet chưa có drawing -> dựng mới và nối vào sheet.
            drawing_path = f'xl/drawings/drawing{next_drawing}.xml'
            next_drawing += 1
            parts[drawing_path] = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
                '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/'
                '2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/'
                'drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships"></xdr:wsDr>').encode('utf-8')
            rels_xml = parts.get(sheet_rels_path, empty_rels.encode('utf-8')).decode('utf-8')
            rid = _next_rid(rels_xml)
            rel = (f'<Relationship Id="{rid}" Type="{_DRAWING_REL_TYPE}" '
                   f'Target="../drawings/{drawing_path.rsplit("/", 1)[-1]}"/>')
            parts[sheet_rels_path] = rels_xml.replace(
                '</Relationships>', rel + '</Relationships>').encode('utf-8')
            sheet_xml = parts[sheet_file].decode('utf-8')
            if '<drawing ' not in sheet_xml:
                # ``<drawing r:id=...>`` cần prefix r trên thẻ <worksheet>. Biểu
                # mẫu thật đã có sẵn (chúng vốn có drawing); workbook dựng tay
                # bằng openpyxl thì chưa, nên khai báo nếu thiếu.
                if 'xmlns:r=' not in sheet_xml[:sheet_xml.index('>') + 1]:
                    sheet_xml = sheet_xml.replace(
                        '<worksheet ',
                        '<worksheet xmlns:r="http://schemas.openxmlformats.org/'
                        'officeDocument/2006/relationships" ', 1)
                sheet_xml = sheet_xml.replace(
                    '</worksheet>', f'<drawing r:id="{rid}"/></worksheet>')
                parts[sheet_file] = sheet_xml.encode('utf-8')
            if f'PartName="/{drawing_path}"' not in content_types:
                content_types = content_types.replace(
                    '</Types>',
                    f'<Override PartName="/{drawing_path}" ContentType='
                    '"application/vnd.openxmlformats-officedocument.drawing+xml"/></Types>')
        if 'Extension="png"' not in content_types:
            # Chèn ngay sau thẻ mở <Types ...> để khai báo phần mở rộng png.
            content_types = re.sub(
                r'(<Types\b[^>]*>)',
                r'\1<Default Extension="png" ContentType="image/png"/>',
                content_types, count=1)

        dbase = drawing_path.rsplit('/', 1)[-1]
        drawing_rels_path = f'xl/drawings/_rels/{dbase}.rels'
        drawing_xml = parts[drawing_path].decode('utf-8')
        # Anchor QR dùng prefix r: (r:embed) và a: (a:blip/a:xfrm...). Một drawing
        # sẵn có mà trước đó CHƯA có ảnh nào có thể chỉ khai báo xdr (+a) và
        # THIẾU xmlns:r -> chèn r:embed vào sẽ thành "unbound prefix". Bổ sung
        # khai báo còn thiếu trên thẻ <xdr:wsDr> trước khi nối anchor.
        wsdr_start = drawing_xml.index('<xdr:wsDr')
        head_end = drawing_xml.index('>', wsdr_start)
        for prefix, uri in (
                ('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'),
                ('a', 'http://schemas.openxmlformats.org/drawingml/2006/main')):
            if f'xmlns:{prefix}=' not in drawing_xml[wsdr_start:head_end]:
                drawing_xml = drawing_xml.replace(
                    '<xdr:wsDr', f'<xdr:wsDr xmlns:{prefix}="{uri}"', 1)
                head_end = drawing_xml.index('>', drawing_xml.index('<xdr:wsDr'))
        drawing_rels = parts.get(drawing_rels_path, empty_rels.encode('utf-8')).decode('utf-8')
        rel_num = max([int(m.group(1)) for m in re.finditer(r'Id="rId(\d+)"', drawing_rels)]
                      or [0])
        cnvpr_num = max([int(m.group(1)) for m in re.finditer(r'<xdr:cNvPr id="(\d+)"', drawing_xml)]
                        or [0])
        new_rels = ''
        for item in items:
            media_name = f'image{next_media}.png'
            next_media += 1
            parts[f'xl/media/{media_name}'] = item['png']
            rel_num += 1
            cnvpr_num += 1
            rid = f'rId{rel_num}'
            new_rels += (f'<Relationship Id="{rid}" Type="{_IMAGE_REL_TYPE}" '
                         f'Target="../media/{media_name}"/>')
            drawing_xml = drawing_xml.replace(
                '</xdr:wsDr>', _one_cell_anchor(item, rid, cnvpr_num) + '</xdr:wsDr>')
        parts[drawing_rels_path] = drawing_rels.replace(
            '</Relationships>', new_rels + '</Relationships>').encode('utf-8')
        parts[drawing_path] = drawing_xml.encode('utf-8')

    parts['[Content_Types].xml'] = content_types.encode('utf-8')

    out = BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
        written = set()
        for item in zin.infolist():
            zout.writestr(item, parts[item.filename])
            written.add(item.filename)
        for name, data in parts.items():
            if name not in written:
                zout.writestr(name, data)
    return out.getvalue()


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
    missing_markers = []
    placed, matched, unmatched, clear_cells = _compute_qr_placements(
        source['data'], po, rows, warnings=missing_markers)
    if placed is None:
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
        # Tới được đây nghĩa là Part của những Operation này KHÔNG có tờ nào
        # trong file gốc -- không phải "người dùng thêm công đoạn" (trường hợp
        # đó đã được dựng thêm block ngay trong tờ của Part), mà là ánh xạ hỏng:
        # file đang lưu nhiều khả năng không phải file đã sinh ra PO này.
        raise RouterSourceUnavailable(
            f'{len(unmatched)} Operation của PO này thuộc Part không có trong file Excel '
            f'gốc đang lưu ({source["filename"]}), nên không biết in tem vào tờ nào: '
            f'{listed}{more}. Nhiều khả năng file đang lưu không phải file đã tạo ra PO '
            'này. Hãy nhập lại đúng file Lộ trình sản xuất của Template nguồn rồi xuất lại.',
            reason='UNMATCHED_OPERATIONS')
    # Chèn tem bằng vá OOXML tối thiểu -> bytes cuối, GIỮ NGUYÊN file gốc
    # (trừ đúng ô marker được xoá chữ 'QRCODE').
    output_bytes = _graft_qr_into_workbook(source['data'], placed, clear_cells)
    return po, output_bytes, placed, {**source, 'matched': matched, 'unmatched': [],
                                      'missing_markers': missing_markers}


def _router_filename(po_code: str) -> str:
    """``Router_<POCODE>_QR.xlsx`` — mã PO đã lọc sạch ký tự không an toàn.

    Tên file đi vào header HTTP và vào thư mục Download của người dùng, nên chỉ
    giữ chữ/số/gạch: dấu ngoặc kép hay xuống dòng lọt vào Content-Disposition
    là một lỗ tiêm header, còn dấu / thì thành đường dẫn.
    """
    safe = re.sub(r'[^A-Za-z0-9._-]+', '-', str(po_code or '')).strip('-.')
    return f'Router_{safe or "PO"}_QR.xlsx'


#: Biểu mẫu chưa chừa ô QRCODE thì vẫn xuất được -- file thật hiện tại của
#: xưởng là loại đó -- nhưng phải NÓI RA, chứ không im lặng đặt tem vào làn
#: trống rồi để người dùng tưởng đó là chỗ đã thiết kế.
MARKER_MODE_NONE_WARNING = (
    'File Excel nguồn chưa có ô ' + QR_MARKER_TEXT + ' nào, nên tem QR được đặt vào '
    'làn trống bên phải mỗi block. Muốn cố định chỗ dán, hãy thêm ô ' + QR_MARKER_TEXT
    + ' vào biểu mẫu Lộ trình sản xuất rồi nhập lại Template nguồn.')


def _marker_mode(placed):
    """'MARKER' nếu file nguồn có chừa ô QRCODE, 'NONE' nếu đi làn tự đoán."""
    return 'MARKER' if any(p.get('placement') == 'marker' for p in placed) else 'NONE'


def _router_warnings(placed, source):
    """Mọi cảnh báo NON-FATAL của một lần xuất, dạng câu chữ cho người dùng.

    Hai nguồn, cùng một tinh thần "file vẫn xuất, nhưng phải NÓI RA":

      * cả workbook không có ô QRCODE nào -> tem đi làn tự đoán (MODE_NONE).
      * workbook CÓ ô QRCODE nhưng vài block thiếu -> tem của block đó bị bỏ qua.
    """
    out = []
    if _marker_mode(placed) == 'NONE':
        out.append(MARKER_MODE_NONE_WARNING)
    out.extend(w['message'] for w in source.get('missing_markers', []))
    return out


def _content_disposition(filename: str) -> str:
    """RFC 5987 cho tên file tiếng Việt có dấu."""
    ascii_fallback = filename.encode('ascii', 'replace').decode('ascii')
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"


@bp.get('/<int:po_id>/router.xlsx')
@roles_required('admin', 'manager')
def export_production_order_router(po_id: int):
    try:
        po, output_bytes, placed, source = build_router_workbook(po_id)
        if output_bytes is None:
            return jsonify(ok=False, message='Không tìm thấy Production Order.'), 404
        out = BytesIO(output_bytes)
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
        response.headers['X-MESFlow-Router-Marker-Mode'] = _marker_mode(placed)
        # Block thiếu ô QRCODE không còn chặn xuất -- nhưng tờ giấy ra sẽ THIẾU
        # tem ở những block đó, nên phải nói ra qua header để giao diện cảnh báo.
        missing = source.get('missing_markers', [])
        response.headers['X-MESFlow-Router-Missing-Markers'] = str(len(missing))
        return response
    except (RouterMarkerError, RouterPlacementError, RouterBlockTemplateError) as exc:
        # Cùng họ 409: file hợp lệ về mặt HTTP nhưng nội dung chưa cho phép dán
        # tem. Trả kèm sheet/ô để người sửa biểu mẫu tới thẳng chỗ cần sửa.
        return jsonify(ok=False, message=str(exc), reason=exc.reason,
                       sheet=exc.sheet, cell=getattr(exc, 'cell', ''),
                       part=getattr(exc, 'part', ''),
                       operation=getattr(exc, 'operation', '')), 409
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
        po, output_bytes, placed, source = build_router_workbook(po_id)
        if output_bytes is None:
            return jsonify(ok=False, message='Không tìm thấy Production Order.'), 404
        mode = _marker_mode(placed)
        return jsonify(ok=True, source='workbook', labels=_public_labels(placed),
                       count=len(placed),
                       source_file={'filename': source['filename'],
                                    'sha256': source['sha256'],
                                    'import_id': source['import_id'],
                                    'imported_at': source['imported_at']},
                       marker_mode=mode,
                       warnings=_router_warnings(placed, source),
                       missing_markers=source.get('missing_markers', []),
                       matched=source['matched'], unmatched=source['unmatched'])
    except (RouterMarkerError, RouterPlacementError, RouterBlockTemplateError) as exc:
        return jsonify(ok=False, message=str(exc), reason=exc.reason,
                       sheet=exc.sheet, cell=getattr(exc, 'cell', ''),
                       part=getattr(exc, 'part', ''),
                       operation=getattr(exc, 'operation', '')), 409
    except RouterSourceUnavailable as exc:
        return jsonify(ok=False, message=str(exc), reason=exc.reason), 409
    except Exception as exc:
        return api_error_response(exc, logger_name=__name__)
