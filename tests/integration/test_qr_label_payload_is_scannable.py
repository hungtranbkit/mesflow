"""Một nhãn QR vừa in ra phải quét được, và phải nói đúng về Operation của nó.

Danh mục QR (`GET /api/qr-labels?type=OPERATION`) in ra hai thứ cho mỗi dòng:
chữ người đọc (display key `<part>-<mã>`) và payload máy quét
(`qr_payload`). Hai thứ đó phải nói về CÙNG MỘT Operation, và payload phải
giải ra được.

`operations.qr` CỐ Ý không bị viết lại khi mã đổi -- tem đã in và đang dán
ngoài xưởng phải tiếp tục quét được, đó là một quyết định chứ không phải thiếu
sót (xem docs/architecture/OPERATION_IDENTITY.md). Nhưng quyết định đó nói về
việc RESOLVER phải chấp nhận tem cũ; nó không nói rằng một tem MỚI IN được
phép mang mã đã chết. Hai việc khác nhau, và danh mục QR đang lẫn chúng.

Hai ca dưới đây đều dựng lại được bằng thao tác quản trị bình thường.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


@pytest.fixture
def po_with_part(db):
    sfx = _suffix()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',100,'IN_PROGRESS') RETURNING id""", (f'PO-QRL-{sfx}',))
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,%s,'Part',0,true) RETURNING id""", (po_id, f'PQRL-{sfx}'))
        part_id = cur.fetchone()['id']
    yield {'po_id': po_id, 'part_id': part_id, 'suffix': sfx}
    with db.cursor() as cur:
        cur.execute("DELETE FROM operations WHERE production_order_id=%s", (po_id,))
        cur.execute("DELETE FROM parts WHERE production_order_id=%s", (po_id,))
        cur.execute("DELETE FROM production_orders WHERE id=%s", (po_id,))


def _labels(api, po_id):
    response = api.get(f'{BASE_URL}/api/qr-labels',
                       params={'type': 'OPERATION', 'production_order_id': po_id,
                               'active_only': '0', 'limit': 500}, timeout=15)
    assert response.status_code == 200, response.text[:300]
    return {int(row['id']): row for row in response.json()['items']}


def test_a_reprinted_label_never_carries_a_code_the_operation_no_longer_has(api, db, po_with_part):
    """Đổi mã xong in lại: chữ trên nhãn và payload phải cùng nói về một Operation.

    Bản hiện tại in chữ theo mã MỚI nhưng payload vẫn mang mã CŨ, vì
    `COALESCE(NULLIF(o.qr,''),...)` giữ nguyên `operations.qr`. Người cầm tem
    đọc một mã, máy quét đọc một mã khác, và mã trong payload là mã không còn
    tồn tại trong hệ thống.
    """
    sfx = po_with_part['suffix']
    old_code = f'CUT-{sfx}'
    new_code = f'CUTNEW-{sfx}'
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Cắt','IN_PROGRESS',%s,0) RETURNING id""",
            (po_with_part['po_id'], po_with_part['part_id'], old_code, f'WF|OP|{old_code}'))
        op_id = cur.fetchone()['id']
        cur.execute("UPDATE operations SET code=%s WHERE id=%s", (new_code, op_id))

    row = _labels(api, po_with_part['po_id'])[op_id]
    payload = str(row['qr_payload'])
    printed = str(row['code'])

    assert new_code in printed, f'chữ in ra phải là mã hiện tại: {printed!r}'
    assert old_code not in payload, (
        f'nhãn vừa in mang mã đã chết {old_code!r} trong payload {payload!r}, '
        f'trong khi chữ in ra là {printed!r} -- hai thứ nói về hai mã khác nhau')
    # Cách đúng duy nhất để một payload nói về Operation này mà không phụ thuộc
    # mã: địa chỉ theo id bất biến.
    assert payload == f'WF|OPID|{op_id}', payload


