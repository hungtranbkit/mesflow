"""Một đường nhập Router duy nhất, cho cả màn Template lẫn màn Production Order.

LÝ DO TỒN TẠI. Hai màn hình cùng nhận một loại file thì phải đi qua cùng một
service. Hai đường nhập riêng là hai bộ ngữ nghĩa sẽ trôi khỏi nhau — một bên
đọc số lượng Part, bên kia quên; một bên tạo OP SETUP, bên kia không — và sai
lệch chỉ lộ ra khi hai người nhập cùng một file rồi nhận hai kết quả khác nhau.
Màn PO ở đây là NGƯỜI GỌI, không phải một luồng thứ hai.

BA QUYẾT ĐỊNH ĐÁNG GHI.

1. Danh tính của một lần nhập là **sha256 của chính bytes**, không phải tên file
   và không phải mã Template. Kho blob (migration 0046) vốn đã đánh địa chỉ theo
   nội dung; cái thiếu là bảng nối "Template NÀY dựng từ file NÀO"
   (``template_source_workbooks``, migration 0052). Nhờ khoá đó, nhập lại ĐÚNG
   một file là no-op sạch — kể cả khi PO đã tồn tại. Đây là chỗ dễ sai nhất:
   nếu để nhánh "PO đã tồn tại" chặn trước, thì gửi lại đúng file cũ sẽ báo lỗi,
   và "nhập lại phải idempotent" bị vi phạm.

2. **PO đã tồn tại thì DỪNG**, không cập nhật. Không có ngữ nghĩa merge nào được
   định nghĩa cho một PO đã chạy và đã có dữ liệu vận hành; đoán một cái ở đây
   là ghi đè số liệu thật của xưởng. Sửa một PO đang chạy là tính năng riêng,
   phải được thiết kế riêng, không phải tác dụng phụ của việc nhập file.

3. **Ghi đè Template phải được xác nhận.** Nhập một file mới trùng mã Template
   sẽ viết lại Template mà những PO khác đã dựng từ đó. PO cũ không đổi
   (instantiate là sao chép), nhưng Template thì dùng chung — và từ màn PO, ý
   định của người dùng là "tạo PO", không phải "viết lại Template". Nên bước đó
   đòi ``confirm`` và màn xem trước phải nói rõ có bao nhiêu PO đã dựng từ nó.

Toàn bộ phần ghi nằm trong MỘT transaction, kể cả dòng nối blob↔Template. Không
phải để "dọn dẹp cho gọn": rollback giữa chừng mà dòng nối đã ghi thì kho file
trỏ tới một Template chưa từng tồn tại.
"""
from __future__ import annotations

import hashlib

from mesflow.db.connection import fetch_all, fetch_one


class RouterImportError(Exception):
    """Nhập không đi tiếp được, và lý do là thứ người dùng xử lý được."""

    def __init__(self, message, *, reason, detail=None):
        super().__init__(message)
        self.reason = reason
        self.detail = detail or {}


#: Hành động với Template.
TEMPLATE_REUSE = 'REUSE'      # đúng file này đã nhập -> không ghi gì
TEMPLATE_UPDATE = 'UPDATE'    # trùng mã, nội dung khác -> cần confirm
TEMPLATE_CREATE = 'CREATE'

#: Hành động với Production Order.
PO_CREATE = 'CREATE'
PO_EXISTS = 'EXISTS'          # dừng, không ghi đè
PO_NONE = 'NONE'              # file không có mã PO -> chỉ Template


def workbook_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _template_by_code(code):
    return fetch_one('SELECT id,code,name FROM templates WHERE UPPER(code)=UPPER(%s)', (code,))


def _template_linked_to(digest):
    """Template đã dựng từ đúng bytes này, nếu có."""
    return fetch_one("""SELECT t.id,t.code,t.name,w.original_filename,w.linked_at
        FROM template_source_workbooks w JOIN templates t ON t.id=w.template_id
        WHERE w.sha256=%s ORDER BY w.linked_at DESC LIMIT 1""", (digest,))


def _po_by_code(code):
    return fetch_one("""SELECT id,code,status,planned_quantity
        FROM production_orders WHERE UPPER(code)=UPPER(%s)""", (code,))


def _po_count_for_template(template_id):
    row = fetch_one('SELECT COUNT(*) c FROM production_orders WHERE source_template_id=%s',
                    (int(template_id),))
    return int(row['c']) if row else 0


