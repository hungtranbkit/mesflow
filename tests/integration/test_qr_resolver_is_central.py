"""Mọi đường quét QR phải trả lời GIỐNG NHAU, nhất là ở ca mơ hồ.

Việc giải mã QR từng được chép ở bốn nơi, và chúng không đồng ý với nhau ở đúng
ca nguy hiểm nhất:

    execution.py    mã trùng ở nhiều Part -> TỪ CHỐI
    kiosk.py        mã trùng ở nhiều Part -> LIMIT 1, lấy đại một dòng
    offline_sync.py mã trùng ở nhiều Part -> LIMIT 1, lấy đại một dòng

`LIMIT 1` ở đây không phải tối ưu, nó là ĐOÁN. Công nhân quét tem của Operation
này, hệ thống mở Operation khác, sản lượng ghi vào chỗ khác -- và không có gì
báo, vì với hệ thống thì mọi thứ đều hợp lệ.

Ca này không hiếm: từ khi mã Operation chỉ unique trong phạm vi Part, hai Part
trong cùng một PO có 'OP01' là chuyện bình thường. Mọi tem in theo định dạng cũ
`WF|OP|<code>` cho các mã đó đều mơ hồ.

Bài test dựng đúng hình dạng đó rồi hỏi CẢ BA đường, và đòi cả ba cùng từ chối.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _duplicate_code_graph(db, suffix):
    """Dựng đúng hình mơ hồ CÓ THẬT với ràng buộc hiện tại.

    operations.code và operations.qr đều UNIQUE toàn cục, nên không thể có hai
    Operation cùng mã. Nhưng bộ giải mã tem cũ khớp bằng
    ``upper(qr)=upper(payload) OR upper(code)=upper(<phần đuôi payload>)`` --
    hai vế OR nhìn vào HAI CỘT khác nhau. Vậy nên một tem vẫn khớp hai dòng:

        A: qr='WF|OP|DUP-xxx'   (khớp vế thứ nhất)
        B: code='DUP-xxx'       (khớp vế thứ hai)

    Đây không phải tình huống bịa: sinh mã tự động đặt qr theo mã của chính OP
    đó, nên chỉ cần một OP được đặt mã trùng với phần đuôi tem của OP khác là
    đủ. LIMIT 1 sẽ chọn một trong hai theo thứ tự CSDL trả về -- tức là ngẫu
    nhiên với người dùng.
    """
    shared = f'DUP-{suffix}'
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',100,'IN_PROGRESS') RETURNING id""", (f'PO-QR-{suffix}',))
        po_id = cur.fetchone()['id']
        ids = {}
        for idx, (part_code, code, qr) in enumerate((
                ('PA', f'PA-{shared}', f'WF|OP|{shared}'),
                ('PB', shared, f'WF|OPID|PB-{shared}'))):
            cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
                VALUES(%s,%s,%s,%s,true) RETURNING id""",
                (po_id, part_code, f'Part {part_code}', idx))
            part_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
                VALUES(%s,%s,%s,%s,'PLANNED',%s,%s) RETURNING id""",
                (po_id, part_id, code, f'Công đoạn {part_code}', qr, idx))
            ids[part_code] = cur.fetchone()['id']
    return {'po_id': po_id, 'shared': shared, 'ids': ids}


