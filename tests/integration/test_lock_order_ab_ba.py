"""Ba đường ghi ngoài execution.py phải khoá PO trước, như mọi đường khác.

Bất biến (xem docstring của lock_production_order_for_operation_first): khoá
FOR UPDATE trên dòng production_orders cha phải là khoá dòng ĐẦU TIÊN mà bất
kỳ transaction ghi nào lấy. Một transaction luôn lấy khoá cha chung trước mọi
khoá con thì không thể nằm trong vòng chờ qua nó -- đồ thị chờ sụp thành một
hàng đợi.

Audit kiến trúc 2026-09-09 tìm ra ba chỗ đi ngược chiều, tất cả đều NGOÀI
execution.py nên đợt sửa deadlock 2026-08-26 không chạm tới:

  ReworkQueueRepository.resolve()   khoá work_sessions + operations rồi mới PO
  OperationRepository.update()      khoá operations (UPDATE) rồi mới PO
  cancel_operation                  khoá operations (FOR UPDATE) rồi mới PO

SỨC MẠNH CỦA TỪNG BÀI TEST -- nói thẳng, vì dễ tưởng nhầm:

- test_po_lock_is_taken_first_on_every_repaired_path là lưới THẬT. Nó đọc
  nguồn và bắt đúng thứ đã gây ra bug: thiếu lời gọi khoá-PO-trước. Đã kiểm
  bằng cách gỡ tạm fix ở rework.py -- bài này đỏ ngay.

- Ba bài chạy song song bên dưới chỉ là SMOKE. Tôi đã gỡ fix rồi chạy lại ở 8
  vòng và 40 vòng: cả ba VẪN XANH. Hai luồng đi qua HTTP không giao nhau đủ
  khít để dựng lại vòng chờ. Chúng bắt được lỗi thô (một đường ghi vỡ hẳn dưới
  tranh chấp) chứ KHÔNG chứng minh được là hết deadlock -- đừng đọc chúng như
  vậy.

Bằng chứng cho bản sửa này là bất biến thứ tự khoá cộng với assertion nguồn,
không phải một lần tái hiện deadlock. Muốn tái hiện thật thì cần điều khiển
lịch trình ở tầng DB (hai session psycopg giữ khoá thủ công), đắt hơn nhiều so
với giá trị nó thêm khi bất biến đã rõ ràng đến vậy.
"""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres

ROUNDS = 8


def _deadlocks(results):
    """Số lần thua vì deadlock -- thứ duy nhất bài test này cấm.

    Xung đột nghiệp vụ (409) là hợp lệ và không tính: hai người cùng sửa một
    session thì một người phải thua, miễn là thua có lý do chứ không phải vì
    PostgreSQL phải huỷ transaction để gỡ vòng chờ.
    """
    hits = []
    for r in results:
        text = (r if isinstance(r, str) else f'{r.status_code} {r.text}').lower()
        if 'deadlock' in text:
            hits.append(text[:200])
    return hits


def _closed_session(api, graph, good=5, defect=4):
    started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'LK-S-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'operation_id': graph['operation_id'], 'station_id': graph['station_id']}, timeout=20)
    assert started.status_code == 201, started.text
    sid = started.json()['session']['id']
    done = api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish', json={
        'request_id': f'LK-F-{uuid.uuid4()}', 'good_qty': good, 'defect_qty': defect,
        'rework_qty': 0}, timeout=20)
    assert done.status_code == 200, done.text
    return sid


def _run_pair(fn_a, fn_b):
    """Chạy hai đường ghi cùng lúc, nhiều vòng, gom mọi kết quả."""
    out = []
    for _ in range(ROUNDS):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(fn_a), pool.submit(fn_b)]
            for f in futures:
                try:
                    out.append(f.result())
                except Exception as exc:            # noqa: BLE001 - muốn thấy mọi lỗi
                    out.append(f'EXC {exc}')
    return out


