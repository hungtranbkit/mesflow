from __future__ import annotations
from mesflow.domain.policy import is_production, production_only_sql, type_value_sql

from datetime import datetime
from io import BytesIO
import json
import re

import logging
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file, session
from openpyxl import Workbook, load_workbook

from mesflow.db.connection import transaction
from mesflow.web.auth import login_required,roles_required
from mesflow.core.time_policy import site_now
from mesflow.core.upload_policy import validate_excel_upload
from mesflow.db.repositories.base import ConflictError,NotFoundError
from mesflow.web.errors import api_error_response
from mesflow.db.repositories.master_data import (_validate_template_part_codes,
    _validate_template_operation_codes, TemplateValidationError)
from mesflow.db.repositories.setup_ops import SETUP_CODE_SUFFIX
from mesflow.db.repositories.template_imports import (TemplateImportRepository,

    OUTCOME_CREATED, OUTCOME_REPLACED, OUTCOME_FAILED)

# Bộ lọc loại Operation lấy từ mesflow.domain.policy -- KHÔNG chép lại chuỗi
# COALESCE(...) ở từng câu truy vấn. Trước 2026-09-10 mỗi module tự viết một
# bản, và mỗi lần quên một chỗ là một lần sản lượng của OP phụ lọt vào tiến độ
# PO, hoặc PO không bao giờ đạt COMPLETED.
PRODUCTION_ONLY_O = production_only_sql('o')
TYPE_VALUE_O = type_value_sql('o')

bp = Blueprint('excel_io', __name__, url_prefix='/api/operations')
template_excel_bp = Blueprint('template_excel_io', __name__, url_prefix='/api/templates')

# 'operation_id' ở đây là MÃ NGHIỆP VỤ, không phải operations.id -- tên cột đã
# đi vào file của khách từ lâu và đổi nó sẽ làm hỏng mọi workbook đang dùng.
# 'operation_row_id' là danh tính thật (operations.id), thêm vào cuối để file
# cũ (không có cột này) vẫn nhập được y như trước: _parse_operations_sheet map
# theo TÊN CỘT, nên cột thiếu chỉ đơn giản là rỗng.
HEADERS = [
    'operation_id', 'product', 'po', 'part', 'part_order', 'operation_name',
    'drawing', 'plan', 'done', 'defect', 'status', 'qr', 'operation_row_id'
]
ALIASES = {
    'operation_id': {'operation_id','operation id','op_id','op id','ma operation','mã operation','ma op','mã op','code'},
    'product': {'product','san pham','sản phẩm'},
    'po': {'po','production order','ma po','mã po'},
    'part': {'part','chi tiet','chi tiết','ten part','tên part'},
    'part_order': {'part_order','part order','thu tu part','thứ tự part'},
    'operation_name': {'operation_name','operation name','operation','ten operation','tên operation','ten cong doan','tên công đoạn'},
    'drawing': {'drawing','ban ve','bản vẽ'},
    'plan': {'plan','plan_qty','planned quantity','ke hoach','kế hoạch'},
    'done': {'done','done_qty','good','dat','đạt'},
    'defect': {'defect','defect_qty','loi','lỗi'},
    'status': {'status','trang thai','trạng thái'},
    'qr': {'qr','qr_code','qr code'},
    'operation_row_id': {'operation_row_id','operation row id','row_id','row id','id he thong','id hệ thống'},
}


def _text(value):
    return '' if value is None else str(value).strip()


def _norm(value):
    value = _text(value).lower().replace('_', ' ')
    return re.sub(r'\s+', ' ', value)


def _integer(value, label, *, default=0):
    if value in (None, ''):
        return default
    try:
        result = int(float(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} phải là số nguyên: {value}') from exc
    if result < 0:
        raise ValueError(f'{label} không được âm: {value}')
    return result


def _header_map(row):
    result = {}
    normalized = [_norm(v) for v in row]
    for canonical, aliases in ALIASES.items():
        for index, value in enumerate(normalized):
            if value in aliases:
                result[canonical] = index
                break
    return result


def _cell(row, mapping, name):
    index = mapping.get(name)
    return row[index] if index is not None and index < len(row) else None


def _parse_operations_sheet(rows):
    for header_index, row in enumerate(rows[:20]):
        mapping = _header_map(row)
        if 'operation_id' in mapping and 'operation_name' in mapping:
            items = []
            for row in rows[header_index + 1:]:
                if not any(v not in (None, '') for v in row):
                    continue
                items.append({name: _cell(row, mapping, name) for name in HEADERS})
            return items
    return []


def _parse_process_workbook(workbook):
    """Read the simple multi-sheet route format used by the SQLite version.

    Each visible sheet is treated as one Part. A header containing an Operation
    name column is detected automatically. PO/Product may be repeated in rows or
    placed in cells B1/B2. This intentionally accepts the common workshop files
    without forcing one exact visual template.
    """
    items = []
    for part_order, sheet in enumerate(workbook.worksheets):
        if sheet.sheet_state != 'visible' or _norm(sheet.title) in {'huong dan','hướng dẫn','instructions'}:
            continue
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        mapping = None
        header_index = None
        for idx, row in enumerate(rows[:25]):
            candidate = _header_map(row)
            if 'operation_name' in candidate:
                mapping, header_index = candidate, idx
                break
        if mapping is None:
            continue
        fallback_product = _text(rows[0][1] if len(rows[0]) > 1 else '')
        fallback_po = _text(rows[1][1] if len(rows) > 1 and len(rows[1]) > 1 else '')
        fallback_part = sheet.title.strip()
        for row_no, row in enumerate(rows[header_index + 1:], start=1):
            name = _text(_cell(row, mapping, 'operation_name'))
            if not name:
                continue
            po = _text(_cell(row, mapping, 'po')) or fallback_po
            product = _text(_cell(row, mapping, 'product')) or fallback_product
            part = _text(_cell(row, mapping, 'part')) or fallback_part
            op_id = _text(_cell(row, mapping, 'operation_id')) or f'{po}-{part_order + 1:02d}-{row_no:02d}'
            items.append({
                'operation_id': op_id, 'product': product, 'po': po, 'part': part,
                'part_order': part_order, 'operation_name': name,
                'drawing': _cell(row, mapping, 'drawing'), 'plan': _cell(row, mapping, 'plan'),
                'done': _cell(row, mapping, 'done'), 'defect': _cell(row, mapping, 'defect'),
                'status': _cell(row, mapping, 'status'), 'qr': _cell(row, mapping, 'qr'),
            })
    return items


def _optional_row_id(value, row_number):
    """operations.id lấy từ file, hoặc None nếu dòng không mang nó.

    Cố ý khắt khe. Một ô rỗng nghĩa là "file cũ, cứ tra theo mã" -- đó là ca
    thường gặp và phải im lặng đi qua. Nhưng một ô CÓ nội dung mà không phải
    số nguyên dương thì không được lặng lẽ rơi về mã: người dùng rõ ràng đã
    định nói điều gì đó, và đoán hộ họ là cách nhanh nhất để sửa nhầm dòng.
    """
    text = _text(value)
    if not text:
        return None
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        raise ValueError(f'Dòng {row_number}: operation_row_id không phải số: {text}')
    if number <= 0:
        raise ValueError(f'Dòng {row_number}: operation_row_id phải là số dương: {text}')
    return number


def _normalize_item(item, row_number):
    code = _text(item.get('operation_id')).upper()
    po_code = _text(item.get('po')).upper()
    part_name = _text(item.get('part'))
    name = _text(item.get('operation_name'))
    if not code:
        raise ValueError(f'Dòng {row_number}: thiếu operation_id.')
    if not po_code:
        raise ValueError(f'Dòng {row_number}: thiếu mã PO.')
    if not part_name:
        raise ValueError(f'Dòng {row_number}: thiếu Part.')
    if not name:
        raise ValueError(f'Dòng {row_number}: thiếu tên Operation.')
    status = _text(item.get('status')).upper() or 'PLANNED'
    return {
        'code': code,
        'product': _text(item.get('product')) or po_code,
        'po_code': po_code,
        'part_name': part_name,
        'part_order': _integer(item.get('part_order'), f'Dòng {row_number} part_order'),
        'name': name,
        'drawing': _text(item.get('drawing')),
        'plan_qty': _integer(item.get('plan'), f'Dòng {row_number} plan'),
        'done_qty': _integer(item.get('done'), f'Dòng {row_number} done'),
        'defect_qty': _integer(item.get('defect'), f'Dòng {row_number} defect'),
        'status': status,
        'qr': _text(item.get('qr')) or f'WF|OP|{code}',
        'row_id': _optional_row_id(item.get('operation_row_id'), row_number),
    }


@bp.get('/export.xlsx')
@roles_required('admin','manager')
def export_operations():
    with transaction() as conn:
        rows = conn.execute(f'''
            SELECT o.id, o.code, po.product, po.code AS po_code,
                   p.code AS part_code, p.name AS part_name, p.sort_order AS part_order,
                   p.drawing_path, o.name, po.planned_quantity AS plan_qty, o.done_qty, o.defect_qty,
                   o.status, o.qr
            FROM operations o
            JOIN production_orders po ON po.id=o.production_order_id
            JOIN parts p ON p.id=o.part_id
            -- Chỉ OP sản xuất. Tem SETUP và bàn SỬA HÀNG không phải bước
            -- routing: xuất chúng ra rồi import ngược lại sẽ tạo lại chúng
            -- thành operation_type=PRODUCTION với parent_operation_id NULL --
            -- check constraint cho qua vì nó là biconditional -- và từ đó
            -- chúng lọt vào operation_count, khiến PO không bao giờ COMPLETED.
            WHERE {PRODUCTION_ONLY_O}
            ORDER BY po.code, p.sort_order, o.sort_order, o.id
        ''').fetchall()
    wb = Workbook()
    ws = wb.active
    ws.title = 'Operations'
    ws.append(HEADERS)
    for row in rows:
        ws.append([
            row['code'], row['product'], row['po_code'], row['part_name'], row['part_order'],
            row['name'], row['drawing_path'], row['plan_qty'], row['done_qty'],
            row['defect_qty'], row['status'], row['qr'], row['id'],
        ])
    widths = [27,18,18,28,12,32,28,12,12,12,18,48,16]
    for idx, width in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(1, idx).column_letter].width = width
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    guide = wb.create_sheet('Huong_dan')
    guide_rows = [
        ['HƯỚNG DẪN IMPORT / EXPORT OPERATION'],
        ['1', 'Không đổi operation_id nếu muốn cập nhật Operation hiện có.'],
        ['2', 'Thêm dòng với operation_id mới để tạo Operation.'],
        ['3', 'PO phải được tạo từ Template trước. Import chỉ cập nhật Operation/Part vào PO đã tồn tại.'],
        ['4', 'plan là số lượng kế hoạch của PO; done/defect/part_order phải là số nguyên không âm.'],
        ['5', 'Chế độ Gộp cập nhật theo operation_id. Chế độ Thay toàn bộ xóa dữ liệu Operation hiện tại trước khi nhập.'],
        ['6', 'Cột qr có thể để trống; hệ thống tự sinh WF|OP|<operation_id>.'],
        ['7', 'operation_row_id là ID hệ thống của Operation. ĐỪNG SỬA và đừng xoá cột này: '
              'nó là thứ giúp nhập lại đúng dòng kể cả khi mã đã đổi. File cũ không có cột '
              'này vẫn nhập được bình thường (hệ thống tra theo operation_id trong phạm vi PO).'],
        ['8', 'Import KHÔNG đổi mã Operation. Muốn đổi mã thì sửa trên màn hình quản lý.'],
    ]
    for row in guide_rows:
        guide.append(row)
    guide.column_dimensions['A'].width = 8
    guide.column_dimensions['B'].width = 100
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    filename = f"operations_{site_now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(out, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', max_age=0)


