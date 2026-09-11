"""Kiosk điều hành v1: mỗi lúc chỉ hiển thị chi tiết MỘT PO.

Nguồn sự thật của màn hình lớn (xem docs/MESFLOW_MASTER_REQUIREMENTS_VI.md,
REQ-KIOSK-010): "Kiosk v1 hiển thị chi tiết cho một PO tại một thời điểm; thay
đổi từ PO khác chỉ xuất hiện dưới dạng notification summary và không ảnh hưởng
layout/task ordering của PO đang focus."

Các bài dưới đây kiểm đúng ranh giới đó ở TẦNG DỮ LIỆU, nơi nó có thể được
khẳng định chắc chắn: nếu server đã tách hai danh sách thì không có đường nào
để task/KPI của PO khác lọt vào panel chính. Phần hành vi màn hình (auto
paging, transition "Vừa hoàn thành") nằm ở e2e.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


@pytest.fixture()
def two_orders(db):
    """Hai PO cùng có Operation và sự kiện, để chứng minh chúng không trộn nhau."""
    suffix = uuid.uuid4().hex[:8].upper()
    made: dict[str, object] = {}
    with db.cursor() as cur:
        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr)
            VALUES(%s,'Thợ Kiosk','TEST','Worker',%s) RETURNING id""",
            (f'KB-{suffix}', f'WF|EMP|KB-{suffix}'))
        employee_id = cur.fetchone()['id']
        for key, label in (('a', 'A'), ('b', 'B')):
            cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
                VALUES(%s,%s,100,'IN_PROGRESS') RETURNING id""",
                (f'PO-KB{label}-{suffix}', f'Sản phẩm {label}'))
            po_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
                VALUES(%s,%s,%s,0,true) RETURNING id""",
                (po_id, f'PART-{label}-{suffix}', f'Thân {label}'))
            part_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
                VALUES(%s,%s,%s,%s,'IN_PROGRESS',%s,0) RETURNING id""",
                (po_id, part_id, f'OP-{label}-{suffix}', f'Công đoạn {label}',
                 f'WF|OP|OP-{label}-{suffix}'))
            op_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO production_trace_events
                  (event_type,category,occurred_at,actor_name,production_order_id,operation_id,title,quantity_delta,source)
                VALUES('GOOD_QUANTITY_RECORDED','QUANTITY',CURRENT_TIMESTAMP,%s,%s,%s,
                       'Ghi nhận sản lượng đạt',%s,'NATIVE') RETURNING id""",
                (f'Người {label}', po_id, op_id, 10 if key == 'a' else 20))
            event_id = cur.fetchone()['id']
            made[key] = {'po_id': po_id, 'part_id': part_id, 'op_id': op_id,
                         'event_id': event_id, 'code': f'PO-KB{label}-{suffix}'}
    made['employee_id'] = employee_id
    yield made
    with db.cursor() as cur:
        for key in ('a', 'b'):
            po_id = made[key]['po_id']
            cur.execute('DELETE FROM production_trace_events WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM work_sessions WHERE operation_id IN (SELECT id FROM operations WHERE production_order_id=%s)', (po_id,))
            cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM parts WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))
        cur.execute('DELETE FROM employees WHERE id=%s', (employee_id,))


def _board(api, po_id, **extra):
    query = '&'.join(f'{k}={v}' for k, v in extra.items())
    url = f'{BASE_URL}/api/kiosk-board?po_id={po_id}' + (f'&{query}' if query else '')
    response = api.get(url, timeout=25)
    assert response.status_code == 200, response.text
    return response.json()