def test_rework_resolve_vs_adjust_never_deadlocks(api, db, seeded_factory):
    """resolve() và adjust() cùng chạm một session -- cặp AB/BA rõ nhất."""
    graph = seeded_factory
    session_id = _closed_session(api, graph, good=5, defect=4)

    def resolve():
        return api.post(f'{BASE_URL}/api/rework/queue/{session_id}/resolve', json={
            'request_id': f'LK-R-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
            'repaired_qty': 1}, timeout=25)

    def adjust():
        return api.post(f'{BASE_URL}/api/supervisor/sessions/{session_id}/adjust', json={
            'request_id': f'LK-A-{uuid.uuid4()}', 'good_qty': 5, 'defect_qty': 4,
            'rework_qty': 4, 'reason': 'Đếm lại'}, timeout=25)

    hits = _deadlocks(_run_pair(resolve, adjust))
    assert not hits, f'deadlock ở resolve/adjust: {hits[:2]}'


def test_operation_update_vs_session_write_never_deadlocks(api, db, seeded_factory):
    """Sửa cấu hình OP trong khi công nhân đang ghi session trên chính OP đó."""
    graph = seeded_factory

    def edit_operation():
        return api.patch(f"{BASE_URL}/api/operations/{graph['operation_id']}",
                         json={'lag_minutes': 0, 'dependency_type': 'FS'}, timeout=25)

    def work():
        started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
            'request_id': f'LK-S2-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
            'operation_id': graph['operation_id'], 'station_id': graph['station_id']}, timeout=25)
        if started.status_code != 201:
            return started
        sid = started.json()['session']['id']
        return api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish', json={
            'request_id': f'LK-F2-{uuid.uuid4()}', 'good_qty': 1, 'defect_qty': 0,
            'rework_qty': 0}, timeout=25)

    hits = _deadlocks(_run_pair(edit_operation, work))
    assert not hits, f'deadlock ở update/session: {hits[:2]}'


def test_cancel_operation_vs_session_write_never_deadlocks(api, db, seeded_factory):
    """Cancel một OP trong khi có session đang chạy trên PO đó."""
    graph = seeded_factory
    suffix = graph['suffix']
    with db.cursor() as cur:
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'OP để cancel','PLANNED',%s,9) RETURNING id""",
            (graph['po_id'], graph['part_id'], f'LK-CANCEL-{suffix}', f'WF|OP|LK-CANCEL-{suffix}'))
        spare_id = cur.fetchone()['id']
    try:
        def cancel():
            # Chỉ vòng đầu đổi được trạng thái; các vòng sau trả 409 -- vẫn đủ
            # để tranh khoá, và 409 không tính là deadlock.
            return api.post(f'{BASE_URL}/api/operations/{spare_id}/cancel', json={}, timeout=25)

        def work():
            started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
                'request_id': f'LK-S3-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
                'operation_id': graph['operation_id'], 'station_id': graph['station_id']}, timeout=25)
            if started.status_code != 201:
                return started
            sid = started.json()['session']['id']
            return api.post(f'{BASE_URL}/api/work-sessions/{sid}/finish', json={
                'request_id': f'LK-F3-{uuid.uuid4()}', 'good_qty': 1, 'defect_qty': 0,
                'rework_qty': 0}, timeout=25)

        hits = _deadlocks(_run_pair(cancel, work))
        assert not hits, f'deadlock ở cancel/session: {hits[:2]}'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM work_sessions WHERE operation_id=%s', (spare_id,))
            cur.execute('DELETE FROM operations WHERE id=%s', (spare_id,))


def test_po_lock_is_taken_first_on_every_repaired_path(db):
    """Chốt ở mức nguồn: ba đường này phải gọi helper khoá-PO-trước.

    Một bài test đồng thời có thể xanh nhờ may -- luồng chạy không giao nhau ở
    đúng khe hở. Assert này thì không: nó bắt đúng thứ đã gây ra bug, là việc
    thiếu lời gọi.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]

    rework = (root / 'app/mesflow/db/repositories/rework.py').read_text(encoding='utf-8')
    assert 'lock_production_order_first_for_session(cur, source_session_id)' in rework
    # FOR UPDATE trần trên một join khoá cả ba bảng, PO là bảng cuối.
    assert 'WHERE ws.id=%s FOR UPDATE OF ws' in rework

    repo = (root / 'app/mesflow/db/repositories/master_data.py').read_text(encoding='utf-8')
    assert 'lock_production_order_for_operation_first(cur,int(entity_id))' in repo

    web = (root / 'app/mesflow/web/master_data.py').read_text(encoding='utf-8')
    assert 'lock_production_order_for_operation_first(cur,operation_id)' in web
