"""REQ-KIOSK-012: bảng mô phỏng quét QR phải lọc được theo Production Order.

Xưởng báo: màn mô phỏng/demo kiosk có quá nhiều Operation nên không tìm nổi.
Danh sách phẳng trước đây gom công đoạn của MỌI PO đang chạy vào một <select>
rồi cắt ở ``LIMIT 500`` -- phần đuôi không có đường nào chạm tới.

Vì vậy điều phải chứng minh ở đây KHÔNG phải là "giao diện có cái ô lọc", mà
là: phạm vi được cắt ở SQL theo ``production_orders.id``, và một Operation nằm
sau chỗ cắt của danh sách tổng vẫn chọn được sau khi lọc/tìm. Lọc lại ở trình
duyệt trên tập đã bị cắt sẽ ĐỎ ở ``test_operation_past_the_global_cap_*``.
"""
from __future__ import annotations

import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = [pytest.mark.postgres, pytest.mark.integration]

DEMO = f'{BASE_URL}/api/kiosk-web/demo-data'
# Bằng DEMO_OP_LIMIT của kiosk.py. Bài test dựng dữ liệu vượt hẳn con số này
# để chỗ cắt là thật, không phải giả định.
OP_LIMIT = 500


def _demo(api, **params):
    response = api.get(DEMO, params=params, timeout=30)
    return response


def _ok(api, **params):
    response = _demo(api, **params)
    assert response.status_code == 200, response.text[:400]
    body = response.json()
    assert body['ok'] is True, body
    return body


def _codes(body):
    return {str(row['code']) for row in body['operations']}


@pytest.fixture()
def two_pos(db):
    """PO A (3 công đoạn), PO B (2 công đoạn), PO C (đang chạy, chưa có OP)."""
    suffix = uuid.uuid4().hex[:8].upper()
    made = {'suffix': suffix}
    with db.cursor() as cur:
        for key, label, ops in (
            ('a', 'A', ('CUT', 'BEND', 'WELD')),
            ('b', 'B', ('PAINT', 'PACK')),
            ('c', 'C', ()),
        ):
            cur.execute(
                "INSERT INTO production_orders(code,product,planned_quantity,status)"
                " VALUES(%s,%s,100,'IN_PROGRESS') RETURNING id",
                (f'HP2-PO-{label}-{suffix}', f'Sản phẩm {label}'))
            po_id = cur.fetchone()['id']
            made[f'po_{key}'] = po_id
            made[f'po_{key}_code'] = f'HP2-PO-{label}-{suffix}'
            if not ops:
                continue
            cur.execute(
                'INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,%s) RETURNING id',
                (po_id, f'HP2-PART-{label}-{suffix}', f'Chi tiết {label}'))
            part_id = cur.fetchone()['id']
            made[f'part_{key}_code'] = f'HP2-PART-{label}-{suffix}'
            made[f'ops_{key}'] = []
            for order, name in enumerate(ops):
                code = f'HP2-{label}-{name}-{suffix}'
                cur.execute(
                    """INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
                       VALUES(%s,%s,%s,%s,'IN_PROGRESS',%s,%s) RETURNING id""",
                    (po_id, part_id, code, f'Công đoạn {name}', f'WF|OP|{code}', order))
                made[f'ops_{key}'].append(code)
    yield made
    _drop_pos(db, f'HP2-PO-%-{suffix}')


@pytest.fixture()
def many_pos(db):
    """45 PO × 45 công đoạn = 2025 OP -- vượt hẳn ``LIMIT 500`` của danh sách
    tổng, nên "còn chọn được không" là câu hỏi có thật chứ không giả định."""
    suffix = uuid.uuid4().hex[:8].upper()
    with db.cursor() as cur:
        cur.execute(
            """WITH po AS (
                 INSERT INTO production_orders(code,product,planned_quantity,status)
                 SELECT format('HP2-BULK-%%s-%s', to_char(n,'FM000')), 'Bulk', 10, 'IN_PROGRESS'
                 FROM generate_series(1,45) n
                 RETURNING id, code
               ), part AS (
                 INSERT INTO parts(production_order_id,code,name)
                 SELECT po.id, po.code || '-P', 'Bulk part' FROM po
                 RETURNING id, production_order_id
               )
               INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
               SELECT part.production_order_id, part.id,
                      po.code || '-OP' || to_char(k,'FM000'),
                      'Bulk op ' || k, 'IN_PROGRESS',
                      'WF|OP|' || po.code || '-OP' || to_char(k,'FM000'), k
               FROM part JOIN po ON po.id = part.production_order_id,
                    generate_series(1,45) k""" % suffix)
        cur.execute(
            """SELECT id, code FROM production_orders
               WHERE code LIKE %s ORDER BY code DESC LIMIT 1""", (f'HP2-BULK-%-{suffix}',))
        last = cur.fetchone()
    yield {'suffix': suffix, 'last_po_id': last['id'], 'last_po_code': last['code'],
           'last_op_code': f"{last['code']}-OP045"}
    _drop_pos(db, f'HP2-BULK-%-{suffix}')


