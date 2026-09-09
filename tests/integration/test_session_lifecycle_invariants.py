"""Bất biến vòng đời Session: dòng vật tư và số lượng phải đi theo session.

Ba lỗ hổng cùng một họ, tìm ra trong audit kiến trúc 2026-09-09. Điểm chung:
edit_session() xử lý đúng, còn hai đường ghi CHUYÊN BIỆT bên cạnh nó thì không
-- vì chúng ra đời sau và không ai nối lại phần dòng vật tư.

BẤT BIẾN của operation_input_consumptions, phát biểu rõ ở đây vì trước giờ nó
chỉ nằm ngầm trong code:

  Một dòng ledger là phần đầu vào mà MỘT session đang giữ, rút từ OP nguồn của
  Operation mà session đó thuộc về. Vậy nên:

    (1) target_operation_id LUÔN bằng operation_id hiện tại của session;
    (2) dòng chỉ tồn tại khi session còn tính vào báo cáo (CLOSED và không bị
        loại) -- session không đóng góp gì thì không được giữ hàng của ai;
    (3) source_operation_id luôn là input_source_operation_id đang cấu hình
        của Operation đích.

  Tổng đã phân bổ trên một OP nguồn KHÔNG nối sang work_sessions khi cộng (xem
  _validate_and_upsert_input_consumption). Đó là lý do vi phạm (2) không lộ ra
  ở bất kỳ báo cáo nào: hàng bị giữ im lặng.

A1  exclude_session() không nhả ledger  -> session bị loại vẫn chiếm sản lượng
    của OP nguồn, chặn OP đích khác lấy đúng số hàng đó.
A1  transfer_operation() không đổi ledger -> sản lượng đếm cho OP mới nhưng
    nguyên liệu vẫn trừ của OP cũ.
A2  transfer_operation() cho phép chuyển session có sản lượng sang OP phụ ->
    số lượng biến mất khỏi tiến độ PO, không dấu vết.
A3  adjust()/edit_session() không kiểm rework+scrap <= defect -> vi phạm CHECK
    ck_work_sessions_rework_scrap_le_defect, người dùng nhận HTTP 500.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _flow_graph(db, api, suffix):
    """PO có OP nguồn -> hai OP đích cùng ăn từ nguồn đó.

    Hai đích là điểm mấu chốt: chỉ khi có người thứ hai muốn lấy hàng thì việc
    session bị loại vẫn giữ hàng mới lộ ra.
    """
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',100,'IN_PROGRESS') RETURNING id""", (f'PO-INV-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,'PA','Thân',0,true) RETURNING id""", (po_id,))
        part_id = cur.fetchone()['id']

        def mkop(code, name, order, **kw):
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order,
                    operation_type,parent_operation_id,input_flow_enabled,input_source_operation_id,input_source_kind)
                VALUES(%s,%s,%s,%s,'PLANNED',%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (po_id, part_id, code, name, f'WF|OP|{code}', order,
                 kw.get('type', 'PRODUCTION'), kw.get('parent'), kw.get('flow', False),
                 kw.get('source'), kw.get('kind', 'GOOD')))
            return cur.fetchone()['id']

        src = mkop(f'INV-{suffix}-SRC', 'OP nguồn', 0)
        dst_a = mkop(f'INV-{suffix}-A', 'OP đích A', 1, flow=True, source=src)
        dst_b = mkop(f'INV-{suffix}-B', 'OP đích B', 2, flow=True, source=src)
        setup = mkop(f'INV-{suffix}-SU', 'Setup nguồn', 3, type='SETUP', parent=src)

        cur.execute("""INSERT INTO employees(employee_no,name,qr,active)
            VALUES(%s,'Thợ kiểm bất biến',%s,TRUE) RETURNING id""",
            (f'EMP-INV-{suffix}', f'WF|EMP|EMP-INV-{suffix}'))
        emp = cur.fetchone()['id']
        cur.execute("""INSERT INTO stations(code,name,active) VALUES(%s,'Trạm',TRUE)
            ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name RETURNING id""", (f'ST-INV-{suffix}',))
        station = cur.fetchone()['id']
    return {'po_id': po_id, 'part_id': part_id, 'src': src, 'dst_a': dst_a,
            'dst_b': dst_b, 'setup': setup, 'employee_id': emp, 'station_id': station}


def _work(api, g, operation_id, good=0, defect=0, rework=0):
    started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'INV-S-{uuid.uuid4()}', 'employee_id': g['employee_id'],
        'operation_id': operation_id, 'station_id': g['station_id']}, timeout=20)
    assert started.status_code == 201, started.text
    sid = started.json()['session']['id']
    done = api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish', json={
        'request_id': f'INV-F-{uuid.uuid4()}', 'good_qty': good,
        'defect_qty': defect, 'rework_qty': rework}, timeout=20)
    assert done.status_code == 200, done.text
    return sid