@bp.post('/import')
@roles_required('admin','manager')
def import_operations():
    upload = request.files.get('file')
    mode = _text(request.form.get('mode') or 'merge').lower()
    if not upload or not upload.filename:
        return jsonify(ok=False, message='Chưa chọn file Excel.'), 400
    if not upload.filename.lower().endswith('.xlsx'):
        return jsonify(ok=False, message='Chỉ hỗ trợ file .xlsx.'), 400
    if mode not in {'merge', 'replace'}:
        return jsonify(ok=False, message='Chế độ import không hợp lệ.'), 400
    try:
        validated=validate_excel_upload(upload)
        workbook = load_workbook(BytesIO(validated.data), data_only=True, read_only=True)
        raw_items = []
        source_type = 'process_workbook'
        for sheet in workbook.worksheets:
            parsed = _parse_operations_sheet(list(sheet.iter_rows(values_only=True)))
            if parsed:
                raw_items = parsed
                source_type = 'operations_table'
                break
        if not raw_items:
            raw_items = _parse_process_workbook(workbook)
        if not raw_items:
            return jsonify(ok=False, message='Không tìm thấy Operation trong file.'), 400
        normalized, errors, seen = [], [], set()
        for index, item in enumerate(raw_items, start=2):
            try:
                row = _normalize_item(item, index)
                if row['done_qty'] or row['defect_qty'] or row['status'] not in {'','PLANNED'}:
                    raise ValueError(f'Dòng {index}: done, defect và status là dữ liệu production tự tính; hãy sửa Session nguồn rồi reconcile.')
                if row['code'] in seen:
                    raise ValueError(f'Dòng {index}: trùng operation_id {row["code"]}.')
                seen.add(row['code'])
                normalized.append(row)
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            return jsonify(ok=False, message='File có dữ liệu không hợp lệ.', errors=errors[:30]), 400

        inserted = updated = po_created = part_created = 0
        with transaction() as conn:
            if mode == 'replace':
                # Replace chỉ được đụng những PO CÓ TRONG FILE. Trước đây hai
                # câu DELETE này không có WHERE: chúng xoá cấu trúc Operation
                # của MỌI PO trong cơ sở dữ liệu, kể cả PO không liên quan gì
                # tới file đang import. Điều kiện chặn bên dưới cũng là toàn
                # cục, nên nó chỉ cứu được hệ thống đã chạy thật -- đúng lúc
                # nguy hiểm nhất, hệ thống mới dựng đang import nhiều PO, thì
                # nó cho qua.
                po_codes=sorted({row['po_code'] for row in normalized if row.get('po_code')})
                if not po_codes:
                    raise ValueError('File không có mã PO nào để Replace.')
                scope=conn.execute('''SELECT id FROM production_orders
                    WHERE UPPER(code)=ANY(%s)''',([c.upper() for c in po_codes],)).fetchall()
                scope_ids=[r['id'] for r in scope]
                if not scope_ids:
                    raise NotFoundError(f"Không tìm thấy PO nào trong file: {', '.join(po_codes)}")
                counts=conn.execute('''SELECT
                    (SELECT COUNT(*) FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
                     WHERE o.production_order_id=ANY(%s)) sessions,
                    (SELECT COUNT(*) FROM operation_input_consumptions c JOIN operations o ON o.id=c.target_operation_id
                     WHERE o.production_order_id=ANY(%s)) ledgers''',(scope_ids,scope_ids)).fetchone()
                if int(counts.get('sessions') or 0)>0 or int(counts.get('ledgers') or 0)>0:
                    raise ConflictError('Không thể Replace cấu trúc Operation khi PO trong file đã có Session hoặc lịch sử cấp đầu vào. Hãy dùng Merge hoặc tạo PO mới.')
                conn.execute('DELETE FROM operations WHERE production_order_id=ANY(%s)',(scope_ids,))
                conn.execute('DELETE FROM parts WHERE production_order_id=ANY(%s)',(scope_ids,))
            for row in normalized:
                po = conn.execute('SELECT id,planned_quantity FROM production_orders WHERE UPPER(code)=UPPER(%s)', (row['po_code'],)).fetchone()
                if not po:
                    raise NotFoundError(f"PO {row['po_code']} chưa tồn tại. Hãy tạo PO từ Template trước khi import Operation.")
                if row['plan_qty'] > 0:
                    current_plan = int(po.get('planned_quantity') or 0)
                    if current_plan <= 0:
                        conn.execute('UPDATE production_orders SET planned_quantity=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s',(row['plan_qty'],po['id']))
                    elif current_plan != row['plan_qty']:
                        raise ConflictError(f"PO {row['po_code']} có số lượng kế hoạch {current_plan}, nhưng file có {row['plan_qty']}")
                part = conn.execute('''
                    SELECT id FROM parts
                    WHERE production_order_id=%s AND (UPPER(code)=UPPER(%s) OR UPPER(name)=UPPER(%s))
                    ORDER BY id LIMIT 1
                ''', (po['id'], row['part_name'], row['part_name'])).fetchone()
                if not part:
                    base_code = re.sub(r'[^A-Z0-9]+', '-', row['part_name'].upper()).strip('-') or 'PART'
                    part_code = base_code
                    suffix = 2
                    while conn.execute('SELECT 1 FROM parts WHERE production_order_id=%s AND UPPER(code)=UPPER(%s)', (po['id'], part_code)).fetchone():
                        part_code = f'{base_code}-{suffix}'
                        suffix += 1
                    part = conn.execute('''
                        INSERT INTO parts(production_order_id,code,name,drawing_path,sort_order,active)
                        VALUES(%s,%s,%s,%s,%s,true) RETURNING id
                    ''', (po['id'], part_code, row['part_name'], row['drawing'], row['part_order'])).fetchone()
                    part_created += 1
                # Tìm trong ĐÚNG PO của dòng đang import, không phải toàn bảng.
                #
                # operations.code unique TOÀN CỤC, nên `WHERE UPPER(code)=?`
                # không kèm PO vẫn luôn tìm thấy đúng một dòng -- kể cả khi
                # dòng đó thuộc một PO khác hẳn. Câu UPDATE bên dưới ghi lại
                # production_order_id và part_id, nên một dòng Excel ghi sai
                # cột po (hoặc dán từ file của PO khác) LẶNG LẼ CHUYỂN
                # Operation đó sang PO trong file, mang theo done_qty và toàn
                # bộ work_sessions của nó: PO cũ mất một công đoạn đã có sản
                # lượng, PO mới nhận số nó chưa từng làm, và API trả về
                # {"ok":true,"updated":1}. Dựng lại được: 42 SP và 1 session
                # nhảy từ PO-ONE sang PO-TWO chỉ bằng một dòng file.
                #
                # Guard cũ chỉ chặn khi Operation đã có
                # operation_input_consumptions, nên ca phổ biến nhất -- đã có
                # Session, chưa có ledger dòng vật tư -- lọt hết.
                if row.get('row_id'):
                    # Danh tính thật đi trước. Nhưng KHÔNG được tin nó một cách
                    # mù quáng: nếu id trỏ vào một dòng có mã khác, thì file và
                    # cơ sở dữ liệu đang bất đồng về việc dòng này LÀ AI, và
                    # đoán hộ một trong hai bên là cách ghi đè nhầm Operation.
                    existing = conn.execute(f'''SELECT o.id,{TYPE_VALUE_O} operation_type,
                            o.code,o.production_order_id,po2.code po_code
                        FROM operations o JOIN production_orders po2 ON po2.id=o.production_order_id
                        WHERE o.id=%s''', (row['row_id'],)).fetchone()
                    if not existing:
                        raise NotFoundError(
                            f"Dòng có operation_row_id={row['row_id']} không còn tồn tại trong hệ thống. "
                            'Xuất lại file Excel mới rồi sửa trên file đó.')
                    if str(existing['code']).upper() != str(row['code']).upper():
                        raise ConflictError(
                            f"operation_row_id={row['row_id']} đang là Operation {existing['code']}, "
                            f"nhưng dòng này ghi mã {row['code']}. Import không đổi mã Operation; "
                            'hãy sửa mã trên màn hình quản lý, hoặc xuất lại file Excel mới.')
                    if int(existing['production_order_id']) != int(po['id']):
                        raise ConflictError(
                            f"Operation {existing['code']} đang thuộc PO {existing['po_code']}, "
                            f"không phải {row['po_code']}. Import không chuyển Operation giữa các PO.")
                else:
                    # LIMIT 5 chứ không fetchone(): so sánh ở đây KHÔNG phân
                    # biệt hoa/thường, mà operations_code_key chỉ unique phân
                    # biệt hoa/thường -- nên 'OP02' và 'op02' là hai dòng hợp
                    # lệ và có thể cùng nằm trong một PO. fetchone() lúc đó là
                    # ĐOÁN, và nhánh UPDATE bên dưới ghi đè dòng đoán trúng.
                    # Cùng luật với resolver QR: mơ hồ thì TỪ CHỐI.
                    candidates = conn.execute(f'''SELECT o.id,{TYPE_VALUE_O} operation_type,o.code
                        FROM operations o
                        WHERE UPPER(o.code)=UPPER(%s) AND o.production_order_id=%s
                        ORDER BY o.id LIMIT 5''', (row['code'], po['id'])).fetchall()
                    if len(candidates) > 1:
                        seen = ', '.join(str(c['code']) for c in candidates[:4])
                        raise ConflictError(
                            f"Mã Operation {row['code']} đang khớp nhiều Operation trong PO "
                            f"{row['po_code']} ({seen}) khi bỏ qua hoa/thường, không xác định được "
                            'dòng nào phải cập nhật. Hãy đổi mã cho duy nhất, hoặc sửa trực tiếp '
                            'trên màn hình PO thay vì bằng Excel.')
                    existing = candidates[0] if candidates else None
                if not existing:
                    # Không có trong PO này. Vì mã unique toàn cục, INSERT bên
                    # dưới sẽ đâm vào operations_code_key -- nói thẳng ra vấn
                    # đề thay vì để người dùng đọc một lỗi ràng buộc Postgres.
                    owner = conn.execute('''SELECT o.id,po2.code po_code,p2.code part_code
                        FROM operations o JOIN production_orders po2 ON po2.id=o.production_order_id
                        LEFT JOIN parts p2 ON p2.id=o.part_id
                        WHERE UPPER(o.code)=UPPER(%s)''', (row['code'],)).fetchone()
                    if owner:
                        raise ConflictError(
                            f"Operation {row['code']} đang thuộc PO {owner['po_code']}"
                            f" (Part {owner.get('part_code') or '?'}), không phải {row['po_code']}. "
                            'Mã Operation là duy nhất trên toàn hệ thống, nên nhập file này sẽ chuyển '
                            'Operation đó sang PO khác cùng toàn bộ sản lượng và Session của nó. '
                            'Hãy sửa cột po cho đúng, hoặc đặt mã khác cho Operation mới.')
                if existing and not is_production(existing['operation_type']):
                    # Một file xuất TRƯỚC bản vá vẫn còn dòng OP phụ trong đó.
                    raise ValueError(
                        f"Operation {row['code']} là OP phụ ({existing['operation_type']}), không sửa được bằng Excel. "
                        'Xoá dòng này khỏi file rồi import lại.')
                # Cột `qr` của file đi thẳng vào bảng, nên đường này vòng qua
                # guard mà OperationRepository.create/update đang giữ.
                # operations_qr_key chỉ cấm hai `qr` GIỐNG HỆT nhau; nó không
                # nói gì về ca chéo cột -- `qr` của dòng này trùng với `code`
                # của dòng khác -- và đó chính là ca làm tem cũ hoá mơ hồ.
                _assert_excel_qr_unambiguous(conn, row['code'], row['qr'],
                                             operation_id=existing['id'] if existing else None)
                if existing:
                    guard=conn.execute('''SELECT o.production_order_id,o.part_id,o.done_qty,
                        COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id),0) allocated,
                        EXISTS(SELECT 1 FROM operation_input_consumptions c WHERE c.target_operation_id=o.id) has_consumption
                        FROM operations o WHERE o.id=%s FOR UPDATE''',(existing['id'],)).fetchone()
                    if bool(guard.get('has_consumption')) and (int(guard['production_order_id'])!=int(po['id']) or int(guard['part_id'])!=int(part['id'])):
                        raise ValueError(f"Operation {row['code']} đã có lịch sử cấp đầu vào nên không thể chuyển PO/Part bằng Excel.")
                    conn.execute('''
                        UPDATE operations SET production_order_id=%s,part_id=%s,name=%s,
                            sort_order=%s,qr=%s,updated_at=CURRENT_TIMESTAMP
                        WHERE id=%s
                    ''', (po['id'], part['id'], row['name'],row['part_order'], row['qr'], existing['id']))
                    updated += 1
                else:
                    conn.execute('''
                        INSERT INTO operations(production_order_id,part_id,code,name,done_qty,
                            defect_qty,status,sort_order,qr)
                        VALUES(%s,%s,%s,%s,0,0,'PLANNED',%s,%s)
                    ''', (po['id'], part['id'], row['code'], row['name'],row['part_order'], row['qr']))
                    inserted += 1
            total = conn.execute('SELECT COUNT(*) AS count FROM operations').fetchone()['count']
        return jsonify(ok=True, message='Đã nhập file Excel thành công.', source_type=source_type,
                       processed=len(normalized), inserted=inserted, updated=updated, total=total,
                       production_orders_created=po_created, parts_created=part_created)
    except Exception as exc:
        return api_error_response(exc,logger_name=__name__)




