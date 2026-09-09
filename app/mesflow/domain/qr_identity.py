"""Một chỗ duy nhất biến một mã QR quét được thành một Operation.

LÝ DO TỒN TẠI. Việc giải mã QR được chép ở bốn nơi -- kiosk v1 (kiosk.py),
tra cứu API (execution.py), đồng bộ offline (offline_sync.py), và đường xem
trước/in hàng loạt. Bốn bản chép, và chúng KHÔNG đồng ý với nhau ở đúng ca
nguy hiểm nhất:

    execution.py    mã trùng ở nhiều Part -> TỪ CHỐI
    kiosk.py        mã trùng ở nhiều Part -> LIMIT 1, lấy đại một dòng
    offline_sync.py mã trùng ở nhiều Part -> LIMIT 1, lấy đại một dòng

`LIMIT 1` ở đây không phải tối ưu, nó là đoán. Công nhân quét tem của Operation
này, hệ thống mở Operation khác, sản lượng ghi vào chỗ khác -- và không có gì
báo, vì với hệ thống thì mọi thứ đều hợp lệ.

Ca này KHÔNG hiếm: từ khi mã Operation chỉ unique trong phạm vi Part
(2026-09-09), hai Part trong cùng một PO có `OP01` là chuyện bình thường, và
Template editor cho phép. Mọi tem in theo định dạng cũ `WF|OP|<code>` cho các
mã đó đều mơ hồ.

NGUYÊN TẮC.

  * `operations.id` là danh tính. Tem mới dùng `WF|OPID|<id>` và luôn giải được
    duy nhất.
  * Tem cũ `WF|OP|<code>` vẫn phải đọc được -- chúng đã in và đang dán ngoài
    xưởng. Chỉ chấp nhận khi mã giải ra ĐÚNG MỘT Operation.
  * Mơ hồ thì TỪ CHỐI, kèm câu nói rõ phải làm gì (in lại tem). Thà bắt người
    ta in lại một tem còn hơn ghi sản lượng vào nhầm công đoạn.
  * Có thể thu hẹp bằng ngữ cảnh Part/PO khi nơi gọi biết -- ví dụ kiosk đã gắn
    với một trạm đang chạy một PO.

Module này chỉ trả về ID. Mỗi nơi gọi vẫn tự SELECT những cột nó cần: ép tất cả
dùng chung một tập cột sẽ khiến module này phình ra thành nơi chứa mọi truy vấn
Operation của hệ thống, đúng thứ ta đang gỡ.
"""
from __future__ import annotations

from mesflow.db.repositories.base import ConflictError, NotFoundError

OPID_PREFIX = 'WF|OPID|'
LEGACY_PREFIX = 'WF|OP|'


def parse_operation_qr(raw: str | None) -> tuple[str, str]:
    """Tách một payload QR thành (loại, khoá).

    Trả về ``('OPID', '<id>')``, ``('OP', '<code>')`` hoặc ``('', '')`` nếu
    không phải QR Operation. Không chạm cơ sở dữ liệu.

    Chú ý thứ tự kiểm: 'WF|OPID|4243' cũng bắt đầu bằng... không, nó KHÔNG bắt
    đầu bằng 'WF|OP|' vì ký tự thứ 7 là 'I' chứ không phải '|'. Đó chính là chỗ
    một bản vá trước đã trượt: `startswith('WF|OP|')` trả False cho payload
    OPID, nên đường tra cứu cũ không nhận ra tem mới (P0-1, 71.0.0.253).
    """
    text = str(raw or '').strip()
    upper = text.upper()
    if upper.startswith(OPID_PREFIX):
        return 'OPID', text[len(OPID_PREFIX):].strip()
    if upper.startswith(LEGACY_PREFIX):
        return 'OP', text[len(LEGACY_PREFIX):].strip()
    return '', ''


def is_operation_qr(raw: str | None) -> bool:
    return parse_operation_qr(raw)[0] != ''


def resolve_operation_id(raw: str | None, *, part_id: int | None = None,
                         production_order_id: int | None = None,
                         allow_bare_code: bool = True) -> int:
    """Mã QR quét được -> id Operation, hoặc ném lỗi nói rõ vì sao không được.

    ``part_id`` / ``production_order_id`` là ngữ cảnh tuỳ chọn để thu hẹp khi
    nơi gọi biết mình đang ở đâu. Chúng chỉ THU HẸP, không bao giờ mở rộng: một
    tem thuộc PO khác vẫn không giải ra được dù mã có trùng.

    ``allow_bare_code`` cho phép chấp nhận chuỗi trần không có tiền tố (một số
    máy quét cũ gửi thẳng mã). Vẫn phải giải ra duy nhất.

    Ném NotFoundError nếu không có, ConflictError nếu mơ hồ.
    """
    from mesflow.db.connection import fetch_all

    text = str(raw or '').strip()
    if not text:
        raise NotFoundError('Chưa có mã QR để tra cứu')

    kind, key = parse_operation_qr(text)
    if kind == 'OPID':
        if not key.isdigit():
            raise NotFoundError(f'Mã QR không hợp lệ: {text}')
        rows = fetch_all('SELECT id FROM operations WHERE id=%s', (int(key),))
        if not rows:
            raise NotFoundError(f'Không tìm thấy Operation cho tem {text}')
        return int(rows[0]['id'])

    if kind == 'OP':
        code = key
    elif allow_bare_code:
        code = text
    else:
        raise NotFoundError(f'Mã QR không đúng định dạng Operation: {text}')

    where = ['(upper(o.qr)=upper(%s) OR upper(o.code)=upper(%s))']
    params: list[object] = [text, code]
    if part_id is not None:
        where.append('o.part_id=%s')
        params.append(int(part_id))
    if production_order_id is not None:
        where.append('o.production_order_id=%s')
        params.append(int(production_order_id))

    # LIMIT 5 chứ không LIMIT 1: phải PHÂN BIỆT ĐƯỢC "một" với "nhiều". LIMIT 1
    # làm hai ca đó trông giống hệt nhau, và đó chính là cách bản cũ đoán bừa mà
    # không ai biết.
    rows = fetch_all(
        'SELECT o.id,o.code,o.part_id,p.code part_code FROM operations o '
        'LEFT JOIN parts p ON p.id=o.part_id WHERE ' + ' AND '.join(where) + ' LIMIT 5',
        tuple(params))
    if not rows:
        raise NotFoundError(f'Không tìm thấy Operation cho tem {text}')
    if len(rows) > 1:
        where_seen = ', '.join(
            f"{r.get('part_code') or '?'}/{r.get('code')}" for r in rows[:4])
        raise ConflictError(
            f'Mã Operation {code} trùng ở nhiều Part ({where_seen}), không xác định được '
            'nên quét mã nào. In lại tem QR cho Operation này.')
    return int(rows[0]['id'])