def test_a_label_is_never_printed_with_a_payload_the_scanner_would_refuse(api, db, po_with_part):
    """Payload mơ hồ = tem không quét được. Không được in ra tem như vậy.

    Ca mơ hồ là CHÉO CỘT: `operations.qr` của dòng này đòi một mã, và mã đó là
    `code` của dòng KHÁC. Resolver gặp hai dòng thì từ chối (đúng thiết kế), nên
    in ra payload đó là phát cho xưởng một tem chết.

    Nhánh an toàn trong danh mục QR định lo việc này -- comment của nó nói
    "by id whenever its code is ambiguous" -- nhưng nó kiểm
    `d.code = o.code AND d.id <> o.id`, tức là đi tìm HAI Operation cùng mã, mà
    `operations_code_key` cấm đúng điều đó. Điều kiện không bao giờ đúng, nên
    lưới an toàn chưa bao giờ bật.
    """
    from mesflow.db.repositories.base import ConflictError
    from mesflow.domain.qr_identity import resolve_operation_id

    sfx = po_with_part['suffix']
    shared = f'AMBQ-{sfx}'
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'A','IN_PROGRESS',%s,0) RETURNING id""",
            (po_with_part['po_id'], po_with_part['part_id'], shared, f'WF|OP|{shared}'))
        first_id = cur.fetchone()['id']
        cur.execute("UPDATE operations SET code=%s WHERE id=%s", (f'{shared}-OLD', first_id))
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'B','IN_PROGRESS',%s,1) RETURNING id""",
            (po_with_part['po_id'], po_with_part['part_id'], shared, f'WF|OPID|PENDING-{sfx}'))
        second_id = cur.fetchone()['id']
        cur.execute("UPDATE operations SET qr=%s WHERE id=%s", (f'WF|OPID|{second_id}', second_id))

    # Tiền đề: payload cũ của dòng thứ nhất giờ THẬT SỰ mơ hồ.
    with pytest.raises(ConflictError):
        resolve_operation_id(f'WF|OP|{shared}')

    rows = _labels(api, po_with_part['po_id'])
    payload = str(rows[first_id]['qr_payload'])
    assert payload != f'WF|OP|{shared}', (
        f'danh mục in ra payload {payload!r} mà chính resolver từ chối -- tem chết')
    assert payload == f'WF|OPID|{first_id}', payload

    # Và tem in ra phải quét được thật, không chỉ "khác cái cũ".
    assert resolve_operation_id(payload) == first_id


def test_an_untouched_operation_keeps_the_label_already_printed_in_the_workshop(api, db, po_with_part):
    """Không được đổi payload của Operation bình thường.

    Đây là vế giữ an toàn của bản vá: hàng nghìn tem `WF|OP|<mã>` đang dán
    ngoài xưởng, và in lại một tem như thế phải ra đúng chuỗi cũ, nếu không
    cùng một Operation lại có hai tem khác nhau mà không vì lý do gì.
    """
    sfx = po_with_part['suffix']
    code = f'OK-{sfx}'
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Bình thường','IN_PROGRESS',%s,0) RETURNING id""",
            (po_with_part['po_id'], po_with_part['part_id'], code, f'WF|OP|{code}'))
        op_id = cur.fetchone()['id']

    row = _labels(api, po_with_part['po_id'])[op_id]
    assert row['qr_payload'] == f'WF|OP|{code}', row['qr_payload']


def test_a_setup_label_keeps_its_id_payload(api, db, po_with_part):
    """OP phụ SETUP vốn đã dùng tem theo id -- bản vá không được đụng vào."""
    sfx = po_with_part['suffix']
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Cha','IN_PROGRESS',%s,0) RETURNING id""",
            (po_with_part['po_id'], po_with_part['part_id'], f'PAR-{sfx}', f'WF|OP|PAR-{sfx}'))
        parent_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,
                sort_order,operation_type,parent_operation_id)
            VALUES(%s,%s,%s,'Setup','PLANNED',%s,2147483646,'SETUP',%s) RETURNING id""",
            (po_with_part['po_id'], po_with_part['part_id'], f'PAR-{sfx}-SU',
             f'WF|OPID|PENDING-{sfx}', parent_id))
        setup_id = cur.fetchone()['id']
        cur.execute("UPDATE operations SET qr=%s WHERE id=%s", (f'WF|OPID|{setup_id}', setup_id))

    row = _labels(api, po_with_part['po_id'])[setup_id]
    assert row['qr_payload'] == f'WF|OPID|{setup_id}', row['qr_payload']
