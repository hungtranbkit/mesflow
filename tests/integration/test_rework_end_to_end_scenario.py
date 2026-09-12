"""Luồng sửa hàng đầy đủ, chạy đúng như xưởng chạy.

Bảy bất biến ở PHẦN VI của master queue được kiểm ở đây bằng MỘT kịch bản liên
tục, thay vì bảy bài rời rạc. Lý do: các lỗi đã gặp đều nằm ở CHỖ NỐI giữa các
bước -- credit về nhầm OP, phế tự sinh, OP phụ làm bẩn rollup, hoàn thành tính
sai. Bài test rời từng bước không đi qua những chỗ nối đó.

Kịch bản chuẩn:

    Mục tiêu 100
      -> đạt 92 + chờ sửa 8
      -> sửa được 6 + phế 2
      -> OP nguồn: đạt 98, chờ sửa 0, phế 2 -- VẪN IN_PROGRESS
      -> làm thêm 2 đạt
      -> COMPLETED
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

TARGET = 100


def _graph(db, suffix):
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',%s,'IN_PROGRESS') RETURNING id""", (f'PO-E2E-{suffix}', TARGET))
        po_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,'PA','Thân',0,true) RETURNING id""", (po_id,))
        part_id = cur.fetchone()['id']
        # Mục tiêu của Operation lấy từ production_orders.planned_quantity --
        # operations không có cột target riêng.
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Cắt phôi','PLANNED',%s,0) RETURNING id""",
            (po_id, part_id, f'E2E-{suffix}-OP1', f'WF|OP|E2E-{suffix}-OP1'))
        op_id = cur.fetchone()['id']
        # OP thứ hai cùng Part: dùng để chứng minh credit KHÔNG lan sang OP khác.
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Chấn','PLANNED',%s,1) RETURNING id""",
            (po_id, part_id, f'E2E-{suffix}-OP2', f'WF|OP|E2E-{suffix}-OP2'))
        other_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO employees(employee_no,name,qr,active)
            VALUES(%s,'Thợ kịch bản',%s,TRUE) RETURNING id""",
            (f'EMP-E2E-{suffix}', f'WF|EMP|EMP-E2E-{suffix}'))
        emp = cur.fetchone()['id']
        cur.execute("""INSERT INTO employees(employee_no,name,qr,active)
            VALUES(%s,'Thợ sửa hàng',%s,TRUE) RETURNING id""",
            (f'EMP-FIX-{suffix}', f'WF|EMP|EMP-FIX-{suffix}'))
        fixer = cur.fetchone()['id']
    return {'po_id': po_id, 'part_id': part_id, 'op': op_id, 'other': other_id,
            'employee_id': emp, 'fixer_id': fixer}


def _drop(db, g):
    with db.cursor() as cur:
        cur.execute("""DELETE FROM rework_ledger WHERE source_operation_id IN
            (SELECT id FROM operations WHERE production_order_id=%s)""", (g['po_id'],))
        cur.execute("""DELETE FROM operation_input_consumptions WHERE session_id IN
            (SELECT id FROM work_sessions WHERE operation_id IN
             (SELECT id FROM operations WHERE production_order_id=%s))""", (g['po_id'],))
        cur.execute("""DELETE FROM work_sessions WHERE operation_id IN
            (SELECT id FROM operations WHERE production_order_id=%s)""", (g['po_id'],))
        cur.execute('DELETE FROM operations WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM parts WHERE production_order_id=%s', (g['po_id'],))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (g['po_id'],))
        cur.execute('DELETE FROM employees WHERE id IN (%s,%s)', (g['employee_id'], g['fixer_id']))


def _work(api, g, operation_id, good, defect, rework=None, employee=None):
    # rework_qty = số NG công nhân KHAI LÀ SỬA ĐƯỢC (0051). Mặc định khai hết,
    # vì kịch bản end-to-end này cần chúng vào được hàng chờ sửa.
    started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'E2E-S-{uuid.uuid4()}', 'employee_id': employee or g['employee_id'],
        'operation_id': operation_id}, timeout=20)
    assert started.status_code == 201, started.text
    sid = started.json()['session']['id']
    done = api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish', json={
        'request_id': f'E2E-F-{uuid.uuid4()}', 'good_qty': good,
        'defect_qty': defect, 'rework_qty': defect if rework is None else rework}, timeout=20)
    assert done.status_code == 200, done.text
    return sid


def _op(db, op_id):
    return db.execute("""SELECT code,status,done_qty,defect_qty,rework_qty,
        COALESCE(operation_type,'PRODUCTION') operation_type FROM operations WHERE id=%s""",
        (op_id,)).fetchone()


def _session(db, sid):
    return db.execute("""SELECT good_qty,defect_qty,rework_qty,repaired_qty,scrap_qty
        FROM work_sessions WHERE id=%s""", (sid,)).fetchone()


def test_full_rework_scenario_reconciles_end_to_end(db, api):
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    try:
        # --- R1 bước 1: đạt 92, chờ sửa 8 --------------------------------
        sid = _work(api, g, g['op'], good=92, defect=8)
        row = _session(db, sid)
        assert (row['good_qty'], row['defect_qty']) == (92, 8)
        assert row['rework_qty'] == 8, 'cả 8 NG được khai là sửa được'
        assert row['repaired_qty'] == 0 and row['scrap_qty'] == 0, (
            'R3: lỗi chưa xử lý KHÔNG được tự thành phế hay tự thành đã sửa')

        op = _op(db, g['op'])
        assert op['status'] != 'COMPLETED', 'R5: 92 < 100 thì chưa hoàn thành'

        # --- R1 bước 2: sửa được 6, phế 2 --------------------------------
        resolved = api.post(f"{BASE_URL}/api/rework/queue/{sid}/resolve", json={
            'request_id': f'E2E-R-{uuid.uuid4()}', 'employee_id': g['fixer_id'],
            'repaired_qty': 6, 'scrapped_qty': 2}, timeout=25)
        assert resolved.status_code == 200, resolved.text

        row = _session(db, sid)
        assert row['good_qty'] == 98, f"R1: đạt phải là 92+6=98, đang là {row['good_qty']}"
        assert row['defect_qty'] == 8, 'NG gốc không đổi -- nó là sự thật đã xảy ra'
        assert row['rework_qty'] == 8, 'khai báo gốc không đổi khi có người sửa'
        assert row['repaired_qty'] == 6 and row['scrap_qty'] == 2
        pending = row['rework_qty'] - row['repaired_qty'] - row['scrap_qty']
        assert pending == 0, f'R1: chờ sửa phải về 0, đang là {pending}'

        # --- R2: credit về ĐÚNG OP nguồn, không lan sang OP khác ----------
        assert _op(db, g['op'])['done_qty'] == 98
        other = _op(db, g['other'])
        assert other['done_qty'] == 0, (
            f"R2: OP khác cùng Part bị credit lây: {other['code']} = {other['done_qty']}")

        # --- R4: bàn SỬA HÀNG không làm bẩn rollup sản xuất ---------------
        rework_ops = db.execute("""SELECT id,code,done_qty,defect_qty,
                COALESCE(operation_type,'PRODUCTION') operation_type
            FROM operations WHERE production_order_id=%s
              AND COALESCE(operation_type,'PRODUCTION')<>'PRODUCTION'""",
            (g['po_id'],)).fetchall()
        assert rework_ops, 'phải có một OP SỬA HÀNG được tạo ra'
        for op_row in rework_ops:
            assert op_row['done_qty'] == 0 and op_row['defect_qty'] == 0, (
                f"R4: OP phụ {op_row['code']} mang sản lượng -- nó sẽ lọt vào tiến độ PO")

        # --- R6: sổ sửa hàng đủ vết ---------------------------------------
        ledger = db.execute("""SELECT source_session_id,source_operation_id,rework_session_id,
                rework_operation_id,employee_id,qty_reworked,qty_scrapped,created_at
            FROM rework_ledger WHERE source_session_id=%s""", (sid,)).fetchall()
        assert len(ledger) == 1, ledger
        entry = ledger[0]
        assert entry['source_session_id'] == sid
        assert entry['source_operation_id'] == g['op']
        assert entry['rework_session_id'] and entry['rework_operation_id']
        assert entry['employee_id'] == g['fixer_id'], 'phải ghi AI đã sửa'
        assert (entry['qty_reworked'], entry['qty_scrapped']) == (6, 2)
        assert entry['created_at'] is not None

        # --- R5: vẫn IN_PROGRESS ở 98/100 ---------------------------------
        op = _op(db, g['op'])
        assert op['status'] != 'COMPLETED', (
            f"R5: 98 < 100 mà đã {op['status']} -- hoàn thành tính sai")

        # --- R1 bước cuối: thêm 2 đạt -> COMPLETED ------------------------
        _work(api, g, g['op'], good=2, defect=0)
        op = _op(db, g['op'])
        assert op['done_qty'] == 100
        assert op['status'] == 'COMPLETED', (
            f"R5: đủ 100/100 mà vẫn {op['status']}")
    finally:
        _drop(db, g)


def test_overproduction_is_allowed_and_still_completes(db, api):
    """R5: sản xuất vượt không được coi là lỗi."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    try:
        _work(api, g, g['op'], good=TARGET + 15, defect=0)
        op = _op(db, g['op'])
        assert op['done_qty'] == TARGET + 15
        assert op['status'] == 'COMPLETED'
    finally:
        _drop(db, g)