class TestPoFocus:
    def test_board_reports_the_requested_po(self, api, two_orders):
        data = _board(api, two_orders['a']['po_id'])
        assert int(data['production_order']['id']) == two_orders['a']['po_id']
        assert data['production_order']['code'] == two_orders['a']['code']

    def test_tasks_never_contain_another_po(self, api, two_orders):
        """Ranh giới quan trọng nhất: panel chính không được trộn PO."""
        data = _board(api, two_orders['a']['po_id'])
        foreign = [t for t in data['tasks']
                   if int(t.get('po_id') or 0) != two_orders['a']['po_id']]
        assert not foreign, f'task của PO khác lọt vào panel chính: {foreign[:2]}'

    def test_kpis_count_only_the_focused_po(self, api, two_orders):
        a = _board(api, two_orders['a']['po_id'])
        b = _board(api, two_orders['b']['po_id'])
        assert a['kpis']['operation_count'] == len(a['tasks'])
        assert b['kpis']['operation_count'] == len(b['tasks'])
        assert int(a['production_order']['id']) != int(b['production_order']['id'])

    def test_the_focused_po_is_always_in_the_selector(self, api, two_orders):
        """PO ĐANG XEM phải luôn có trong bộ chọn, kể cả khi nó xếp ngoài cửa sổ.

        Bộ chọn chỉ trả về PO_OPTION_LIMIT dòng. Bản đầu không ghim PO đang xem
        nên trên một CSDL có hơn 40 PO đang mở, một PO vừa tạo (chưa session,
        chưa hạn -- xếp đáy cả ba tiêu chí) không nằm trong danh sách: <select>
        không có option nào khớp và bộ chọn nói khác header. Chính lane
        integration bắt được ca này trên CSDL test có 119 PO đang mở.
        """
        data = _board(api, two_orders['a']['po_id'])
        listed = {int(x['id']) for x in data['po_options']}
        assert two_orders['a']['po_id'] in listed, 'PO đang xem biến mất khỏi bộ chọn'

    def test_the_selector_says_when_it_is_only_showing_a_window(self, api, two_orders):
        """Cửa sổ bị cắt thì phải NÓI RA, không trình bày như cả danh sách."""
        data = _board(api, two_orders['a']['po_id'])
        assert 'po_total' in data and 'po_truncated' in data
        assert data['po_total'] >= len(data['po_options'])
        assert data['po_truncated'] is (data['po_total'] > len(data['po_options']))

    def test_any_po_is_reachable_by_searching(self, api, two_orders):
        """Thứ hạng không được quyết định PO nào CHỌN ĐƯỢC.

        Xếp hạng (đang làm -> hoạt động gần đây -> hạn) là đúng cho màn hình
        lớn, nhưng nó không được biến thành "PO thứ 41 trở đi không tồn tại".
        Tìm kiếm là thứ bảo đảm mọi PO đều với tới được.
        """
        code = two_orders['b']['code']
        response = api.get(f'{BASE_URL}/api/kiosk-board/po-options?q={code}', timeout=25)
        assert response.status_code == 200, response.text
        data = response.json()
        assert two_orders['b']['po_id'] in {int(x['id']) for x in data['items']}
        assert data['query'] == code

    def test_search_narrows_the_total_too(self, api, two_orders):
        """`total` phải là tổng của CHÍNH bộ lọc đang xem, không phải tổng chung."""
        everything = api.get(f'{BASE_URL}/api/kiosk-board/po-options', timeout=25).json()
        narrowed = api.get(
            f'{BASE_URL}/api/kiosk-board/po-options?q={two_orders["b"]["code"]}', timeout=25).json()
        assert narrowed['total'] <= everything['total']
        assert narrowed['total'] >= 1

    def test_include_id_pins_a_po_that_search_would_drop(self, api, two_orders):
        """include_id ghim PO đang xem kể cả khi nó không khớp từ khoá tìm."""
        data = api.get(
            f'{BASE_URL}/api/kiosk-board/po-options'
            f'?q={two_orders["b"]["code"]}&include_id={two_orders["a"]["po_id"]}',
            timeout=25).json()
        listed = {int(x['id']) for x in data['items']}
        assert two_orders['a']['po_id'] in listed
        assert two_orders['b']['po_id'] in listed

    def test_an_unknown_po_is_refused_not_silently_replaced(self, api):
        """Hỏi một PO không tồn tại phải báo lỗi.

        Lặng lẽ rơi về 'PO đầu danh sách' là kiểu hỏng tệ nhất cho màn hình
        lớn: người xem tin rằng mình đang nhìn PO mình chọn.
        """
        response = api.get(f'{BASE_URL}/api/kiosk-board?po_id=999999999', timeout=25)
        assert response.status_code in {400, 404}, response.status_code

    def test_a_bad_po_id_is_refused(self, api):
        response = api.get(f'{BASE_URL}/api/kiosk-board?po_id=abc', timeout=25)
        assert response.status_code in {400, 422}, response.status_code


