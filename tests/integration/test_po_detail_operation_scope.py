"""Chi tiết PO phải lấy được ĐÚNG Operation của PO đó, không phụ thuộc DB to cỡ nào.

LỖI THẬT. Màn chi tiết PO (web/static/app.js) nạp dữ liệu bằng

    GET /api/parts?limit=1000
    GET /api/operations?limit=1000

rồi mới lọc theo `production_order_id` Ở TRÌNH DUYỆT. Hai câu đó không có tham
số lọc nào, và endpoint tổng quát sắp xếp `ORDER BY id DESC` với trần cứng
1000 dòng. Nghĩa là khi xưởng đã tạo quá 1000 Operation, cửa sổ 1000 dòng mới
nhất đẩy hết Operation của các PO CŨ ra ngoài -- và màn chi tiết của chính
những PO đó hiện "Part này chưa có Operation". Không có lỗi, không có cảnh báo:
dữ liệu vẫn còn nguyên trong DB, chỉ là màn hình không bao giờ hỏi tới nó.

Hỏng dần theo thời gian nên nó không lộ ra lúc mới dựng: PO đầu tiên luôn đúng,
PO thứ N mới sai, và lúc đó không ai nối được nguyên nhân với màn hình.

Bài test dưới đây KHÔNG dựng 1000 Operation (chậm mà không chứng minh thêm gì).
Nó tái hiện đúng cơ chế: đẩy PO cần xem ra khỏi cửa sổ `limit` bằng vài
Operation mới hơn, rồi đòi hỏi lấy được đủ Operation của PO đó.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = [pytest.mark.postgres, pytest.mark.integration]

OLD_PO_OPERATIONS = 3
NEWER_OPERATIONS = 12


@pytest.fixture()
def crowded_catalog(db):
    """Một PO 'cũ' có Operation, rồi nhiều Operation mới hơn của PO khác."""
    suffix = uuid.uuid4().hex[:8].upper()
    created: dict[str, object] = {'suffix': suffix}
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP CŨ',100,'IN_PROGRESS') RETURNING id""", (f'PO-OLD-{suffix}',))
        old_po = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,%s,'Thân',0,true) RETURNING id""", (old_po, f'PART-OLD-{suffix}'))
        old_part = cur.fetchone()['id']
        old_ops = []
        for index in range(OLD_PO_OPERATIONS):
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
                VALUES(%s,%s,%s,%s,'PLANNED',%s,%s) RETURNING id""",
                (old_po, old_part, f'OLD-{suffix}-{index}', f'Công đoạn {index}',
                 f'WF|OP|OLD-{suffix}-{index}', index))
            old_ops.append(cur.fetchone()['id'])

        # PO mới hơn -> id lớn hơn -> đứng trước trong ORDER BY id DESC.
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP MỚI',100,'IN_PROGRESS') RETURNING id""", (f'PO-NEW-{suffix}',))
        new_po = cur.fetchone()['id']
        cur.execute("""INSERT INTO parts(production_order_id,code,name,sort_order,active)
            VALUES(%s,%s,'Vỏ',0,true) RETURNING id""", (new_po, f'PART-NEW-{suffix}'))
        new_part = cur.fetchone()['id']
        for index in range(NEWER_OPERATIONS):
            cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
                VALUES(%s,%s,%s,%s,'PLANNED',%s,%s)""",
                (new_po, new_part, f'NEW-{suffix}-{index}', f'Công đoạn mới {index}',
                 f'WF|OP|NEW-{suffix}-{index}', index))

    created.update(old_po=old_po, old_part=old_part, old_ops=old_ops,
                   new_po=new_po, new_part=new_part)
    yield created

    with db.cursor() as cur:
        for po_id in (new_po, old_po):
            cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM parts WHERE production_order_id=%s', (po_id,))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))


def test_operations_can_be_scoped_to_one_production_order(api, crowded_catalog):
    """Có cách hỏi ĐÚNG Operation của một PO, không phải lọc sau khi đã cắt."""
    response = api.get(
        f'{BASE_URL}/api/operations?production_order_id={crowded_catalog["old_po"]}&limit=1000',
        timeout=25)
    assert response.status_code == 200, response.text
    items = response.json()['items']
    returned = {int(x['id']) for x in items}
    assert returned == set(crowded_catalog['old_ops']), (
        'API không lọc được theo PO: trả về Operation của PO khác hoặc thiếu Operation '
        f'của chính PO này ({len(items)} dòng)')


def test_an_older_po_keeps_its_operations_when_newer_ones_crowd_the_window(api, crowded_catalog):
    """Đúng cơ chế hỏng: cửa sổ `limit` bị Operation mới hơn chiếm chỗ.

    `limit` nhỏ hơn số Operation mới ở đây đóng vai trò trần 1000 dòng ngoài
    thực tế -- cùng một phép cắt, chỉ nhỏ lại cho test chạy nhanh.
    """
    limit = NEWER_OPERATIONS // 2
    response = api.get(
        f'{BASE_URL}/api/operations?production_order_id={crowded_catalog["old_po"]}&limit={limit}',
        timeout=25)
    assert response.status_code == 200, response.text
    returned = {int(x['id']) for x in response.json()['items']}
    assert returned == set(crowded_catalog['old_ops']), (
        'Operation của PO cũ bị Operation mới hơn đẩy ra khỏi kết quả -- đúng lỗi '
        'màn chi tiết PO hiện "Part này chưa có Operation"')


def test_parts_can_be_scoped_to_one_production_order(api, crowded_catalog):
    """Part đi cùng một đường với Operation, và hỏng theo đúng cách đó."""
    response = api.get(
        f'{BASE_URL}/api/parts?production_order_id={crowded_catalog["old_po"]}&limit=1000',
        timeout=25)
    assert response.status_code == 200, response.text
    returned = {int(x['id']) for x in response.json()['items']}
    assert returned == {crowded_catalog['old_part']}, 'API Part không lọc được theo PO'


def test_listing_without_the_filter_is_unchanged(api, crowded_catalog):
    """Bộ lọc là TÙY CHỌN: nơi gọi cũ không truyền gì thì hành vi y như trước."""
    response = api.get(f'{BASE_URL}/api/operations?limit=1000', timeout=25)
    assert response.status_code == 200, response.text
    returned = {int(x['id']) for x in response.json()['items']}
    assert set(crowded_catalog['old_ops']) & returned, 'danh sách không lọc phải vẫn có dữ liệu'


def test_a_bad_filter_value_is_refused_rather_than_ignored(api):
    """Lọc sai kiểu phải báo lỗi, không được lặng lẽ trả về TOÀN BỘ danh sách.

    Bỏ qua tham số không hiểu chính là cách một màn hình tưởng mình đã lọc mà
    thật ra đang đọc cả bảng.
    """
    response = api.get(f'{BASE_URL}/api/operations?production_order_id=abc', timeout=25)
    assert response.status_code in {400, 422}, (
        f'lọc sai kiểu bị bỏ qua thay vì báo lỗi: {response.status_code}')


def test_a_resource_with_its_own_list_signature_still_lists(api):
    """Them tham so cho danh sach tong quat khong duoc lam vo resource khac.

    TemplateRepository ghi de list() voi chu ky rieng (no con tinh them
    part_count/operation_count). Ban dau ban va nay truyen scope_id vo dieu
    kien va lam /api/templates tra 400 -- mot resource khong lien quan gi toi
    lỗi dang sua. Nen duong "khong co pham vi" phai goi Y NGUYEN nhu truoc.
    """
    response = api.get(f'{BASE_URL}/api/templates?limit=500', timeout=25)
    assert response.status_code == 200, response.text


def test_a_resource_that_cannot_be_scoped_refuses_the_filter(api):
    """Template khong thuoc ve mot PO nao, nen loc theo PO la mot yeu cau vo
    nghia -- phai bao loi chu khong duoc lam ngo roi tra ve ca bang."""
    response = api.get(f'{BASE_URL}/api/templates?production_order_id=1', timeout=25)
    assert response.status_code in {400, 422}, (
        f'resource khong loc duoc theo PO van nhan tham so: {response.status_code}')