def _assert_excel_qr_unambiguous(conn, code, qr, *, operation_id=None):
    """Không cho một dòng Excel làm tem cũ ngoài xưởng hoá mơ hồ.

    Cùng bất biến mà OperationRepository giữ, viết lại ở đây vì đường Excel
    ghi thẳng bằng SQL trong transaction của chính nó chứ không đi qua
    repository. Kiểm cả hai chiều: mã của dòng này có đang bị `qr` của dòng
    khác đòi không, và `qr` của dòng này có đòi mã của dòng khác không.
    """
    code = _text(code)
    qr = _text(qr)
    if code:
        clash = conn.execute(
            'SELECT id,code FROM operations WHERE upper(qr)=upper(%s) AND id<>COALESCE(%s,-1) LIMIT 1',
            (f'WF|OP|{code}', operation_id)).fetchone()
        if clash:
            raise ConflictError(
                f"Mã {code} vẫn đang được tem QR cũ của Operation {clash['code']} sử dụng. "
                'Nếu dùng lại mã này thì tem cũ sẽ trỏ tới hai Operation và không quét được nữa.')
    upper = qr.upper()
    if upper.startswith('WF|OP|') and not upper.startswith('WF|OPID|'):
        claimed = qr[len('WF|OP|'):].strip()
        if claimed and claimed.upper() != code.upper():
            clash = conn.execute(
                'SELECT id,code FROM operations WHERE upper(code)=upper(%s) AND id<>COALESCE(%s,-1) LIMIT 1',
                (claimed, operation_id)).fetchone()
            if clash:
                raise ConflictError(
                    f"Tem {qr} trùng với mã của Operation {clash['code']}, nên tem này sẽ trỏ tới "
                    'hai Operation và không quét được.')