class TestActivityFeed:
    def test_focus_feed_only_has_the_focused_po(self, api, two_orders):
        response = api.get(
            f'{BASE_URL}/api/kiosk-board/activity?po_id={two_orders["a"]["po_id"]}', timeout=25)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['events'], 'PO đang xem phải có sự kiện'
        assert all(int(e['po_id']) == two_orders['a']['po_id'] for e in data['events'])

    def test_other_po_events_are_a_separate_list(self, api, two_orders):
        """Biến động PO khác nằm ở danh sách RIÊNG, không chen vào feed chính."""
        data = api.get(
            f'{BASE_URL}/api/kiosk-board/activity?po_id={two_orders["a"]["po_id"]}',
            timeout=25).json()
        other_ids = {int(e['po_id']) for e in data['other_events'] if e.get('po_id')}
        assert two_orders['a']['po_id'] not in other_ids
        assert two_orders['b']['po_id'] in other_ids

    def test_an_event_answers_actor_action_object_impact_time(self, api, two_orders):
        data = api.get(
            f'{BASE_URL}/api/kiosk-board/activity?po_id={two_orders["a"]["po_id"]}',
            timeout=25).json()
        event = next(e for e in data['events'] if e['id'] == two_orders['a']['event_id'])
        assert event['actor_name'] == 'Người A'          # AI
        assert event['actor_kind'] == 'PERSON'
        assert event['event_type'] == 'GOOD_QUANTITY_RECORDED'   # LÀM GÌ
        assert event['operation_name']                   # TRÊN CÁI GÌ
        assert int(event['quantity_delta']) == 10        # RA SAO
        assert event['occurred_at']                      # LÚC NÀO

    def test_a_system_event_is_labelled_system_not_given_a_fake_name(self, api, db, two_orders):
        """Không có actor thì phải nói rõ là hệ thống, không bịa ra tên người."""
        with db.cursor() as cur:
            cur.execute("""INSERT INTO production_trace_events
                  (event_type,category,occurred_at,actor_name,production_order_id,operation_id,title,source)
                VALUES('SESSION_AUTO_CLOSED','SESSION',CURRENT_TIMESTAMP,'',%s,%s,
                       'Session tự đóng cuối ca','NATIVE') RETURNING id""",
                (two_orders['a']['po_id'], two_orders['a']['op_id']))
            auto_id = cur.fetchone()['id']
        data = api.get(
            f'{BASE_URL}/api/kiosk-board/activity?po_id={two_orders["a"]["po_id"]}',
            timeout=25).json()
        event = next(e for e in data['events'] if e['id'] == auto_id)
        assert event['actor_kind'] == 'SYSTEM'
        assert event['actor_name'] == ''

    def test_since_id_only_returns_what_is_new(self, api, db, two_orders):
        """Poll nhanh không được kéo lại cả lịch sử mỗi nhịp."""
        po_id = two_orders['a']['po_id']
        first = api.get(f'{BASE_URL}/api/kiosk-board/activity?po_id={po_id}', timeout=25).json()
        latest = first['latest_id']
        assert latest

        empty = api.get(
            f'{BASE_URL}/api/kiosk-board/activity?po_id={po_id}&since_id={latest}',
            timeout=25).json()
        assert empty['events'] == [], 'since_id không lọc — poll sẽ tải lại toàn bộ'

        with db.cursor() as cur:
            cur.execute("""INSERT INTO production_trace_events
                  (event_type,category,occurred_at,actor_name,production_order_id,operation_id,title,quantity_delta,source)
                VALUES('OPERATION_COMPLETED','OPERATION',CURRENT_TIMESTAMP,'Người A',%s,%s,
                       'Operation hoàn tất',NULL,'NATIVE') RETURNING id""",
                (po_id, two_orders['a']['op_id']))
            new_id = cur.fetchone()['id']
        after = api.get(
            f'{BASE_URL}/api/kiosk-board/activity?po_id={po_id}&since_id={latest}',
            timeout=25).json()
        assert [e['id'] for e in after['events']] == [new_id]

    def test_events_carry_a_stable_id_for_dedupe(self, api, two_orders):
        data = api.get(
            f'{BASE_URL}/api/kiosk-board/activity?po_id={two_orders["a"]["po_id"]}',
            timeout=25).json()
        ids = [e['id'] for e in data['events']]
        assert len(ids) == len(set(ids)), 'id trùng nhau thì khử trùng lặp phía client vô nghĩa'
        assert all(isinstance(i, int) for i in ids)

    def test_activity_requires_a_po(self, api):
        response = api.get(f'{BASE_URL}/api/kiosk-board/activity', timeout=25)
        assert response.status_code in {400, 422}