def plan_import(parsed, digest):
    """Quyết định SẼ làm gì, không ghi gì. Dùng chung cho preview và cho import.

    Tách khỏi phần ghi có chủ đích: màn xem trước và lần nhập thật phải nói cùng
    một câu, nên chúng phải chạy cùng một hàm quyết định.
    """
    linked = _template_linked_to(digest)
    template_code = parsed['code']
    po_code = (parsed.get('po') or '').strip()

    if linked:
        template = {'action': TEMPLATE_REUSE, 'id': linked['id'], 'code': linked['code'],
                    'name': linked['name'], 'needs_confirm': False,
                    'message': f"Dùng lại Template {linked['code']} — đúng file này đã nhập trước đó."}
    else:
        existing = _template_by_code(template_code)
        if existing:
            built = _po_count_for_template(existing['id'])
            template = {
                'action': TEMPLATE_UPDATE, 'id': existing['id'], 'code': existing['code'],
                'name': existing['name'], 'needs_confirm': True, 'po_built_from_it': built,
                'message': (f"Cập nhật Template {existing['code']} bằng nội dung file này. "
                            + (f'Đã có {built} Production Order dựng từ Template này; '
                               'các PO đó không đổi, nhưng Template dùng chung sẽ được '
                               'viết lại.' if built else
                               'Chưa có Production Order nào dựng từ Template này.'))}
        else:
            template = {'action': TEMPLATE_CREATE, 'id': None, 'code': template_code,
                        'name': parsed['name'], 'needs_confirm': False,
                        'message': f'Tạo Template mới {template_code}.'}

    if not po_code:
        po = {'action': PO_NONE, 'code': '', 'id': None,
              'message': ('File không có mã PO nên chỉ tạo/cập nhật Template. '
                          'Tạo Production Order bằng thao tác riêng sau đó.')}
    else:
        existing_po = _po_by_code(po_code)
        if existing_po:
            po = {'action': PO_EXISTS, 'code': existing_po['code'], 'id': existing_po['id'],
                  'status': existing_po['status'],
                  'message': (f"Production Order {existing_po['code']} đã tồn tại "
                              f"(trạng thái {existing_po['status']}). Lần nhập này KHÔNG ghi đè "
                              'nó — sửa một PO đang chạy là thao tác riêng, không phải tác '
                              'dụng phụ của việc nhập file.')}
        else:
            po = {'action': PO_CREATE, 'code': po_code, 'id': None,
                  'planned_quantity': parsed.get('qty') or 0,
                  'message': (f"Tạo Production Order {po_code}, số lượng "
                              f"{parsed.get('qty') or 0}.")}
    return {'template': template, 'po': po, 'digest': digest}


def assert_can_apply(plan, *, confirm, can_manage_templates, can_manage_pos):
    """Chặn TRƯỚC khi ghi: quyền, và xác nhận cho việc ghi đè Template.

    Kiểm ở đây chứ không ở chỗ ẩn nút: một client khác gọi thẳng API cũng phải
    đi qua đúng hàng rào này. Và kiểm TRƯỚC mọi lệnh ghi, để trường hợp "có
    quyền tạo PO nhưng không có quyền Template" không để lại Template dở dang.
    """
    template, po = plan['template'], plan['po']
    if template['action'] in (TEMPLATE_CREATE, TEMPLATE_UPDATE) and not can_manage_templates:
        raise RouterImportError(
            'Bạn không có quyền tạo hoặc sửa Template, mà file này cần '
            f"{'tạo Template mới' if template['action'] == TEMPLATE_CREATE else 'cập nhật Template đang có'}. "
            'Không có gì được tạo. Nhờ người có quyền Template nhập file này trước.',
            reason='TEMPLATE_PERMISSION_REQUIRED', detail={'template_code': template['code']})
    if po['action'] == PO_CREATE and not can_manage_pos:
        raise RouterImportError(
            f"Bạn không có quyền tạo Production Order, mà file này khai báo PO {po['code']}. "
            'Không có gì được tạo.',
            reason='PO_PERMISSION_REQUIRED', detail={'po_code': po['code']})
    if template['action'] == TEMPLATE_UPDATE and not confirm:
        raise RouterImportError(
            template['message'] + ' Hãy xác nhận để tiếp tục.',
            reason='TEMPLATE_UPDATE_NEEDS_CONFIRM',
            detail={'template_code': template['code'],
                    'po_built_from_it': template.get('po_built_from_it', 0)})
    if po['action'] == PO_EXISTS:
        raise RouterImportError(po['message'], reason='PO_ALREADY_EXISTS',
                                detail={'po_code': po['code'], 'po_id': po['id']})


def preserved_key(operation):
    """Khoá nối cấu hình cũ với dòng mới khi cập nhật Template.

    KHÔNG dùng id: cập nhật Template là xoá rồi chèn lại, nên mọi id đều mới.
    Cũng không dùng riêng mã nội bộ: mã nội bộ được sinh ra, và khi file đánh
    trùng số OP thì hậu tố phụ thuộc THỨ TỰ đọc — chèn thêm một block ở giữa là
    mọi hậu tố phía sau dịch đi một nấc, và cấu hình nhảy sang nhầm công đoạn.

    Cặp (số OP gốc, tiêu đề gốc) là thứ ổn định: nó là cái ghi trên giấy.
    """
    return (int(operation.get('source_op_no') or 0),
            str(operation.get('source_title') or '').strip().upper(),
            str(operation.get('part_key') or '').strip().upper())