def _find_labeled_value(rows, labels, max_rows=12, max_span=4):
    """Giá trị BÊN PHẢI ô nhãn, trong phạm vi vài cột.

    ``max_span`` không phải chi tiết vụn: đầu tờ router có nhiều khối nhãn nằm
    cạnh nhau trên cùng một dòng. Dòng 4 là
    ``A='TÊN BẢN VẼ:' ... C=<tên> ... G='SẢN XUẤT HÀNG LOẠT' ... I=110``.
    Quét hết dòng thì bốn sheet mức quy trình (TÊN/MÃ BẢN VẼ để trống) nhận
    nhầm 'SẢN XUẤT HÀNG LOẠT' làm tên bản vẽ -- và tệ hơn, hệ thống tưởng chúng
    CÓ danh tính bản vẽ nên không cảnh báo gì. Giá trị luôn nằm sát nhãn.
    """
    labels={_norm(x).rstrip(':') for x in labels}
    for row in rows[:max_rows]:
        for idx,value in enumerate(row):
            if _norm(value).rstrip(':') in labels:
                for candidate in row[idx+1:idx+1+max_span]:
                    if candidate not in (None, ''):
                        return candidate
    return None


def _find_labeled_value_below(rows, labels, max_rows=12, max_below=6):
    """Giá trị nằm DƯỚI ô nhãn, cùng cột.

    Đầu tờ router dùng HAI kiểu đặt nhãn cùng lúc, và nhầm chúng là cách chắc
    chắn nhất để đọc sai:

      * bên trái, nhãn -> giá trị BÊN PHẢI cùng dòng
        (``A2='PO NUMBER:'`` -> ``C2=6126``);
      * bên phải, nhãn là TIÊU ĐỀ CỘT -> giá trị ở dòng DƯỚI
        (``I2='SỐ LƯỢNG'`` -> ``I4=110``, ``G2='LOẠI ĐƠN HÀNG'`` -> ``G4=...``).

    Đọc 'SỐ LƯỢNG' bằng kiểu thứ nhất sẽ nhặt phải ``J2='HÌNH ẢNH'`` -- đúng lỗi
    mà file thật vừa lộ ra.
    """
    wanted = {_deaccent(x).rstrip(':') for x in labels}
    for index, row in enumerate(rows[:max_rows]):
        for col, value in enumerate(row):
            if _deaccent(value).rstrip(':') not in wanted:
                continue
            for below in rows[index + 1:index + 1 + max_below]:
                candidate = below[col] if col < len(below) else None
                if candidate not in (None, ''):
                    return candidate
    return None


def _safe_code(value, fallback):
    text=_text(value).upper()
    text=re.sub(r'[^A-Z0-9]+','-',text).strip('-')
    return text or fallback


# --- GO ROUTER: đọc số trong một block Operation -------------------------
#
# Mỗi block Operation của workbook xưởng đặt NHÃN và GIÁ TRỊ ở hai dòng liền
# nhau, cùng một cột: dòng trên là 'Thời gian Setup ( phút )', dòng dưới là
# con số (cột A của dòng dưới ghi 'SETUP'). Vị trí tuyệt đối KHÔNG ổn định --
# nó phụ thuộc block đứng thứ mấy trong sheet -- nên ở đây neo theo NHÃN rồi
# đọc xuống một dòng trong ĐÚNG cột đó, thay vì gõ cứng L10/L11.
SETUP_TIME_LABELS = ('thoi gian setup', 'thoi gian cai dat', 'setup time')
CYCLE_TIME_LABELS = ('thoi gian gia cong / san pham', 'cycle time', 'thoi gian chu ky')
TOTAL_TIME_LABELS = ('tong thoi gian gia cong du kien', 'tong thoi gian', 'total time')

#: Từ khoá NGẮN chỉ được coi là nhãn thời gian khi ô đó CÓ đơn vị trong ngoặc.
#:
#: Cột A của tờ router có ô ghi trần 'SETUP' -- đó là nhãn DÒNG, và ngay dưới nó
#: là 'Nhân viên Setup'. Nếu 'setup' trần cũng khớp thì parser sẽ đọc tên nhân
#: viên làm thời gian set máy. Đơn vị trong ngoặc là thứ phân biệt một ô tiêu đề
#: số liệu ('Setup (min)') với một nhãn dòng ('SETUP').
SHORT_TIME_KEYWORDS = {'setup': 'setup', 'cycle': 'cycle', 'total': 'total',
                       'thoi gian': 'any'}

#: Cách xưởng viết "không có" trong ô số. File thật (NEWARK ARM CHAIR) điền dấu
#: '-' vào ô Thời gian Setup của 6 Operation không phải set máy. Đây là Ý ĐỊNH
#: "không áp dụng", không phải dữ liệu hỏng -- bắt cả file 44 sheet trượt vì một
#: dấu gạch là biến tính năng thành không dùng được. KHÁC với số 0: 0 là "có
#: khai báo và bằng không". Cả hai đều không sinh OP SETUP, nhưng trạng thái thô
#: được giữ lại để màn xem trước nói đúng file đang ghi gì.
BLANK_NUMBER_PLACEHOLDERS = frozenset({'-', '--', '–', '—', 'x', 'n/a', 'na',
                                       'không', 'khong', 'ko', '.', '/'})

#: Đơn vị thời gian đọc TỪ NHÃN, không đóng cứng.
#:
#: File hiện tại ghi '( phút )', '(s)', '( giờ )', nhưng một biểu mẫu khác hoàn
#: toàn có thể ghi 'Thời gian gia công / sản phẩm ( phút )'. Đóng cứng giây vì
#: file hôm nay dùng giây là cách chắc chắn nhất để một ngày nào đó nhập sai
#: gấp 60 lần mà không ai thấy. Nhãn không nói rõ đơn vị thì KHÔNG đoán.
TIME_UNIT_SECONDS = {'second': 1, 'minute': 60, 'hour': 3600}
TIME_UNIT_PATTERNS = (
    ('hour', (r'\bgio\b', r'\bgiowf\b', r'\bh\b', r'\bhr\b', r'\bhrs\b', r'\bhour', r'\btieng\b')),
    ('minute', (r'\bphut\b', r'\bmin\b', r'\bmins\b', r'\bminute')),
    ('second', (r'\bgiay\b', r'\bs\b', r'\bsec\b', r'\bsecs\b', r'\bsecond')),
)


def _time_unit_from_label(label):
    """'Thời gian gia công / sản phẩm (s)' -> 'second'. Không rõ -> None.

    Chỉ soi phần trong ngoặc nếu có -- tên trường hay chứa chữ cái trùng với ký
    hiệu đơn vị ('sản phẩm' có 's'), nên quét cả câu sẽ đoán bừa.
    """
    text = _deaccent(label)
    inside = re.findall(r'\(([^)]*)\)', text)
    haystacks = [f' {x.strip()} ' for x in inside] or [f' {text} ']
    for unit, patterns in TIME_UNIT_PATTERNS:
        for haystack in haystacks:
            for pattern in patterns:
                if re.search(pattern, haystack):
                    return unit
    return None


def _deaccent(value):
    """So nhãn không phụ thuộc dấu: file xưởng gõ tay, dấu không đều nhau."""
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', _norm(value))
                   if unicodedata.category(c) != 'Mn')


def _block_labeled_time(block_rows, labels, *, where, label_vi):
    """Một trường thời gian trong block: giá trị, đơn vị theo nhãn, trạng thái thô.

    Trả dict:
      ``declared``  block có nhãn này không;
      ``raw``       đúng thứ trong ô ('-' vẫn là '-', 0 vẫn là 0);
      ``seconds``   giá trị đã quy về giây theo ĐƠN VỊ TRONG NHÃN;
      ``unit``      'second' | 'minute' | 'hour';
      ``label``     nguyên văn nhãn, để hiện lại ở màn xem trước.

    Số âm, chữ vô nghĩa và nhãn không nói rõ đơn vị đều bị CHẶN kèm vị trí --
    không lặng lẽ quy về 0.
    """
    empty = {'declared': False, 'raw': None, 'seconds': None, 'unit': None, 'label': ''}
    wanted = {_deaccent(x) for x in labels}
    short = {'setup': SETUP_TIME_LABELS, 'cycle': CYCLE_TIME_LABELS,
             'total': TOTAL_TIME_LABELS}
    short_key = next((k for k, v in short.items() if v is labels), None)
    for idx, row in enumerate(block_rows):
        for col, cell in enumerate(row):
            text = _deaccent(cell)
            if not text:
                continue
            matched = any(w in text for w in wanted)
            if not matched and short_key and text.startswith(short_key):
                # Từ khoá ngắn chỉ tính khi ô CÓ đơn vị -- xem SHORT_TIME_KEYWORDS.
                matched = _time_unit_from_label(_text(cell)) is not None
            if not matched:
                continue
            label = _text(cell)
            unit = _time_unit_from_label(label)
            if unit is None:
                raise ValueError(
                    f'{where}: nhãn "{label}" không nói rõ đơn vị thời gian '
                    '(giây/phút/giờ), nên không biết quy đổi. Ghi rõ đơn vị trong '
                    'ngoặc, ví dụ "( phút )" hoặc "(s)".')
            found = {'declared': True, 'raw': None, 'seconds': 0.0,
                     'unit': unit, 'label': label}
            for below in block_rows[idx + 1:idx + 3]:
                value = below[col] if col < len(below) else None
                if value in (None, ''):
                    continue
                found['raw'] = value
                if _norm(value) in BLANK_NUMBER_PLACEHOLDERS:
                    # '-' = không áp dụng. Giữ raw để phân biệt với 0.
                    found['seconds'] = 0.0
                    return found
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    raise ValueError(
                        f'{where}: {label_vi} phải là số, đang là {value!r}.')
                if number < 0:
                    raise ValueError(
                        f'{where}: {label_vi} không được âm (đang là {value!r}).')
                found['seconds'] = number * TIME_UNIT_SECONDS[unit]
                return found
            return found
    return dict(empty)


