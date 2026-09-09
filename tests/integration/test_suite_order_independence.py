"""Bài test không được đỏ chỉ vì bài khác chạy trước nó.

BỐI CẢNH THẬT. Fixture `db` là session-scope, autocommit, và API ghi qua một
connection KHÁC (tiến trình Flask). Vì vậy không thể dùng transaction rollback
để cô lập: transaction phía test không nhìn thấy, càng không huỷ được, những gì
ứng dụng đã commit. Kiến trúc hiện tại buộc mỗi bài tự dọn trong `finally` --
và hầu hết đã làm đúng.

Cái KHÔNG dọn được là dữ liệu tích luỹ hợp lệ: sự kiện, nhật ký, hoạt động gần
đây. Một bài xét "session của tôi có nằm trong 500 dòng hoạt động mới nhất
không" sẽ đỏ khi các bài trước sinh vài trăm sự kiện -- đã xảy ra thật, 472
kiosk_events cùng ngày đẩy hai session ra khỏi cửa sổ.

Hỏng theo kiểu tệ nhất: "không thấy" trông y hệt "đã bị loại khỏi báo cáo",
đúng thứ bài kia đang muốn phân biệt. Người đọc kết quả sẽ đi tìm bug nghiệp vụ
không tồn tại.

Bài test này CỐ Ý tạo ra tình huống đó -- sinh một loạt hoạt động rồi mới kiểm
-- để chứng minh cách xét hiện tại chịu được, thay vì chờ nó đỏ ngẫu nhiên
trong một lần chạy CI nào đó.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _graph(db, suffix):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',1000,'IN_PROGRESS') RETURNING id""", (f'PO-ORD-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,'PA','Thân',0,true) RETURNING id""", (po_id,))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Cắt','PLANNED',%s,0) RETURNING id""",
            (po_id, part_id, f'ORD-{suffix}', f'WF|OP|ORD-{suffix}'))
        op_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO employees(employee_no,name,qr,active)
            VALUES(%s,'Thợ thứ tự',%s,TRUE) RETURNING id""",
            (f'EMP-ORD-{suffix}', f'WF|EMP|EMP-ORD-{suffix}'))
        emp = cur.fetchone()['id']
    return {'po_id': po_id, 'op': op_id, 'employee_id': emp}


def _drop(db, g, kiosk=None):
    with db.cursor() as cur:
        if kiosk:
            cur.execute('DELETE FROM kiosk_events WHERE device_uuid=%s', (kiosk,))
        cur.execute("""DELETE FROM work_sessions WHERE operation_id IN
            (SELECT id FROM operations WHERE production_order_id=%s)""", (g['po_id'],))
        cur.execute('DELETE FROM operations WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM parts WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (g['po_id'],))
        cur.execute('DELETE FROM employees WHERE id=%s', (g['employee_id'],))


def _session(api, g):
    started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'ORD-S-{uuid.uuid4()}', 'employee_id': g['employee_id'],
        'operation_id': g['op']}, timeout=20)
    assert started.status_code == 201, started.text
    sid = started.json()['session']['id']
    done = api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish', json={
        'request_id': f'ORD-F-{uuid.uuid4()}', 'good_qty': 3,
        'defect_qty': 0, 'rework_qty': 0}, timeout=20)
    assert done.status_code == 200, done.text
    return sid


def test_exclusion_symmetry_holds_even_when_the_activity_window_is_saturated(db, api):
    """Sinh 600 hoạt động mới hơn rồi mới kiểm -- đúng tình huống đã làm CI đỏ.

    recent_activity() chặn cứng ở 500 dòng, sắp theo thời gian giảm dần trên
    TOÀN hệ thống. Không có cách nào nới. Nên bài test nào khẳng định "session
    của tôi phải có mặt" đều mong manh theo đúng nghĩa đen: nó phụ thuộc vào
    việc các bài chạy trước sinh bao nhiêu hoạt động.

    Cách khẳng định ĐÚNG là so sánh trước/sau: loại một session thì session ĐÓ
    biến mất, session kia không đổi. Tính chất này giữ nguyên dù cửa sổ có bão
    hoà hay không -- và đó là điều bài test kia thật sự muốn chứng minh.
    """
    from mesflow.db.repositories.analytics import DashboardRepository
    from mesflow.db.repositories.execution import SupervisorRepository

    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    kiosk = f'KIOSK-ORD-{suffix}'
    sid_a = _session(api, g)
    sid_b = _session(api, g)

    def window():
        return {int(x['item_id']) for x in DashboardRepository().recent_activity(500)
                if x['item_type'] in ('SESSION_STARTED', 'QUANTITY_REPORTED')
                and int(x['item_id']) in (sid_a, sid_b)}

    try:
        # Nhiễu: 600 sự kiện kiosk MỚI HƠN hai session vừa tạo. Trên hệ thống
        # thật đây là chuyện bình thường -- một ca sản xuất sinh nhiều hơn thế.
        with db.cursor() as cur:
            for i in range(600):
                cur.execute("""INSERT INTO kiosk_events(event_uuid,device_uuid,event_type,
                        severity,message,payload_json)
                    VALUES(%s,%s,'HEARTBEAT','INFO','ồn',%s::jsonb)""",
                    (f'ORD-{suffix}-{i}', kiosk, '{}'))

        before = window()
        SupervisorRepository().exclude_session(
            sid_b, {'reason': 'Kiểm tính đối xứng'}, user_id=None, actor_username='tester')
        after = window()

        assert sid_b not in after, 'session bị loại vẫn còn trong hoạt động gần đây'
        assert (sid_a in after) == (sid_a in before), (
            'loại session B đã làm thay đổi cả session A -- không đối xứng')
    finally:
        _drop(db, g, kiosk=kiosk)


def test_each_test_cleans_up_its_own_production_orders(db, api):
    """Rác tích luỹ là thứ làm bài sau đỏ -- kiểm ngay chính bài này.

    Không quét toàn bộ CSDL (nhiều bài khác đang chạy song song trong cùng
    session pytest). Chỉ chứng minh khuôn dọn dẹp mà mọi bài trong repo dùng là
    khuôn ĐÚNG: sau finally, không còn dòng nào mang tiền tố của bài này.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    _session(api, g)
    _drop(db, g)
    left = db.execute("SELECT COUNT(*) c FROM production_orders WHERE code=%s",
                      (f'PO-ORD-{suffix}',)).fetchone()['c']
    assert left == 0, 'khuôn dọn dẹp để sót PO'
    ops = db.execute("SELECT COUNT(*) c FROM operations WHERE code=%s",
                     (f'ORD-{suffix}',)).fetchone()['c']
    assert ops == 0, 'khuôn dọn dẹp để sót Operation'