def _ledger(db, session_id):
    return db.execute("""SELECT source_operation_id,target_operation_id,
        good_qty_consumed,defect_qty_consumed FROM operation_input_consumptions
        WHERE session_id=%s""", (session_id,)).fetchall()


def _drop(db, g):
    with db.cursor() as cur:
        cur.execute("""DELETE FROM operation_input_consumptions WHERE session_id IN
            (SELECT id FROM work_sessions WHERE operation_id IN
             (SELECT id FROM operations WHERE production_order_id=%s))""", (g['po_id'],))
        cur.execute("""DELETE FROM work_sessions WHERE operation_id IN
            (SELECT id FROM operations WHERE production_order_id=%s)""", (g['po_id'],))
        cur.execute('DELETE FROM operations WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM parts WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (g['po_id'],))
        cur.execute('DELETE FROM employees WHERE id=%s', (g['employee_id'],))


# ------------------------------------------------------------------ A1


def test_excluding_a_session_releases_the_input_it_was_holding(db, api):
    """Session bị loại khỏi báo cáo thì phải nhả hàng cho người khác lấy."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _flow_graph(db, api, suffix)
    try:
        _work(api, g, g['src'], good=10)                 # nguồn làm ra 10
        sid_a = _work(api, g, g['dst_a'], good=10)       # A lấy hết 10
        assert len(_ledger(db, sid_a)) == 1

        # B chưa lấy được gì -- đúng, vì A đang giữ.
        blocked = api.post(f'{BASE_URL}/api/work-sessions/start', json={
            'request_id': f'INV-B1-{uuid.uuid4()}', 'employee_id': g['employee_id'],
            'operation_id': g['dst_b'], 'station_id': g['station_id']}, timeout=20)
        if blocked.status_code == 201:
            bid = blocked.json()['session']['id']
            over = api.post(f'{BASE_URL}/api/work-sessions/{bid}/finish', json={
                'request_id': f'INV-B2-{uuid.uuid4()}', 'good_qty': 10,
                'defect_qty': 0, 'rework_qty': 0}, timeout=20)
            assert over.status_code >= 400, 'B không được lấy phần A đang giữ'

        excluded = api.post(f'{BASE_URL}/api/supervisor/sessions/{sid_a}/exclude', json={
            'reason': 'Ghi nhầm ca'}, timeout=20)
        assert excluded.status_code == 200, excluded.text
        assert _ledger(db, sid_a) == [], 'session bị loại vẫn còn giữ dòng vật tư'
    finally:
        _drop(db, g)


def test_restoring_a_session_takes_the_input_back(db, api):
    """Khôi phục thì cấp lại -- và nếu hết hàng thì phải từ chối rõ ràng."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _flow_graph(db, api, suffix)
    try:
        _work(api, g, g['src'], good=10)
        sid_a = _work(api, g, g['dst_a'], good=10)
        api.post(f'{BASE_URL}/api/supervisor/sessions/{sid_a}/exclude',
                 json={'reason': 'Ghi nhầm ca'}, timeout=20)
        assert _ledger(db, sid_a) == []

        restored = api.post(f'{BASE_URL}/api/supervisor/sessions/{sid_a}/restore',
                            json={'reason': 'Xác nhận lại là đúng'}, timeout=20)
        assert restored.status_code == 200, restored.text
        rows = _ledger(db, sid_a)
        assert len(rows) == 1, 'khôi phục phải cấp lại phần đầu vào đã nhả'
        assert rows[0]['target_operation_id'] == g['dst_a']
        assert rows[0]['source_operation_id'] == g['src']
    finally:
        _drop(db, g)


def test_transfer_moves_the_input_ledger_to_the_new_operation(db, api):
    """Sản lượng sang OP mới thì nguyên liệu cũng phải sang theo."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _flow_graph(db, api, suffix)
    try:
        _work(api, g, g['src'], good=20)
        sid = _work(api, g, g['dst_a'], good=5)
        before = _ledger(db, sid)
        assert before[0]['target_operation_id'] == g['dst_a']

        moved = api.post(f'{BASE_URL}/api/supervisor/sessions/{sid}/transfer-operation', json={
            'request_id': f'INV-T-{uuid.uuid4()}', 'operation_id': g['dst_b'],
            'reason': 'Ghi nhầm Operation', 'confirm_cross_part': True}, timeout=20)
        assert moved.status_code == 200, moved.text

        after = _ledger(db, sid)
        assert len(after) == 1, 'chuyển Operation không được làm mất dòng vật tư'
        assert after[0]['target_operation_id'] == g['dst_b'], (
            'dòng vật tư vẫn trỏ về Operation cũ sau khi chuyển')
        assert after[0]['source_operation_id'] == g['src']
    finally:
        _drop(db, g)


# ------------------------------------------------------------------ A2


def test_cannot_transfer_a_quantity_bearing_session_into_a_support_op(db, api):
    """OP phụ không tính vào sản lượng -- chuyển vào đó là làm mất số."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _flow_graph(db, api, suffix)
    try:
        sid = _work(api, g, g['src'], good=7, defect=2, rework=1)
        blocked = api.post(f'{BASE_URL}/api/supervisor/sessions/{sid}/transfer-operation', json={
            'request_id': f'INV-T2-{uuid.uuid4()}', 'operation_id': g['setup'],
            'reason': 'Thử chuyển sang SETUP', 'confirm_cross_part': True}, timeout=20)
        assert blocked.status_code >= 400, blocked.text
        assert 'OP phụ' in blocked.json().get('message', '')

        still = db.execute('SELECT operation_id FROM work_sessions WHERE id=%s',
                           (sid,)).fetchone()
        assert still['operation_id'] == g['src'], 'session không được chuyển đi'
    finally:
        _drop(db, g)


def test_a_session_with_no_quantity_may_still_move_to_a_support_op(db, api):
    """Chặn đúng cái cần chặn: session rỗng thì không làm mất số nào cả."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _flow_graph(db, api, suffix)
    try:
        sid = _work(api, g, g['src'], good=0, defect=0, rework=0)
        moved = api.post(f'{BASE_URL}/api/supervisor/sessions/{sid}/transfer-operation', json={
            'request_id': f'INV-T3-{uuid.uuid4()}', 'operation_id': g['setup'],
            'reason': 'Ghi nhầm, thực ra là setup máy', 'confirm_cross_part': True}, timeout=20)
        assert moved.status_code == 200, moved.text
    finally:
        _drop(db, g)


# ------------------------------------------------------------------ A3


def test_lowering_defect_below_recorded_scrap_is_refused_not_a_500(db, api):
    """CHECK của CSDL phải được chặn trước bằng câu tiếng Việt, không phải 500."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _flow_graph(db, api, suffix)
    try:
        sid = _work(api, g, g['src'], good=10, defect=6, rework=0)
        resolved = api.post(f'{BASE_URL}/api/rework/queue/{sid}/resolve', json={
            'request_id': f'INV-R-{uuid.uuid4()}', 'employee_id': g['employee_id'],
            'repaired_qty': 1, 'scrapped_qty': 4}, timeout=25)
        assert resolved.status_code == 200, resolved.text
        row = db.execute('SELECT rework_qty,scrap_qty,defect_qty FROM work_sessions WHERE id=%s',
                         (sid,)).fetchone()
        assert row['scrap_qty'] == 4 and row['rework_qty'] == 1

        # defect=2 < scrap 4 + rework 1: CSDL sẽ từ chối. Người dùng phải nhận
        # lỗi nghiệp vụ, không phải lỗi PostgreSQL.
        bad = api.post(f'{BASE_URL}/api/supervisor/sessions/{sid}/adjust', json={
            'request_id': f'INV-A-{uuid.uuid4()}', 'good_qty': 10, 'defect_qty': 2,
            'rework_qty': 1, 'reason': 'Đếm lại'}, timeout=20)
        assert 400 <= bad.status_code < 500, f'phải là lỗi nghiệp vụ, nhận {bad.status_code}: {bad.text[:200]}'
        message = bad.json().get('message', '')
        assert 'phế' in message or 'NG' in message, message

        unchanged = db.execute('SELECT defect_qty FROM work_sessions WHERE id=%s',
                               (sid,)).fetchone()
        assert unchanged['defect_qty'] == 6, 'lệnh bị từ chối không được ghi gì'
    finally:
        _drop(db, g)


def test_adjust_still_works_when_the_new_shape_is_valid(db, api):
    """Guard không được chặn nhầm đường hợp lệ."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _flow_graph(db, api, suffix)
    try:
        sid = _work(api, g, g['src'], good=10, defect=6, rework=0)
        api.post(f'{BASE_URL}/api/rework/queue/{sid}/resolve', json={
            'request_id': f'INV-R2-{uuid.uuid4()}', 'employee_id': g['employee_id'],
            'repaired_qty': 1, 'scrapped_qty': 4}, timeout=25)
        ok = api.post(f'{BASE_URL}/api/supervisor/sessions/{sid}/adjust', json={
            'request_id': f'INV-A2-{uuid.uuid4()}', 'good_qty': 12, 'defect_qty': 8,
            'rework_qty': 1, 'reason': 'Đếm lại, NG nhiều hơn'}, timeout=20)
        assert ok.status_code == 200, ok.text
        row = db.execute('SELECT defect_qty,rework_qty,scrap_qty FROM work_sessions WHERE id=%s',
                         (sid,)).fetchone()
        assert (row['defect_qty'], row['rework_qty'], row['scrap_qty']) == (8, 1, 4)
    finally:
        _drop(db, g)