def _parse_go_router_template(workbook, filename):
    """Parse the workshop GO ROUTER workbook used by the SQLite version.

    Each visible worksheet becomes one Template Part. Operation blocks are
    detected from rows like ``OPERATION # 01 - CẮT LASER``. This format does
    not contain the normalized Template/Parts/Operations sheets.
    """
    parts=[]; operations=[]
    visible=[s for s in workbook.worksheets if s.sheet_state=='visible']
    if not visible:
        return None
    first_rows=list(visible[0].iter_rows(values_only=True))
    po_value=_find_labeled_value(first_rows, {'PO NUMBER','PO NUMBER:'})
    qty_value=_find_labeled_value(first_rows, {'QTY','QTY:'})
    order_type=_find_labeled_value_below(first_rows, {'LOẠI ĐƠN HÀNG','LOAI DON HANG','ORDER TYPE'})
    po_note=_find_labeled_value(first_rows, {'CHÚ Ý','CHU Y','NOTE','GHI CHÚ'})
    stem=re.sub(r'\.xlsx$','',filename,flags=re.I).strip()
    base_code=_safe_code(po_value, f'ROUTER-{site_now().strftime("%Y%m%d%H%M%S")}')
    template_code=f'TPL-{base_code}'
    template_name=stem or f'Lộ trình sản xuất {base_code}'
    product=stem
    seen_part_codes=set()
    warnings=[]
    # Mọi thứ hệ thống ĐỌC ĐƯỢC nhưng chưa map vào model, cộng với mọi cảnh báo,
    # đi chung một kênh có phân loại. Không có đường nào để một field trong file
    # biến mất im lặng: nó hoặc vào 'operations'/'parts', hoặc nằm ở đây.
    notes=[]
    op_pattern=re.compile(r'^\s*OPERATION\s*#?\s*(\d+)\s*[-–:]?\s*(.*)$',re.I)
    for part_order,sheet in enumerate(visible):
        if _norm(sheet.title) in {'huong dan','hướng dẫn','instructions'}:
            continue
        rows=list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        drawing_code=_find_labeled_value(rows, {'MÃ BẢN VẼ','MA BAN VE','DRAWING CODE'})
        drawing_name=_find_labeled_value(rows, {'TÊN BẢN VẼ','TEN BAN VE','DRAWING NAME'})
        raw_part_code=_safe_code(drawing_code, f'PART-{part_order+1:02d}')
        part_code=raw_part_code
        suffix=2
        while part_code in seen_part_codes:
            part_code=f'{raw_part_code}-{suffix}'; suffix+=1
        seen_part_codes.add(part_code)
        part_name=sheet.title.strip() or _text(drawing_name) or part_code
        # SỐ LƯỢNG của sheet là số lượng Part phải làm, ĐỘC LẬP với QTY của PO.
        # File thật: PO QTY 110, nhưng 11 sheet ghi 220 và 1 sheet ghi 440 -- bội
        # số BOM. Gộp về QTY của PO là xoá mất định mức.
        sheet_qty=_find_labeled_value_below(rows, {'SỐ LƯỢNG','SO LUONG','QUANTITY'})
        sheet_meta=_text(rows[0][9] if len(rows[0])>9 else '')
        has_drawing_identity=bool(_text(drawing_code) or _text(drawing_name))
        if not has_drawing_identity:
            notes.append({
                'kind':'SHEET_WITHOUT_DRAWING_IDENTITY','sheet':sheet.title,'row':0,
                'raw':'','message':(
                    f"Sheet '{sheet.title}' không có TÊN/MÃ BẢN VẼ nên đây là tờ mức quy "
                    f"trình; Part được đặt mã tạm {part_code}.")})
        parts.append({'key':part_code,'code':part_code,'name':part_name,
                      'sort_order':part_order,
                      'planned_quantity':_integer(sheet_qty,f"SỐ LƯỢNG của sheet '{sheet.title}'",
                                                  default=0),
                      'source_quantity_raw':sheet_qty,
                      'source_drawing_code':_text(drawing_code),
                      'source_drawing_name':_text(drawing_name),
                      'source_sheet':sheet.title,
                      'source_document_meta':sheet_meta,
                      'has_drawing_identity':has_drawing_identity,
                      'image_count':len(getattr(sheet,'_images',()) or ())})
        # Mã NỘI BỘ chỉ cần duy nhất TRONG một Part -- OP01 của Part khác là
        # hợp lệ và rất phổ biến, nên tập này reset ở mỗi sheet.
        seen_op_codes=set()
        # Vị trí mọi block trong sheet, lấy TRƯỚC: một block chạy từ dòng tiêu
        # đề của nó tới ngay trước dòng tiêu đề kế tiếp. Biết biên rồi mới đọc
        # được số của ĐÚNG block đó -- nhãn 'Thời gian Setup' lặp ở mọi block,
        # nên tìm toàn sheet sẽ luôn trả về block đầu tiên.
        starts=[]
        for excel_row,row in enumerate(rows,start=1):
            first_nonempty=next((_text(v) for v in row if _text(v)), '')
            match=op_pattern.match(first_nonempty)
            if match:
                starts.append((excel_row,match))
        op_order=0
        for position,(excel_row,match) in enumerate(starts):
            seq=int(match.group(1)); op_name=_text(match.group(2)).strip(' -\u2013:')
            source_title=next((_text(v) for v in rows[excel_row-1] if _text(v)), '')
            if not op_name:
                op_name=f'Operation {seq:02d}'
            # SỐ OP GỐC LÀ DỮ LIỆU CỦA KHÁCH, KHÔNG ĐƯỢC SỬA.
            #
            # Xưởng đánh trùng số một cách có chủ đích: sheet 'Thanh la khung
            # ngồi phía trước' có HAI block cùng 'OPERATION # 02' -- CHAMFER LỖ
            # và LÀM NGUỘI -- và đó là hai công đoạn thật, khác nhau. Mười chỗ
            # như vậy trong file NEWARK.
            #
            # Nên: giữ NGUYÊN source_op_no và source_title đúng như trên giấy,
            # còn mã NỘI BỘ thì sinh duy nhất để hai dòng không đụng nhau trong
            # CSDL. Danh tính canonical vẫn là operation.id. Đây là khác biệt
            # then chốt so với bản trước: bản trước ghi đè số của khách thành
            # 'OP02-2' và làm mất thông tin gốc.
            base_op_code=f'{part_code}-OP{seq:02d}'
            op_code=base_op_code
            collision=2
            while op_code in seen_op_codes:
                op_code=f'{base_op_code}-{collision}'; collision+=1
            if op_code!=base_op_code:
                notes.append({
                    'kind':'DUPLICATE_SOURCE_OP_NO','sheet':sheet.title,'row':excel_row,
                    'raw':source_title,
                    'message':(f"Sheet '{sheet.title}' dòng {excel_row}: Part này đã có "
                               f"Operation số {seq:02d}. Giữ nguyên số gốc trên giấy; "
                               f"mã nội bộ dùng {op_code} để hai công đoạn không đụng "
                               'danh tính.')})
            seen_op_codes.add(op_code)
            end=starts[position+1][0]-1 if position+1<len(starts) else len(rows)
            block=rows[excel_row-1:end]
            where=(f"Sheet '{sheet.title}' dòng {excel_row} "
                   f"(Operation {source_title or op_name})")
            setup=_block_labeled_time(block,SETUP_TIME_LABELS,where=where,
                                      label_vi='Thời gian Setup')
            cycle=_block_labeled_time(block,CYCLE_TIME_LABELS,where=where,
                                      label_vi='Thời gian gia công / sản phẩm')
            total=_block_labeled_time(block,TOTAL_TIME_LABELS,where=where,
                                      label_vi='Tổng thời gian gia công dự kiến')
            # Part Number riêng của block. 27/112 block trong file thật để
            # trống, chủ yếu công đoạn xử lý -- trống thì KẾ THỪA Part của
            # sheet, không phải lỗi.
            block_part_number=''
            for brow in block:
                for bcol,bcell in enumerate(brow):
                    if 'part number' in _deaccent(bcell):
                        block_part_number=_text(brow[bcol+1] if bcol+1<len(brow) else '')
                        break
                if block_part_number:
                    break
            # >0 mới là "thật sự có setup". 0, '-' và thiếu nhãn đều KHÔNG sinh
            # OP SETUP; số âm và chữ vô nghĩa đã bị chặn kèm sheet+dòng.
            setup_seconds=setup['seconds'] or 0.0
            requires_setup=bool(setup['declared'] and setup_seconds>0)
            # expected_setup_minutes là cột PHÚT của schema (migration 0047),
            # nên quy về phút ở đây thay vì đổi đơn vị cột.
            setup_minutes=int(round(setup_seconds/60.0)) if requires_setup else None
            operations.append({
                'part_key':part_code,'code':op_code,'name':op_name,
                'equipment_code':'','sort_order':op_order,
                'standard_seconds_per_unit':cycle['seconds'] or 0.0,
                'requires_setup':requires_setup,
                'expected_setup_minutes':setup_minutes,
                '_setup_declared':setup['declared'],
                # --- nguyên văn từ file, không suy diễn ---
                'source_op_no':seq,
                'source_title':source_title,
                'source_part_number':block_part_number,
                'setup_raw':setup['raw'],'setup_unit':setup['unit'],
                'setup_label':setup['label'],'setup_seconds':setup_seconds,
                'cycle_raw':cycle['raw'],'cycle_unit':cycle['unit'],
                'cycle_label':cycle['label'],
                'total_expected_seconds':total['seconds'],
                'total_expected_raw':total['raw'],
                'total_expected_unit':total['unit'],
                'total_expected_label':total['label'],
                # Where this block actually sits, so a rejection can point at
                # it: this layout puts each Part on its own sheet, so the sheet
                # name matters as much as the row number.
                '_excel_sheet':sheet.title,'_excel_row':excel_row
            })
            op_order+=1
        if not starts:
            notes.append({
                'kind':'SHEET_WITHOUT_OPERATION_BLOCK','sheet':sheet.title,'row':0,'raw':'',
                'message':(f"Sheet '{sheet.title}' không có block OPERATION nào. Không tạo "
                           'công đoạn nào cho tờ này -- hệ thống không tự suy ra công đoạn.')})
    if not parts or not operations:
        return None
    return {
        'code':template_code,'name':template_name,'product':product,
        'version':'1.0','active':True,'parts':parts,'operations':operations,
        'po':_text(po_value),'qty':_integer(qty_value,'QTY',default=0),
        'order_type':_text(order_type),'po_note':_text(po_note),
        'source_document_meta':_text(first_rows[0][9] if len(first_rows[0])>9 else ''),
        'warnings':warnings,'notes':notes,
    }

