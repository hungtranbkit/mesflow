"""Sửa số liệu Session không được phép làm hàng đã sửa quay lại hàng chờ.

Lỗ hổng (audit kiến trúc 2026-09-09, P1): ReworkQueueRepository.resolve() tính
"còn chờ sửa" thuần từ dòng work_sessions — defect - rework - scrap — trong khi
SupervisorRepository.adjust()/edit_session() ghi ĐÈ TUYỆT ĐỐI lên rework_qty và
không hề đọc rework_ledger.

Kịch bản có thật: session đóng với good=10, defect=5. Hàng chờ sửa resolve 2
sản phẩm → good=12, rework=2, ledger ghi 2. Sau đó quản đốc sửa lại số liệu
"như đáng lẽ công nhân phải nhập": good=10, defect=5, rework=0. Ràng buộc
rework<=defect vẫn thoả nên lệnh đi qua. Giờ pending = 5-0-0 = 5: đúng hai sản
phẩm đã sửa quay lại hàng chờ, resolve lần nữa là good được cộng lần hai —
operations.done_qty đếm hai lần cùng một sản phẩm vật lý, và Operation có thể
lên COMPLETED bằng hàng không tồn tại.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _closed_session(api, graph, good, defect, repairable=None):
    # rework_qty = số NG công nhân KHAI LÀ SỬA ĐƯỢC (0051). Mặc định khai hết,
    # vì mọi bài dưới đây đều cần số NG đó vào được hàng chờ sửa để resolve.
    started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'RW-S-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'operation_id': graph['operation_id'], 'station_id': graph['station_id']}, timeout=15)
    assert started.status_code == 201, started.text
    session_id = started.json()['session']['id']
    finished = api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'RW-F-{uuid.uuid4()}', 'good_qty': good, 'defect_qty': defect,
        'rework_qty': defect if repairable is None else repairable}, timeout=15)
    assert finished.status_code == 200, finished.text
    return session_id


def _resolve(api, session_id, graph, repaired=0, scrapped=0):
    return api.post(f'{BASE_URL}/api/rework/queue/{session_id}/resolve', json={
        'request_id': f'RW-R-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'repaired_qty': repaired, 'scrapped_qty': scrapped}, timeout=20)


def test_adjust_cannot_erase_repairs_already_recorded_in_the_ledger(api, db, seeded_factory):
    graph = seeded_factory
    session_id = _closed_session(api, graph, good=10, defect=5)
    assert _resolve(api, session_id, graph, repaired=2).status_code == 200

    row = db.execute('SELECT good_qty,rework_qty,repaired_qty FROM work_sessions WHERE id=%s',
                     (session_id,)).fetchone()
    # rework_qty giữ nguyên khai báo (5); phần đã sửa nằm ở repaired_qty (0051).
    assert (row['good_qty'], row['rework_qty'], row['repaired_qty']) == (12, 5, 2)
    ledger = db.execute('SELECT COALESCE(SUM(qty_reworked),0) n FROM rework_ledger WHERE source_session_id=%s',
                        (session_id,)).fetchone()['n']
    assert ledger == 2

    # Quản đốc sửa lại "như đáng lẽ công nhân nhập": rework về 0.
    corrected = api.post(f'{BASE_URL}/api/supervisor/sessions/{session_id}/adjust', json={
        'request_id': f'RW-ADJ-{uuid.uuid4()}', 'good_qty': 10, 'defect_qty': 5,
        'rework_qty': 0, 'reason': 'Nhập lại theo phiếu'}, timeout=20)
    assert corrected.status_code == 409, corrected.text
    assert '2' in corrected.json().get('message', ''), corrected.text

    # Không có gì bị ghi: dòng session giữ nguyên credit.
    after = db.execute('SELECT good_qty,rework_qty,repaired_qty FROM work_sessions WHERE id=%s',
                       (session_id,)).fetchone()
    assert (after['good_qty'], after['rework_qty'], after['repaired_qty']) == (12, 5, 2)


def test_adjust_still_allows_a_correction_that_keeps_the_ledger_whole(api, db, seeded_factory):
    """Guard chỉ chặn phần đã ghi sổ, không được chặn việc sửa số liệu bình thường."""
    graph = seeded_factory
    session_id = _closed_session(api, graph, good=10, defect=5)
    assert _resolve(api, session_id, graph, repaired=2).status_code == 200

    ok = api.post(f'{BASE_URL}/api/supervisor/sessions/{session_id}/adjust', json={
        'request_id': f'RW-ADJ-{uuid.uuid4()}', 'good_qty': 20, 'defect_qty': 6,
        'rework_qty': 2, 'reason': 'Đếm lại thùng'}, timeout=20)
    assert ok.status_code == 200, ok.text
    row = db.execute('SELECT good_qty,defect_qty,rework_qty,repaired_qty FROM work_sessions WHERE id=%s',
                     (session_id,)).fetchone()
    # Hạ khai báo sửa được xuống đúng bằng phần đã sửa (2) vẫn hợp lệ.
    assert (row['good_qty'], row['defect_qty'], row['rework_qty'], row['repaired_qty']) == (20, 6, 2, 2)


def test_resolve_reads_the_ledger_floor_so_repairs_cannot_be_credited_twice(api, db, seeded_factory):
    """Chốt chặn thứ hai, ở chiều đọc.

    Ngay cả khi dòng session bị đưa về trạng thái lệch bằng SQL trực tiếp (dữ
    liệu cũ đã lệch sẵn trước khi có guard), resolve vẫn không được credit lại
    những sản phẩm ledger đã ghi.
    """
    graph = seeded_factory
    session_id = _closed_session(api, graph, good=10, defect=5)
    assert _resolve(api, session_id, graph, repaired=2).status_code == 200

    # Giả lập dữ liệu đã lệch từ trước: xoá credit khỏi dòng session, giữ ledger.
    # Từ 0051 phần credit nằm ở repaired_qty, nên đó là cột bị xoá ở đây.
    with db.cursor() as cur:
        cur.execute('UPDATE work_sessions SET good_qty=10,repaired_qty=0 WHERE id=%s', (session_id,))

    # Còn chờ sửa thật = 5 - 2 (ledger) = 3, chứ không phải 5.
    too_many = _resolve(api, session_id, graph, repaired=4)
    assert too_many.status_code == 409, too_many.text
    assert '3' in too_many.json().get('message', ''), too_many.text

    within = _resolve(api, session_id, graph, repaired=3)
    assert within.status_code == 200, within.text
    total = db.execute('SELECT COALESCE(SUM(qty_reworked),0) n FROM rework_ledger WHERE source_session_id=%s',
                       (session_id,)).fetchone()['n']
    assert total == 5, 'tổng đã xử lý không được vượt số lỗi ban đầu'


def test_edit_session_is_guarded_the_same_way(api, db, seeded_factory):
    graph = seeded_factory
    session_id = _closed_session(api, graph, good=10, defect=5)
    assert _resolve(api, session_id, graph, repaired=2).status_code == 200
    current = db.execute('SELECT employee_id,operation_id,started_at,ended_at,updated_at FROM work_sessions WHERE id=%s',
                         (session_id,)).fetchone()

    edited = api.patch(f'{BASE_URL}/api/supervisor/sessions/{session_id}', json={
        'employee_id': current['employee_id'], 'operation_id': current['operation_id'],
        'status': 'CLOSED',
        'started_at': current['started_at'].isoformat(),
        'ended_at': current['ended_at'].isoformat(),
        'good_qty': 10, 'defect_qty': 5, 'rework_qty': 0,
        'reason': 'Nhập lại theo phiếu'}, timeout=20)
    assert edited.status_code == 409, edited.text
    after = db.execute('SELECT rework_qty,repaired_qty FROM work_sessions WHERE id=%s', (session_id,)).fetchone()
    assert (after['rework_qty'], after['repaired_qty']) == (5, 2)
