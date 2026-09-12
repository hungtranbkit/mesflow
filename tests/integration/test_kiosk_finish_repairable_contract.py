"""Hợp đồng sản lượng khi kết thúc session từ Kiosk web — REQ-KIOSK-011.

Điều quan trọng nhất ở đây là MỘT CÂU: `rework_qty` nghĩa là "trong số NG này,
bao nhiêu cái CÓ THỂ sửa", không phải "đã sửa xong". Nó đi vào hàng chờ sửa và
chỉ được credit về sản lượng đạt SAU KHI có người sửa thật và resolve.

Nếu chỗ nào cộng repairable vào good ngay lúc kết thúc session thì cùng một sản
phẩm vật lý được tính đạt hai lần: một lần ở đây, một lần khi resolve. Bài test
dưới đây đóng đúng cánh cửa đó ở tầng API.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


def _start(api, graph):
    response = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'PAR-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'operation_id': graph['operation_id'], 'station_id': graph['station_id']}, timeout=15)
    assert response.status_code == 201, response.text
    return response.json()['session']['id']


def _finish(api, session_id, *, good, defect, rework):
    return api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'PAR-{uuid.uuid4()}', 'good_qty': good,
        'defect_qty': defect, 'rework_qty': rework}, timeout=15)


class TestRepairableIsNotProduction:
    def test_repairable_does_not_inflate_good_quantity(self, api, db, seeded_factory):
        """Khai báo 4 lỗi sửa được KHÔNG làm sản lượng đạt tăng thêm 4."""
        session_id = _start(api, seeded_factory)
        assert _finish(api, session_id, good=40, defect=6, rework=4).status_code == 200

        row = db.execute(
            'SELECT good_qty,defect_qty,rework_qty,scrap_qty FROM work_sessions WHERE id=%s',
            (session_id,)).fetchone()
        assert int(row['good_qty']) == 40, 'lỗi sửa được bị cộng vào sản lượng đạt'
        assert int(row['defect_qty']) == 6
        assert int(row['rework_qty']) == 4
        assert int(row['scrap_qty']) == 0

        operation = db.execute('SELECT done_qty,defect_qty,rework_qty FROM operations WHERE id=%s',
                               (seeded_factory['operation_id'],)).fetchone()
        assert int(operation['done_qty']) == 40
        assert int(operation['rework_qty']) == 4

    def test_a_session_with_unresolved_defects_reaches_the_repair_queue(self, api, seeded_factory):
        """Session còn NG chưa xử lý phải hiện ở Hàng chờ sửa."""
        session_id = _start(api, seeded_factory)
        assert _finish(api, session_id, good=40, defect=6, rework=4).status_code == 200

        queue = api.get(f'{BASE_URL}/api/rework/queue?limit=1000', timeout=20)
        assert queue.status_code == 200, queue.text
        mine = [x for x in queue.json()['items'] if int(x['source_session_id']) == session_id]
        assert mine, 'session có NG chưa xử lý phải nằm trong hàng chờ sửa'
        # Chờ sửa = số CÔNG NHÂN KHAI LÀ SỬA ĐƯỢC và chưa xử lý = 4.
        # Trước 0051_repair_pending_semantics con số này là 2 -- tức
        # defect - rework - scrap, chính là 2 cái công nhân khai là KHÔNG sửa
        # được. Xem test_declared_repairable_is_not_lost ngay dưới.
        assert int(mine[0]['pending_qty']) == 4

    def test_declared_repairable_is_not_lost(self, api, seeded_factory):
        """Khai báo 4 sửa được thì 4 cái đó phải còn đường quay lại sản lượng.

        xfail(strict) do lane Kiosk parity đặt, kèm chẩn đoán đúng: rework_qty
        mang HAI NGHĨA, nên N cái khai là sửa được bị trừ khỏi pending mà không
        bao giờ được credit về good -- biến mất khỏi cả hai sổ. Đã sửa tại
        0051_repair_pending_semantics (tách repaired_qty ra khỏi rework_qty),
        nên gỡ xfail theo đúng lời dặn trong reason.

        MỘT ĐIỂM KHÁC với bản gốc: bài cũ chờ `pending == 6`. Con số đó gộp hai
        thứ khác nhau -- "NG không bị mất" và "NG đang chờ sửa". 2 cái công nhân
        khai là KHÔNG sửa được là PHẾ ngay tại thời điểm khai báo; đưa chúng vào
        hàng chờ sửa là mời người ta đi sửa hàng đã bỏ. Bất biến đúng là không
        cái nào biến mất: chờ sửa + phế = tổng NG.
        """
        session_id = _start(api, seeded_factory)
        assert _finish(api, session_id, good=40, defect=6, rework=4).status_code == 200
        queue = api.get(f'{BASE_URL}/api/rework/queue?limit=1000', timeout=20).json()
        mine = [x for x in queue['items'] if int(x['source_session_id']) == session_id]
        pending = int(mine[0]['pending_qty']) if mine else 0
        assert pending == 4, (
            f'{4 - pending} sản phẩm khai báo sửa được không còn ở hàng chờ sửa '
            'mà cũng chưa được tính vào sản lượng đạt'
        )
        overview = api.get(f'{BASE_URL}/api/dashboard/overview?limit=5000', timeout=20).json()
        row = next(x for x in overview['operations']
                   if int(x['operation_id']) == int(seeded_factory['operation_id']))
        assert int(row['repair_pending_quantity']) == 4, 'Tổng quan phải nói đúng con số đó'
        assert int(row['scrap_qty']) == 2, '2 cái khai là không sửa được là phế'
        assert int(row['repair_pending_quantity']) + int(row['scrap_qty']) == 6, 'không cái nào biến mất'

    def test_repairable_above_defect_is_refused_by_the_server(self, api, seeded_factory):
        """Giao diện chặn là lớp đầu; API phải tự chặn kể cả khi gọi thẳng."""
        session_id = _start(api, seeded_factory)
        response = _finish(api, session_id, good=10, defect=3, rework=9)
        assert response.status_code in {400, 422}, response.status_code

    def test_zero_repairable_is_accepted(self, api, db, seeded_factory):
        """Chọn "tiếp tục, không có" gửi rework=0 và phải đi qua bình thường."""
        session_id = _start(api, seeded_factory)
        assert _finish(api, session_id, good=12, defect=3, rework=0).status_code == 200
        row = db.execute('SELECT good_qty,defect_qty,rework_qty FROM work_sessions WHERE id=%s',
                         (session_id,)).fetchone()
        assert (int(row['good_qty']), int(row['defect_qty']), int(row['rework_qty'])) == (12, 3, 0)

    def test_no_defect_means_no_repairable(self, api, db, seeded_factory):
        """NG = 0 thì luồng bỏ qua bước hỏi, và rework phải là 0."""
        session_id = _start(api, seeded_factory)
        assert _finish(api, session_id, good=25, defect=0, rework=0).status_code == 200
        row = db.execute('SELECT defect_qty,rework_qty FROM work_sessions WHERE id=%s',
                         (session_id,)).fetchone()
        assert int(row['defect_qty']) == 0 and int(row['rework_qty']) == 0


class TestKioskWebPayload:
    def test_the_kiosk_web_endpoint_forwards_all_three_numbers(self, api, db, seeded_factory):
        """Ba số phải đi TÁCH BẠCH qua đường kiosk web, không gộp vào nhau."""
        session_id = _start(api, seeded_factory)
        response = api.post(f'{BASE_URL}/api/kiosk-web/finish/{session_id}', json={
            'request_id': f'PAR-{uuid.uuid4()}',
            'good_qty': 30, 'defect_qty': 5, 'rework_qty': 2}, timeout=15)
        assert response.status_code == 200, response.text
        row = db.execute('SELECT good_qty,defect_qty,rework_qty FROM work_sessions WHERE id=%s',
                         (session_id,)).fetchone()
        assert (int(row['good_qty']), int(row['defect_qty']), int(row['rework_qty'])) == (30, 5, 2)

    def test_the_kiosk_web_endpoint_also_refuses_repairable_above_defect(self, api, seeded_factory):
        session_id = _start(api, seeded_factory)
        response = api.post(f'{BASE_URL}/api/kiosk-web/finish/{session_id}', json={
            'request_id': f'PAR-{uuid.uuid4()}',
            'good_qty': 1, 'defect_qty': 2, 'rework_qty': 5}, timeout=15)
        assert response.status_code in {400, 422}, response.status_code