@template_excel_bp.get('/<int:template_id>/export-workbook')
@roles_required('admin','manager')
def export_template_workbook(template_id):
    with transaction() as conn:
        template = conn.execute('SELECT * FROM templates WHERE id=%s',(template_id,)).fetchone()
        if not template:
            return jsonify(ok=False,message='Không tìm thấy Template.'),404
        parts = conn.execute('SELECT * FROM template_parts WHERE template_id=%s ORDER BY sort_order,id',(template_id,)).fetchall()
        operations = conn.execute('SELECT * FROM template_operations WHERE template_id=%s ORDER BY part_id,sort_order,id',(template_id,)).fetchall()
    wb=Workbook(); meta=wb.active; meta.title='Template'
    meta.append(['template_code','template_name','product','version','active'])
    meta.append([template['code'],template['name'],template['product'],template['version'],1 if template['active'] else 0])
    ps=wb.create_sheet('Parts'); ps.append(['part_code','part_name','sort_order'])
    for part in parts: ps.append([part['code'],part['name'],part['sort_order']])
    os=wb.create_sheet('Operations'); os.append(['part_code','operation_code','operation_name','equipment_code','cycle_time_value','cycle_time_unit','sort_order'])
    part_codes={p['id']:p['code'] for p in parts}
    for op in operations:
        sec=float(op.get('standard_seconds_per_unit') or 0)
        use_minutes=sec>=60 and abs(sec/60-round(sec/60))<0.0001
        os.append([part_codes.get(op['part_id'],''),op['code'],op['name'],op['equipment_code'],round(sec/60,3) if use_minutes else round(sec,3),'minute' if use_minutes else 'second',op['sort_order']])
    for ws in (meta,ps,os):
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width=max(14,min(40,max(len(_text(c.value)) for c in col)+3))
    out=BytesIO(); wb.save(out); out.seek(0)
    return send_file(out,as_attachment=True,download_name=f"template_{template['code']}.xlsx",mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',max_age=0)


def _duplicate_rows_message(parts, operations, duplicate_codes):
    """Point at the rows in the sheet, not just at the code.

    The person reading this has the workbook open and needs to know which
    lines to edit; "OP02 bị trùng" makes them hunt for it. Falls back to the
    plain code list for a workbook shape that carries no row numbers.
    """
    from mesflow.db.repositories.master_data import operation_code_suffix
    part_code_by_key={p['key']:p['code'] for p in parts}
    lines=[]
    for wanted in duplicate_codes:
        rows={}
        part_label=''
        for op in operations:
            part_code=part_code_by_key.get(op.get('part_key'))
            if operation_code_suffix(part_code,op.get('code'))!=wanted:
                continue
            part_label=part_label or str(part_code or '')
            if op.get('_excel_row'):
                rows.setdefault(str(op.get('_excel_sheet') or 'Operations'),[]).append(str(op['_excel_row']))
        code=str((next((o.get('code') for o in operations
                        if operation_code_suffix(part_code_by_key.get(o.get('part_key')),o.get('code'))==wanted),
                       wanted)) or wanted)
        if rows:
            where='; '.join(f"sheet '{sheet}' dòng {', '.join(nums)}" for sheet,nums in rows.items())
            lines.append(f'Part {part_label} · Operation {code} — {where}')
        else:
            lines.append(f'Part {part_label} · Operation {code}')
    return ('File Excel có Operation trùng mã trong cùng một Part:\n- '
            +'\n- '.join(lines)
            +'\nMã Operation được phép trùng giữa các Part KHÁC NHAU, nhưng trong CÙNG một Part '
             'thì phải khác nhau. Sửa lại file Excel rồi nhập lại.')


def _duplicate_operation_codes(operations):
    """Codes appearing more than once, so the archive says WHY a sheet is bad."""
    counts={}
    for op in operations or []:
        code=str(op.get('code') or '').strip().upper()
        if code: counts[code]=counts.get(code,0)+1
    return ', '.join(sorted(c for c,n in counts.items() if n>1))


# --- Preview trước khi nhập ------------------------------------------------
#
# Nhập Excel trước đây là một cú POST duy nhất: chọn file xong là dữ liệu vào
# thẳng. Không ai nhìn thấy file sinh ra cái gì trước khi nó sinh ra. Với OP
# SETUP tự tạo thì điều đó càng không chấp nhận được -- một file 44 sheet có
# thể đẻ ra hàng chục Operation phụ mà người bấm nút không hề biết.
#
# Preview KHÔNG ghi gì vào CSDL. Nó trả về đúng cấu trúc mà lần nhập sẽ tạo,
# kèm lựa chọn mặc định, để màn hình dựng checkbox và người dùng bỏ bớt trước
# khi xác nhận.

def _preview_payload(parsed):
    """Cấu trúc phẳng hai cấp Part -> Operation cho màn preview."""
    ops_by_part = {}
    for op in parsed['operations']:
        ops_by_part.setdefault(op['part_key'], []).append(op)
    parts = []
    setup_count = 0
    for part in parsed['parts']:
        rows = []
        for op in ops_by_part.get(part['key'], []):
            minutes = op.get('expected_setup_minutes')
            has_setup = bool(op.get('requires_setup')) and minutes is not None and minutes > 0
            if has_setup:
                setup_count += 1
            rows.append({
                'code': op['code'], 'name': op['name'],
                'sort_order': op['sort_order'],
                'standard_seconds_per_unit': op.get('standard_seconds_per_unit') or 0,
                'setup_declared': bool(op.get('_setup_declared')),
                'requires_setup': has_setup,
                'expected_setup_minutes': minutes if has_setup else None,
                # Mã OP SETUP dựng bằng ĐÚNG hậu tố của setup_ops, để cái người
                # dùng thấy ở preview trùng khít cái sẽ được tạo lúc lên PO.
                'setup_code': f"{op['code']}{SETUP_CODE_SUFFIX}" if has_setup else None,
                'setup_name': f"Setup {op['name']}" if has_setup else None,
                'sheet': op.get('_excel_sheet') or '', 'row': op.get('_excel_row') or 0,
            })
        parts.append({'code': part['code'], 'name': part['name'],
                      'sort_order': part['sort_order'], 'operations': rows})
    return {
        'template': {'code': parsed['code'], 'name': parsed['name'],
                     'product': parsed.get('product') or '', 'version': parsed.get('version') or '1.0'},
        'po': parsed.get('po') or '', 'qty': parsed.get('qty') or 0,
        'parts': parts, 'warnings': parsed.get('warnings') or [],
        'counts': {'parts': len(parts),
                   'operations': sum(len(p['operations']) for p in parts),
                   'setups': setup_count},
    }


def _selection_key(part_code, op_code):
    return (str(part_code or '').strip().upper(), str(op_code or '').strip().upper())


def _apply_selection(parsed, selection):
    """Bỏ khỏi kết quả parse những gì người dùng đã bỏ chọn ở preview.

    ``selection`` là danh sách {part_code, operation_code, include_setup}.
    Không gửi selection = nhập tất cả, y như hành vi cũ.

    Quy tắc chống OP SETUP mồ côi nằm Ở ĐÂY chứ không chỉ ở giao diện: bỏ chọn
    OP sản xuất thì OP SETUP của nó biến mất cùng, dù payload có nói gì đi nữa.
    Giao diện tự bỏ tick hộ người dùng, nhưng một client khác gọi thẳng API
    cũng không tạo được setup không cha.
    """
    if selection is None:
        return parsed, []
    if not isinstance(selection, list):
        raise ValueError('selection phải là danh sách Operation được chọn.')
    part_code_by_key = {p['key']: p['code'] for p in parsed['parts']}
    chosen = {}
    for entry in selection:
        if not isinstance(entry, dict):
            raise ValueError('Mỗi phần tử selection phải là một object.')
        chosen[_selection_key(entry.get('part_code'), entry.get('operation_code'))] = bool(
            entry.get('include_setup', True))
    kept_ops = []
    dropped_setups = []
    for op in parsed['operations']:
        key = _selection_key(part_code_by_key.get(op['part_key']), op['code'])
        if key not in chosen:
            continue
        op = dict(op)
        if not chosen[key] and op.get('requires_setup'):
            # Giữ nguyên OP sản xuất, chỉ bỏ phần setup. '_setup_declared' vẫn
            # True nên lần nhập này GHI ĐÈ requires_setup=False -- người dùng đã
            # nói rõ là không muốn, không phải "file không nói gì".
            op['requires_setup'] = False
            op['expected_setup_minutes'] = None
            dropped_setups.append(f"{key[0]} · {key[1]}")
        kept_ops.append(op)
    kept_keys = {op['part_key'] for op in kept_ops}
    parsed = dict(parsed)
    parsed['operations'] = kept_ops
    # Part không còn Operation nào thì không nhập Part rỗng.
    parsed['parts'] = [p for p in parsed['parts'] if p['key'] in kept_keys]
    return parsed, dropped_setups


def _parse_uploaded_router(upload):
    """Đọc file đã upload thành cấu trúc Template, dùng chung cho preview và import."""
    validated = validate_excel_upload(upload)
    wb = load_workbook(BytesIO(validated.data), data_only=True)
    parsed = _parse_go_router_template(wb, upload.filename)
    return validated.data, parsed


@template_excel_bp.post('/preview-workbook')
@roles_required('admin', 'manager')
def preview_template_workbook():
    """Xem trước file Excel sẽ tạo ra gì. KHÔNG ghi gì vào CSDL."""
    upload = request.files.get('file')
    if not upload or not upload.filename:
        return jsonify(ok=False, message='Chưa chọn file Excel.'), 400
    if not upload.filename.lower().endswith('.xlsx'):
        return jsonify(ok=False, message='Chỉ hỗ trợ file .xlsx.'), 400
    try:
        _, parsed = _parse_uploaded_router(upload)
        if not parsed:
            return jsonify(ok=False, message=(
                'File này không phải Lộ trình sản xuất (GO ROUTER). Xem trước chỉ hỗ trợ '
                'workbook có các block "OPERATION # ..." theo từng sheet Part.')), 400
        return jsonify(ok=True, filename=upload.filename, **_preview_payload(parsed))
    except Exception as exc:
        return api_error_response(exc, logger_name=__name__)


@template_excel_bp.post('/import-workbook')
@roles_required('admin','manager')
def import_template_workbook():
    upload=request.files.get('file')
    if not upload or not upload.filename:
        return jsonify(ok=False,message='Chưa chọn file Excel Template.'),400
    if not upload.filename.lower().endswith('.xlsx'):
        return jsonify(ok=False,message='Chỉ hỗ trợ file .xlsx.'),400
    # Kept in scope for the archive below: whatever happens to the import, the
    # workbook that caused it has to be recoverable (see
    # db/repositories/template_imports.py).
    archive=TemplateImportRepository()
    # Checkbox của màn preview đi kèm file trong cùng một multipart. Chuỗi rỗng
    # hoặc thiếu hẳn = nhập tất cả, nên client cũ không đổi hành vi.
    selection=None
    raw_selection=(request.form.get('selection') or '').strip()
    if raw_selection:
        try:
            selection=json.loads(raw_selection)
        except ValueError:
            return jsonify(ok=False,message='Danh sách Operation được chọn không hợp lệ.'),400
    dropped_setups=[]
    import_warnings=[]
    raw_bytes=b''
    actor_id=session.get('user_id'); actor_name=str(session.get('username') or '')
    imported_code=''
    try:
        validated=validate_excel_upload(upload)
        raw_bytes=validated.data
        wb=load_workbook(BytesIO(validated.data),data_only=True)
        standard={'Template','Parts','Operations'}.issubset(set(wb.sheetnames))
        source_format='template_workbook'
        if standard:
            meta=list(wb['Template'].iter_rows(values_only=True))
            if len(meta)<2:
                return jsonify(ok=False,message='Sheet Template chưa có dữ liệu.'),400
            raw=meta[1]; headers={_norm(v):i for i,v in enumerate(meta[0])}
            def mv(name,default=''):
                i=headers.get(name); return raw[i] if i is not None and i<len(raw) else default
            code=_text(mv('template code') or mv('template_code')).upper() or f'TPL-{site_now().strftime("%Y%m%d%H%M%S")}'
            imported_code=code
            name=_text(mv('template name') or mv('template_name')) or code
            product=_text(mv('product')); version=_text(mv('version')) or '1.0'
            active=str(mv('active',1)).lower() not in {'0','false','no'}
            part_rows=list(wb['Parts'].iter_rows(values_only=True))
            if not part_rows: raise ValueError('Sheet Parts chưa có dữ liệu.')
            ph={_norm(v):i for i,v in enumerate(part_rows[0])}
            parts=[]
            for idx,row in enumerate(part_rows[1:]):
                pc=_text(row[ph.get('part code',ph.get('part_code',0))] if row else '').upper()
                pn=_text(row[ph.get('part name',ph.get('part_name',1))] if len(row)>1 else '')
                if not pc and not pn: continue
                if not pc or not pn: raise ValueError(f'Sheet Parts dòng {idx+2}: thiếu mã hoặc tên Part.')
                so=row[ph.get('sort order',ph.get('sort_order',2))] if len(row)>2 else idx
                parts.append({'key':pc,'code':pc,'name':pn,'sort_order':_integer(so,f'Parts dòng {idx+2} sort_order',default=idx)})
            part_keys={p['code'] for p in parts}
            op_rows=list(wb['Operations'].iter_rows(values_only=True))
            if not op_rows: raise ValueError('Sheet Operations chưa có dữ liệu.')
            oh={_norm(v):i for i,v in enumerate(op_rows[0])}
            operations=[]
            for idx,row in enumerate(op_rows[1:]):
                def ov(*names,default=''):
                    for n in names:
                        i=oh.get(n)
                        if i is not None and i<len(row): return row[i]
                    return default
                pc=_text(ov('part code','part_code')).upper(); on=_text(ov('operation name','operation_name'))
                if not pc and not on: continue
                if pc not in part_keys: raise ValueError(f'Operations dòng {idx+2}: Part {pc} không tồn tại.')
                if not on: raise ValueError(f'Operations dòng {idx+2}: thiếu tên Operation.')
                cycle_value=float(ov('cycle time value','cycle_time_value',default=0) or 0); cycle_unit=_text(ov('cycle time unit','cycle_time_unit',default='second')).lower(); operations.append({'part_key':pc,'code':_text(ov('operation code','operation_code')).upper(),'name':on,'equipment_code':_text(ov('equipment code','equipment_code')).upper(),'standard_seconds_per_unit':cycle_value*(60 if cycle_unit.startswith(('min','phút','phut')) else 1),'sort_order':_integer(ov('sort order','sort_order',default=idx),f'Operations dòng {idx+2} sort_order',default=idx),'_excel_sheet':'Operations','_excel_row':idx+2})
        else:
            parsed=_parse_go_router_template(wb,upload.filename)
            if not parsed:
                return jsonify(ok=False,message='Không nhận diện được dữ liệu Template. File cần có 3 sheet chuẩn hoặc các dòng OPERATION # trong từng sheet.'),400
            source_format='go_router'
            # Lựa chọn từ màn preview. Không gửi = nhập tất cả, đúng như trước.
            parsed,dropped_setups=_apply_selection(parsed,selection)
            if not parsed['operations']:
                return jsonify(ok=False,message='Chưa chọn Operation nào để nhập.'),400
            code=parsed['code']; name=parsed['name']; product=parsed['product']; version=parsed['version']; active=parsed['active']
            imported_code=code
            parts=parsed['parts']; operations=parsed['operations']
            import_warnings=list(parsed.get('warnings') or [])
        with transaction() as conn:
            # Gate 19 (2026-08-26): real confirmed bug -- this used to silently
            # fork a NEW template with an auto-suffixed code ('-2','-3',...) on
            # every code collision, including re-uploading the exact same
            # file. A client retry after a timeout/network blip (the standard
            # "did my write actually land?" scenario, same as every other
            # import/write path in this codebase) then created a permanent
            # duplicate template instead of a safe no-op, violating the same
            # retry-safety guarantee import_operations() already gives (that
            # one updates in place by matching code, see above). Fixed by
            # matching the SAME update-in-place-by-code idiom already used
            # both there and by seed_demo_templates() just below: a code
            # collision now replaces the existing template's Parts/Operations
            # content instead of forking a second template under it.
            # Same rules the Template editor enforces, applied before a single
            # row is written: Part codes unique in the workbook, and no two
            # Operations that would generate the same real Operation code.
            # Excel used to write straight through, which is how TPL-6126's
            # ten duplicates got in (2026-09-09).
            try:
                _validate_template_part_codes(parts)
                part_code_by_key={p['key']:p['code'] for p in parts}
                _validate_template_operation_codes(
                    [(part_code_by_key.get(o['part_key']),o.get('code')) for o in operations])
            except TemplateValidationError as verr:
                if verr.code=='DUPLICATE_PART_CODE_IN_TEMPLATE':
                    raise ValueError('File Excel có mã Part bị trùng: '
                        +', '.join(verr.details.get('duplicate_codes') or [])
                        +'. Mỗi Part phải có mã riêng.') from verr
                raise ValueError(_duplicate_rows_message(
                    parts,operations,verr.details.get('duplicate_codes') or [])) from verr
            existing=conn.execute('SELECT id FROM templates WHERE UPPER(code)=UPPER(%s)',(code,)).fetchone()
            replaced=bool(existing)
            # Những cột KHÔNG có trong workbook nhưng người dùng đã cấu hình
            # trên web. Import lại một Template đang tồn tại là xoá rồi chèn
            # mới, nên trước bản vá này chúng biến mất im lặng -- kèm thông báo
            # "Đã cập nhật Template" như thể mọi thứ bình thường. Một kỹ sư
            # nhập file, cấu hình hướng dẫn setup và dòng vật tư cho 40 OP trên
            # web, rồi đồng nghiệp upload lại file đã sửa một chữ: mất sạch.
            PRESERVED=('requires_setup','expected_setup_minutes','setup_note',
                       'repair_cycle_time_seconds_per_unit','input_flow_enabled',
                       'input_source_code','input_source_kind','defects_consume_input')
            # Dùng cho OP mới trong file, chưa từng được cấu hình trên web.
            # Trùng đúng DEFAULT của bảng: chèn tường minh nên không còn
            # DEFAULT nào đỡ, và bốn cột trong số này là NOT NULL.
            PRESERVED_DEFAULTS={'requires_setup':False,'expected_setup_minutes':None,
                'setup_note':'','repair_cycle_time_seconds_per_unit':0,
                'input_flow_enabled':False,'input_source_code':None,
                'input_source_kind':'GOOD','defects_consume_input':True}
            keep={}
            keep_drawings={}
            if existing:
                t={'id':existing['id']}
                for row in conn.execute(f'''SELECT p.code part_code,o.code,{','.join('o.'+c for c in PRESERVED)}
                    FROM template_operations o JOIN template_parts p ON p.id=o.part_id
                    WHERE o.template_id=%s''',(t['id'],)).fetchall():
                    keep[(str(row['part_code'] or '').upper(),str(row['code'] or '').upper())]={
                        c:row[c] for c in PRESERVED}
                for row in conn.execute('SELECT code,drawing_path FROM template_parts WHERE template_id=%s',
                                        (t['id'],)).fetchall():
                    if row.get('drawing_path'):
                        keep_drawings[str(row['code'] or '').upper()]=row['drawing_path']
                conn.execute('UPDATE templates SET name=%s,product=%s,version=%s,active=%s,source_workbook=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                    (name,product,version,active,upload.filename,t['id']))
                conn.execute('DELETE FROM template_operations WHERE template_id=%s',(t['id'],))
                conn.execute('DELETE FROM template_parts WHERE template_id=%s',(t['id'],))
            else:
                t=conn.execute('INSERT INTO templates(code,name,product,version,active,source_workbook) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id',(code,name,product,version,active,upload.filename)).fetchone()
            ids={}
            for pitem in parts:
                r=conn.execute('INSERT INTO template_parts(template_id,code,name,sort_order,drawing_path) VALUES(%s,%s,%s,%s,%s) RETURNING id',
                    (t['id'],pitem['code'],pitem['name'],pitem['sort_order'],
                     keep_drawings.get(str(pitem['code'] or '').upper(),''))).fetchone()
                ids[pitem['key']]=r['id']
            for opitem in operations:
                # Khớp lại theo (mã Part, mã OP) -- cùng cặp mà editor Template
                # dùng làm danh tính. Đổi mã OP trong file = OP khác, mất cấu
                # hình cũ là đúng; giữ nguyên mã thì phải giữ nguyên cấu hình.
                cfg=dict(PRESERVED_DEFAULTS)
                cfg.update(keep.get((
                    str(part_code_by_key.get(opitem['part_key']) or '').upper(),
                    str(opitem['code'] or '').upper()),{}))
                if opitem.get('_setup_declared'):
                    cfg['requires_setup']=bool(opitem.get('requires_setup'))
                    cfg['expected_setup_minutes']=(
                        opitem.get('expected_setup_minutes') if opitem.get('requires_setup') else None)
                conn.execute('INSERT INTO template_operations(template_id,part_id,code,name,sort_order,equipment_code,standard_seconds_per_unit,'
                    +','.join(PRESERVED)+') VALUES('+','.join(['%s']*(7+len(PRESERVED)))+')',
                    (t['id'],ids[opitem['part_key']],opitem['code'],opitem['name'],opitem['sort_order'],
                     opitem['equipment_code'],float(opitem.get('standard_seconds_per_unit') or 0))
                    +tuple(cfg[c] for c in PRESERVED))
        verb='cập nhật' if replaced else 'tạo'
        archive.record(data=raw_bytes,filename=upload.filename,
            outcome=OUTCOME_REPLACED if replaced else OUTCOME_CREATED,
            template_id=t['id'],template_code=code,part_count=len(parts),
            operation_count=len(operations),
            duplicate_operation_codes=_duplicate_operation_codes(operations),
            actor_user_id=actor_id,actor_username=actor_name)
        setup_count=sum(1 for o in operations if o.get('requires_setup'))
        message=f'Đã {verb} Template {code}: {len(parts)} Part, {len(operations)} Operation'
        message+=f', {setup_count} OP Setup.' if setup_count else '.'
        return jsonify(ok=True,message=message,template_id=t['id'],part_count=len(parts),
            operation_count=len(operations),setup_count=setup_count,
            warnings=import_warnings,dropped_setups=dropped_setups,
            source_format=source_format,replaced=replaced)
    except Exception as exc:
        # A rejected workbook is exactly the one someone needs to open, so the
        # attempt is archived even though the import itself rolled back.
        if raw_bytes:
            try:
                archive.record(data=raw_bytes,filename=upload.filename,outcome=OUTCOME_FAILED,
                    template_code=imported_code,error_message=str(exc),
                    actor_user_id=actor_id,actor_username=actor_name)
            except Exception:
                logging.getLogger(__name__).exception('Could not archive the rejected template workbook')
        return api_error_response(exc,logger_name=__name__)


@template_excel_bp.get('/<int:template_id>/import-history')
@login_required
def template_import_history(template_id:int):
    """Which workbooks produced this Template -- successes and rejections."""
    try:
        return jsonify(ok=True,items=TemplateImportRepository().list(template_id=template_id))
    except Exception as exc:
        return api_error_response(exc,logger_name=__name__)


@template_excel_bp.get('/import-history')
@login_required
def template_import_history_all():
    try:
        return jsonify(ok=True,items=TemplateImportRepository().list(
            template_code=str(request.args.get('template_code') or ''),
            limit=int(request.args.get('limit') or 200)))
    except Exception as exc:
        return api_error_response(exc,logger_name=__name__)


@template_excel_bp.get('/import-history/<int:import_id>/download')
@roles_required('admin','manager')
def download_template_import(import_id:int):
    """Hand back the exact bytes that were uploaded, under the original name."""
    try:
        row=TemplateImportRepository().file_for(import_id)
        if not row:
            raise NotFoundError('Không tìm thấy lần nhập Template này.')
        path=Path(row['storage_path'])
        if not path.exists():
            raise NotFoundError('File Excel của lần nhập này không còn trên máy chủ.')
        return send_file(path,as_attachment=True,
            download_name=row['original_filename'] or path.name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as exc:
        return api_error_response(exc,logger_name=__name__)