class TestCrowdedPoCatalogue:
    """Tái hiện đúng ca lane integration gặp: CSDL có nhiều PO đang mở hơn cửa sổ.

    Không mock, không giả định — dựng thật hơn PO_OPTION_LIMIT production order
    đang mở, rồi hỏi về một PO vừa tạo (chưa session, chưa hạn) tức là PO xếp
    đáy cả ba tiêu chí sắp xếp. Đây chính là dòng bị cửa sổ nuốt mất.
    """

    @pytest.fixture()
    def crowd(self, db):
        from mesflow.web.kiosk_board import PO_OPTION_LIMIT
        suffix = uuid.uuid4().hex[:6].upper()
        ids = []
        with db.cursor() as cur:
            # Nhiều PO "hấp dẫn" hơn: có hạn gần, nên xếp trên.
            for i in range(PO_OPTION_LIMIT + 5):
                cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status,due_date)
                    VALUES(%s,'SP đông',10,'IN_PROGRESS',CURRENT_DATE + 1) RETURNING id""",
                    (f'PO-CROWD-{suffix}-{i:03d}',))
                ids.append(cur.fetchone()['id'])
            # PO cần xem: tạo SAU, không session, KHÔNG hạn -> đáy mọi tiêu chí.
            cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
                VALUES(%s,'SP mới tinh',10,'IN_PROGRESS') RETURNING id""",
                (f'PO-FRESH-{suffix}',))
            fresh = cur.fetchone()['id']
        yield {'fresh': fresh, 'code': f'PO-FRESH-{suffix}', 'others': ids, 'limit': PO_OPTION_LIMIT}
        with db.cursor() as cur:
            cur.execute('DELETE FROM production_orders WHERE id = ANY(%s)', (ids + [fresh],))

    def test_a_fresh_po_outside_the_window_is_still_selectable(self, api, crowd):
        data = _board(api, crowd['fresh'])
        assert int(data['production_order']['id']) == crowd['fresh']
        listed = {int(x['id']) for x in data['po_options']}
        assert crowd['fresh'] in listed, (
            'PO đang xem nằm ngoài cửa sổ và bị bộ chọn bỏ rơi — đúng lỗi đã báo'
        )

    def test_the_window_admits_it_is_a_window(self, api, crowd):
        data = _board(api, crowd['fresh'])
        assert len(data['po_options']) <= crowd['limit'] + 1
        assert data['po_truncated'] is True
        assert data['po_total'] > len(data['po_options'])

    def test_the_fresh_po_is_findable_by_search(self, api, crowd):
        data = api.get(
            f'{BASE_URL}/api/kiosk-board/po-options?q={crowd["code"]}', timeout=25).json()
        assert crowd['fresh'] in {int(x['id']) for x in data['items']}
