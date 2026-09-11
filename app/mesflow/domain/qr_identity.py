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


class AmbiguousOperationQR(ConflictError):
    """Một tem cũ giải ra NHIỀU HƠN MỘT Operation.

    Là một loại riêng chứ không phải ConflictError trần, vì mỗi đường quét
    phải xử lý nó KHÁC với mọi đụng độ nghiệp vụ khác. Một ConflictError bình
    thường ("OP nguồn chưa có hàng để cấp", "session khác đang mở") có thể tự
    đúng lại khi công đoạn trước nhập số hay người khác kết thúc việc của họ --
    nên thử lại là hợp lý. Tem trùng thì KHÔNG: nó chỉ hết khi có người in lại
    tem. Bảo thiết bị thử lại là bắt nó quay vòng tới lúc hết lượt, và không ai
    biết phải sửa gì.

    Kế thừa ConflictError để mọi nơi đã bắt ConflictError (HTTP 409, phân loại
    giữ-lại-để-thử-lại của offline sync) tiếp tục chạy y như trước; nơi nào cần
    phân biệt thì kiểm loại này TRƯỚC. Không nơi nào phải dò chuỗi tiếng Việt
    trong message để đoán ra ý nghĩa.
    """


class AmbiguousEmployeeQR(ConflictError):
    """Một thẻ nhân viên quét ra NHIỀU HƠN MỘT người.

    Cùng họ với AmbiguousOperationQR, và cùng lý do phải là loại riêng. Nhưng
    hậu quả nặng hơn: công của cả một ca ghi sang tên người khác -- sai lương,
    sai năng suất, sai phiếu phạt -- và không có gì báo, vì với hệ thống thì
    mọi thứ đều hợp lệ.

    `employees.employee_no` và `employees.qr` đều unique RIÊNG LẺ, nhưng không
    unique CHÉO NHAU: chuỗi 'WF|EMP|E2' có thể vừa là `qr` của người E1 vừa
    trỏ tới `employee_no` của người E2. Dựng lại được bằng đúng API quản trị --
    `qr` là cột ghi được. Lúc đó LIMIT 1 chọn theo thứ tự vật lý của bảng.
    """


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
        raise AmbiguousOperationQR(
            f'Mã Operation {code} trùng ở nhiều Part ({where_seen}), không xác định được '
            'nên quét mã nào. In lại tem QR cho Operation này.')
    return int(rows[0]['id'])


EMPLOYEE_PREFIX = 'WF|EMP|'


def resolve_employee_id(raw: str | None) -> int:
    """Thẻ nhân viên quét được -> id nhân viên, hoặc lỗi nói rõ vì sao không.

    Chấp nhận cả `WF|EMP|<mã>` lẫn mã trần, và khớp theo `qr` HOẶC
    `employee_no` -- đúng như ba bản chép cũ ở kiosk v1, execution.py và
    offline_sync.py. Khác một điều duy nhất, và là điều quan trọng: khi chuỗi
    quét được khớp nhiều hơn một người thì TỪ CHỐI, thay vì LIMIT 1 lấy đại.

    Chỉ trả về id. Mỗi nơi gọi vẫn tự SELECT các cột nó cần, cùng lý do đã ghi
    ở đầu module này cho resolve_operation_id().
    """
    from mesflow.db.connection import fetch_all

    text = str(raw or '').strip()
    if not text:
        raise NotFoundError('Chưa có mã thẻ để tra cứu')
    key = text[len(EMPLOYEE_PREFIX):].strip() if text.upper().startswith(EMPLOYEE_PREFIX) else text

    # LIMIT 5, không LIMIT 1 -- phải phân biệt được "một" với "nhiều".
    rows = fetch_all(
        'SELECT id,employee_no,name FROM employees '
        'WHERE active=TRUE AND (upper(qr)=upper(%s) OR upper(employee_no)=upper(%s)) LIMIT 5',
        (text, key))
    if not rows:
        raise NotFoundError('Không tìm thấy nhân viên đang hoạt động')
    if len(rows) > 1:
        who = ', '.join(f"{r.get('employee_no')} ({r.get('name')})" for r in rows[:4])
        raise AmbiguousEmployeeQR(
            f'Thẻ {text} trỏ tới nhiều nhân viên ({who}), không xác định được là ai. '
            'Sửa lại mã QR của các nhân viên này trong Danh mục rồi in lại thẻ.')
    return int(rows[0]['id'])


def printable_qr_payload_sql(op_alias: str = 'o') -> str:
    """SQL: payload nào được phép IN RA cho một Operation.

    Khác với việc resolver CHẤP NHẬN cái gì. Resolver phải rộng rãi -- tem cũ
    đã dán ngoài xưởng phải tiếp tục quét được, nên nó nhận cả `qr` lẫn `code`.
    Còn cái in ra hôm nay thì phải hẹp: một tem MỚI không được mang mã đã chết,
    và tuyệt đối không được mang payload mà chính resolver sẽ từ chối.

    Hai thứ đó từng bị lẫn làm một. Danh mục QR giữ nguyên `operations.qr` cho
    mọi dòng, kèm một nhánh dự phòng định chuyển sang id "khi mã mơ hồ" -- nhưng
    nhánh ấy kiểm `d.code = o.code AND d.id <> o.id`, tức đi tìm hai Operation
    cùng mã, mà `operations_code_key` cấm đúng điều đó. Điều kiện không bao giờ
    đúng; lưới an toàn chưa từng bật.

    Sự mơ hồ THẬT nằm chéo cột: `qr` của dòng này đòi một mã, và mã đó là `code`
    của dòng KHÁC (xảy ra sau khi đổi tên -- `qr` cố ý không được viết lại -- rồi
    mã vừa giải phóng được cấp cho Operation khác).

    Quy tắc:

      * không có payload lưu sẵn -> địa chỉ theo id;
      * tem cũ `WF|OP|<mã>` mà mã trong tem KHÁC mã hiện tại (đã đổi tên), hoặc
        mã đó đang là `code` của dòng khác (mơ hồ) -> địa chỉ theo id;
      * còn lại giữ nguyên payload đang có -- kể cả `WF|OPID|` lẫn payload tự
        đặt -- để in lại một tem bình thường ra đúng chuỗi đang dán ngoài xưởng.

    Dùng `left(...)` chứ không `LIKE '...%'`: psycopg đọc một dấu `%` trong câu
    lệnh CÓ tham số như một placeholder rồi từ chối cả câu. Biểu thức này được
    nhúng vào đúng loại câu đó, nên `%` sẽ làm hỏng toàn bộ danh mục QR (HTTP
    500). Cùng lý do đã ghi ở `setup_ops.DISPLAY_KEY_SQL`.
    """
    op = op_alias
    legacy_code = f'substring({op}.qr from {len(LEGACY_PREFIX) + 1})'
    return (
        "CASE "
        f"WHEN COALESCE({op}.qr,'')='' THEN '{OPID_PREFIX}'||{op}.id "
        f"WHEN left(upper({op}.qr),{len(LEGACY_PREFIX)})='{LEGACY_PREFIX}' AND ("
        f"upper({legacy_code}) <> upper({op}.code) "
        f"OR EXISTS (SELECT 1 FROM operations d WHERE d.id<>{op}.id "
        f"AND upper(d.code)=upper({legacy_code}))"
        f") THEN '{OPID_PREFIX}'||{op}.id "
        f"ELSE {op}.qr END"
    )