def link_workbook(conn, template_id, blob_id, digest, filename):
    """Nối blob với Template. Phải nằm TRONG transaction tạo Template."""
    conn.execute("""INSERT INTO template_source_workbooks
            (template_id,blob_id,sha256,original_filename)
        VALUES(%s,%s,%s,%s)
        ON CONFLICT (template_id,sha256) DO UPDATE
        SET original_filename=EXCLUDED.original_filename,
            linked_at=CURRENT_TIMESTAMP""",
        (int(template_id), int(blob_id), digest, str(filename or '')[:200]))


#: Ghi nhận KHÔNG phải cảnh báo.
#:
#: DUPLICATE_OP_IN_PART là lỗi chặn và đi qua `sections.error` với đúng câu đã
#: chốt, không phải một dòng người dùng có thể cuộn qua. NO_OPERATION_DATA là
#: chuyện bình thường của tờ mức quy trình. Cả hai đều không thuộc "cảnh báo cần
#: xử lý" -- danh sách đó chỉ nên chứa thứ người dùng THẬT SỰ phải làm gì đó.
INFO_NOTE_KINDS = frozenset({'DUPLICATE_OP_IN_PART'})


def unused_field_sections(parsed):
    """Ba mục màn xem trước phải hiện. Không có mục nào được rỗng một cách im lặng.

    Mục 2 là điều kiện của hợp đồng: field nào có trong Excel mà MESFlow chưa
    dùng thì phải ĐƯỢC NÓI RA, kèm sheet/ô/giá trị thô và lý do — không được
    biến mất.
    """
    imported = {
        'po': {'code': parsed.get('po') or '', 'quantity': parsed.get('qty') or 0,
               'order_type': parsed.get('order_type') or ''},
        'parts': [{'code': p['code'], 'name': p['name'],
                   'planned_quantity': p.get('planned_quantity'),
                   'sheet': p.get('source_sheet') or '',
                   'images': p.get('image_count') or 0}
                  for p in parsed['parts']],
        'operation_count': len(parsed['operations']),
        'setup_count': sum(1 for op in parsed['operations'] if op.get('requires_setup')),
    }

    unused = []
    meta = parsed.get('source_document_meta') or ''
    if meta:
        unused.append({'field': 'Mã số / Lần ban hành / Ngày BH', 'sheet': '(mọi sheet)',
                       'cell': 'J1', 'raw': meta,
                       'reason': 'Metadata biểu mẫu — MESFlow chưa có trường tương ứng; '
                                 'giữ trong file nguồn đã lưu.'})
    if parsed.get('po_note'):
        unused.append({'field': 'CHÚ Ý', 'sheet': '(sheet đầu)', 'cell': 'CHÚ Ý',
                       'raw': parsed['po_note'],
                       'reason': 'Ghi chú của tờ router — chưa map vào trường PO.'})
    images = sum(p.get('image_count') or 0 for p in parsed['parts'])
    if images:
        unused.append({'field': 'HÌNH ẢNH', 'sheet': '(nhiều sheet)', 'cell': 'vùng ảnh',
                       'raw': f'{images} ảnh nhúng',
                       'reason': 'Ảnh tham chiếu Part — chưa trích vào drawing_path; '
                                 'vẫn còn nguyên trong file nguồn đã lưu.'})
    totals = [op for op in parsed['operations'] if op.get('total_expected_seconds')]
    if totals:
        unused.append({
            'field': 'Tổng thời gian gia công dự kiến', 'sheet': '(mọi block)',
            'cell': 'cột M', 'raw': f'{len(totals)} Operation có giá trị',
            'reason': 'Được LƯU làm số liệu nguồn (expected_total_seconds) nhưng chưa có '
                      'màn hình nào hiển thị; không dùng để suy lại số lượng.'})
    unused.append({
        'field': 'Ngày/Tháng/Năm · Nhân viên Setup · Nhân viên SX · Nhân viên QC · '
                 'Hàng đạt · Hàng lỗi · Tổng số lượng sản xuất · Xác nhận',
        'sheet': '(mọi block)', 'cell': 'cột A', 'raw': '(đang trống)',
        'reason': 'Trường VẬN HÀNH — MESFlow thu thập qua Session/QC/duyệt. '
                  'Không tạo dữ liệu thực tế giả khi nhập.'})

    # Trùng số OP trong cùng Part KHÔNG nằm ở đây: nó là LỖI CHẶN, đi qua
    # `sections.error` với đúng câu đã chốt, chứ không phải một dòng trong danh
    # sách cảnh báo mà người dùng có thể cuộn qua.
    # Ghi nhận trung tính đi vào mục "có trong Excel nhưng chưa dùng", không vào
    # "cảnh báo cần xử lý": một tờ mức quy trình không có công đoạn nào là chuyện
    # bình thường, người dùng không phải làm gì cả.
    warnings = [note for note in (parsed.get('notes') or [])
                if note.get('kind') not in INFO_NOTE_KINDS]
    return {'imported': imported, 'unused': unused, 'warnings': warnings}