def _drop_pos(db, code_like):
    with db.cursor() as cur:
        cur.execute('DELETE FROM operations WHERE production_order_id IN'
                    ' (SELECT id FROM production_orders WHERE code LIKE %s)', (code_like,))
        cur.execute('DELETE FROM parts WHERE production_order_id IN'
                    ' (SELECT id FROM production_orders WHERE code LIKE %s)', (code_like,))
        cur.execute('DELETE FROM production_orders WHERE code LIKE %s', (code_like,))


# ------------------------------------------------------- danh sách PH để chọn

def test_running_po_with_no_operation_is_still_selectable(api, two_pos):
    """PO đang chạy mà chưa có công đoạn nào vẫn phải nằm trong danh sách chọn.

    Giấu nó đi thì người dùng chỉ thấy PO của mình biến mất mà không hiểu vì
    sao; để nó lại kèm ``operation_count = 0`` là câu trả lời đọc được.
    """
    listed = {row['code']: row for row in _ok(api)['production_orders']}
    assert two_pos['po_c_code'] in listed, 'PO chưa có OP bị loại khỏi danh sách chọn'
    assert int(listed[two_pos['po_c_code']]['operation_count']) == 0
    assert int(listed[two_pos['po_a_code']]['operation_count']) == 3


def test_po_list_carries_the_canonical_id_not_only_the_code(api, two_pos):
    """Phạm vi phải khoá bằng khoá chính. ``code`` là chuỗi người nhập."""
    row = next(x for x in _ok(api)['production_orders'] if x['code'] == two_pos['po_a_code'])
    assert int(row['id']) == two_pos['po_a']


# ------------------------------------------------------------- cô lập phạm vi

def test_po_scope_hides_every_operation_of_another_po(api, two_pos):
    scoped = _ok(api, po_id=two_pos['po_a'])
    codes = _codes(scoped)
    assert codes == set(two_pos['ops_a']), codes
    for code in two_pos['ops_b']:
        assert code not in codes, 'công đoạn của PO B lọt vào phạm vi PO A'
    assert scoped['po_id'] == two_pos['po_a']
    assert all(int(row['po_id']) == two_pos['po_a'] for row in scoped['operations'])


def test_switching_po_switches_the_whole_result_set(api, two_pos):
    assert _codes(_ok(api, po_id=two_pos['po_b'])) == set(two_pos['ops_b'])


def test_po_with_no_operation_scopes_to_empty_not_to_everything(api, two_pos):
    """Bẫy kinh điển: phạm vi rỗng bị hiểu thành "không lọc" và trả về tất cả."""
    body = _ok(api, po_id=two_pos['po_c'])
    assert body['operations'] == []
    assert body['operations_total'] == 0


def test_unknown_po_id_returns_an_empty_scope(api, two_pos):
    body = _ok(api, po_id=2_000_000_000)
    assert body['operations'] == []


def test_garbage_po_id_is_rejected_instead_of_silently_ignored(api):
    """Bỏ qua ``po_id`` rác nghĩa là bày công đoạn của mọi lệnh cho một màn
    hình đang tưởng mình chỉ hiện một lệnh."""
    response = _demo(api, po_id='abc')
    assert response.status_code == 400, response.text[:300]
    assert response.json()['error_code'] == 'REQ-400'


# -------------------------------------------------------------- tìm kiếm OP

def test_search_matches_operation_code_name_and_part(api, two_pos):
    suffix = two_pos['suffix']
    by_code = _codes(_ok(api, po_id=two_pos['po_a'], q=f'BEND-{suffix}'))
    assert by_code == {f'HP2-A-BEND-{suffix}'}
    by_name = _codes(_ok(api, po_id=two_pos['po_a'], q='Công đoạn WELD'))
    assert by_name == {f'HP2-A-WELD-{suffix}'}
    by_part = _codes(_ok(api, po_id=two_pos['po_a'], q=two_pos['part_a_code']))
    assert by_part == set(two_pos['ops_a'])