def _drop(db, g):
    with db.cursor() as cur:
        cur.execute("""DELETE FROM work_sessions WHERE operation_id IN
            (SELECT id FROM operations WHERE production_order_id=%s)""", (g['po_id'],))
        cur.execute('DELETE FROM operations WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM parts WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (g['po_id'],))


def test_ambiguous_legacy_qr_is_refused_by_the_api_lookup(db, api):
    suffix = uuid.uuid4().hex[:8].upper()
    g = _duplicate_code_graph(db, suffix)
    try:
        response = api.get(f"{BASE_URL}/api/lookup?qr=WF|OP|{g['shared']}", timeout=20)
        assert response.status_code >= 400, (
            f'tra cứu API đã ĐOÁN thay vì từ chối: {response.text[:200]}')
        assert 'trùng' in response.json().get('message', '').lower() \
            or 'nhiều' in response.json().get('message', '').lower(), response.text[:200]
    finally:
        _drop(db, g)


def test_ambiguous_legacy_qr_is_refused_by_the_kiosk_scan(db, api):
    """Đường kiosk trước đây LIMIT 1 -- đây là chỗ đoán bừa gây hại nhất."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _duplicate_code_graph(db, suffix)
    try:
        response = api.post(f'{BASE_URL}/api/kiosk/scan',
                            json={'qr': f"WF|OP|{g['shared']}"}, timeout=20)
        assert response.status_code >= 400, (
            f'kiosk đã mở một Operation tuỳ ý cho tem mơ hồ: {response.text[:250]}')
        body = response.json()
        message = str(body.get('message') or body.get('error') or '')
        assert message, body
        # Không được trả về một operation cụ thể nào.
        assert not body.get('operation'), body
    finally:
        _drop(db, g)


def test_id_based_qr_always_resolves_even_when_the_code_is_ambiguous(db, api):
    """Tem mới giải được duy nhất -- đó là cả lý do đổi sang WF|OPID|."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _duplicate_code_graph(db, suffix)
    try:
        for part_code, op_id in g['ids'].items():
            response = api.get(f'{BASE_URL}/api/lookup?qr=WF|OPID|{op_id}', timeout=20)
            assert response.status_code == 200, response.text[:200]
            item = response.json().get('item') or response.json().get('operation') or {}
            assert int(item.get('id') or 0) == op_id, (part_code, item)
    finally:
        _drop(db, g)


def test_unambiguous_legacy_qr_still_works(db, api):
    """Tem cũ vẫn phải đọc được -- chúng đang dán ngoài xưởng."""
    suffix = uuid.uuid4().hex[:8].upper()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',10,'IN_PROGRESS') RETURNING id""", (f'PO-QR1-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,'PA','Thân',0,true) RETURNING id""", (po_id,))
        part_id = cur.fetchone()['id']
        code = f'SOLO-{suffix}'
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Cắt','PLANNED',%s,0) RETURNING id""",
            (po_id, part_id, code, f'WF|OP|{code}'))
        op_id = cur.fetchone()['id']
    try:
        response = api.get(f'{BASE_URL}/api/lookup?qr=WF|OP|{code}', timeout=20)
        assert response.status_code == 200, response.text[:200]
        item = response.json().get('item') or response.json().get('operation') or {}
        assert int(item.get('id') or 0) == op_id
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM parts WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))


def test_no_scan_path_keeps_its_own_limit_one_guess():
    """Chốt ở mức nguồn: không đường quét nào được quay lại LIMIT 1.

    Một bài test hành vi chỉ phủ được ca ta nghĩ ra. Assertion nguồn này bắt
    đúng thứ đã gây ra bug -- việc chọn LIMIT 1 thay vì phân biệt một với nhiều.
    """
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    for rel in ('app/mesflow/web/kiosk.py',
                'app/mesflow/web/execution.py',
                'app/mesflow/db/repositories/offline_sync.py'):
        source = (root / rel).read_text(encoding='utf-8')
        code_only = '\n'.join(line for line in source.split('\n')
                              if not line.lstrip().startswith('#'))
        # Chỉ bắt tra cứu OPERATION. Trạm (stations) có mã unique toàn cục nên
        # LIMIT 1 ở đó là đúng -- dấu hiệu nhận biết là truy vấn Operation luôn
        # OR cả trên cột qr.
        offenders = [m for m in re.findall(r'[^\n]*LIMIT 1', code_only)
                     if 'qr)=upper' in m and 'code)=upper' in m]
        assert not offenders, f'{rel} còn đoán bằng LIMIT 1: {offenders}'
        assert 'qr_identity import' in code_only or 'resolve_operation_id' in code_only, (
            f'{rel} không dùng resolver chung')