def test_repairing_more_than_pending_is_refused(db, api):
    """Không được sửa nhiều hơn số đang chờ -- đó là cách credit khống lọt vào."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    try:
        sid = _work(api, g, g['op'], good=90, defect=5)
        over = api.post(f'{BASE_URL}/api/rework/queue/{sid}/resolve', json={
            'request_id': f'E2E-OV-{uuid.uuid4()}', 'employee_id': g['fixer_id'],
            'repaired_qty': 6, 'scrapped_qty': 0}, timeout=25)
        assert over.status_code >= 400, over.text
        assert _session(db, sid)['good_qty'] == 90, 'lệnh bị từ chối không được ghi gì'
    finally:
        _drop(db, g)


def test_resolving_twice_does_not_double_credit(db, api):
    """R2/R6: cùng một sản phẩm vật lý không được credit hai lần."""
    suffix = uuid.uuid4().hex[:8].upper()
    g = _graph(db, suffix)
    try:
        sid = _work(api, g, g['op'], good=90, defect=10)
        payload = {'request_id': f'E2E-D-{uuid.uuid4()}', 'employee_id': g['fixer_id'],
                   'repaired_qty': 4, 'scrapped_qty': 0}
        first = api.post(f'{BASE_URL}/api/rework/queue/{sid}/resolve', json=payload, timeout=25)
        assert first.status_code == 200, first.text
        # Cùng request_id -> replay, phải là no-op.
        second = api.post(f'{BASE_URL}/api/rework/queue/{sid}/resolve', json=payload, timeout=25)
        assert second.status_code == 200, second.text
        row = _session(db, sid)
        assert row['good_qty'] == 94, f"credit hai lần: {row['good_qty']}"
        assert row['repaired_qty'] == 4
        count = db.execute('SELECT COUNT(*) c FROM rework_ledger WHERE source_session_id=%s',
                           (sid,)).fetchone()['c']
        assert count == 1, f'sổ ghi {count} dòng cho một lần xử lý'
    finally:
        _drop(db, g)