def test_search_stays_inside_the_selected_po(api, two_pos):
    """Cùng một từ khoá, nhưng phạm vi PO phải thắng."""
    shared = f'HP2-'
    assert _codes(_ok(api, po_id=two_pos['po_b'], q=shared)) == set(two_pos['ops_b'])


def test_search_wildcards_are_literal_characters(api, two_pos):
    """Gõ ``%`` phải là gõ ký tự ``%``. Nếu nó lọt xuống LIKE thì mọi công đoạn
    khớp và ô tìm kiếm trở thành vô nghĩa."""
    body = _ok(api, po_id=two_pos['po_a'], q='%')
    assert body['operations'] == [], 'ký tự đại diện của LIKE không được thoát'


def test_search_with_no_match_is_empty_not_unfiltered(api, two_pos):
    assert _ok(api, po_id=two_pos['po_a'], q='KHONG-CO-CAI-NAY')['operations'] == []


# ------------------------------------------ vượt trần: OP nào cũng phải tới được

def test_operation_past_the_global_cap_is_reachable_by_po_scope(api, many_pos):
    """Đây là bài quan trọng nhất của REQ-KIOSK-012.

    Công đoạn cuối của PO cuối nằm sau chỗ cắt ``LIMIT 500`` của danh sách
    tổng. Nếu việc lọc làm ở trình duyệt trên đúng tập đã bị cắt đó thì nó
    KHÔNG BAO GIỜ xuất hiện, dù giao diện có bao nhiêu ô lọc.
    """
    unscoped = _ok(api)
    assert len(unscoped['operations']) == OP_LIMIT, 'kịch bản cần một tập thật sự bị cắt'
    assert unscoped['operations_total'] > OP_LIMIT, 'tổng phải đếm trước LIMIT'
    assert many_pos['last_op_code'] not in _codes(unscoped), \
        'dữ liệu chưa đủ lớn để chứng minh điều cần chứng minh'

    scoped = _ok(api, po_id=many_pos['last_po_id'])
    assert many_pos['last_op_code'] in _codes(scoped)
    assert len(scoped['operations']) == 45
    assert scoped['operations_total'] == 45


def test_operation_past_the_global_cap_is_reachable_by_search(api, many_pos):
    found = _codes(_ok(api, q=many_pos['last_op_code']))
    assert found == {many_pos['last_op_code']}


def test_every_running_po_is_listed_not_just_the_first_page(api, many_pos):
    body = _ok(api)
    codes = {row['code'] for row in body['production_orders']}
    assert many_pos['last_po_code'] in codes, 'PO thứ 45 không chọn được'
    assert body['production_orders_total'] >= 45


# ------------------------------------------------------------------- hợp đồng

def test_include_operations_skips_the_employee_roster(api, two_pos):
    """Đổi PO/gõ tìm kiếm chỉ cần công đoạn. Kéo lại cả danh sách nhân viên sẽ
    dựng lại <select> đó và làm mất nhân viên người dùng đang chọn."""
    body = _ok(api, include='operations', po_id=two_pos['po_a'])
    assert 'employees' not in body
    assert 'operations' in body


def test_unknown_include_section_is_rejected(api):
    response = _demo(api, include='employees,secrets')
    assert response.status_code == 400, response.text[:300]


def test_no_parameters_keeps_the_original_contract(api, two_pos):
    """Hợp đồng cũ vẫn nguyên: gọi trần vẫn có employees + operations."""
    body = _ok(api)
    assert isinstance(body['employees'], list)
    assert isinstance(body['operations'], list)
    assert body['po_id'] is None


def test_filter_parameters_do_not_open_an_unauthenticated_door(two_pos):
    """``demo-data`` trả QR thẻ nhân viên -- một credential. Thêm tham số lọc
    không được tạo ra một biến thể nào của endpoint bỏ qua đăng nhập."""
    anon = requests.Session()
    anon.headers['User-Agent'] = 'hp2-anon'
    for params in ({'po_id': two_pos['po_a']}, {'include': 'operations'}, {'q': 'CUT'}):
        response = anon.get(DEMO, params=params, timeout=15)
        assert response.status_code in (401, 403), response.text[:200]
        assert 'WF|EMP|' not in response.text
