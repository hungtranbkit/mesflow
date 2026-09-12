"""B2: cùng một Operation phải được coi là sản-xuất/hỗ-trợ giống nhau ở MỌI nơi.

Mỗi bài dưới đây tương ứng một chỗ mà luật phân loại từng được viết riêng, và
mỗi bài ĐỎ trên hành vi cũ -- không phải một lời hứa bằng comment.

  * danh sách việc của kiosk web và snapshot offline của ESP liệt kê CẢ bàn
    SỬA HÀNG, trong khi lock_startable_operation() từ chối mở session trên nó:
    công nhân nhìn thấy một dòng việc mà chính máy sẽ từ chối;
  * ``operation_count`` trả về từ endpoint Start đếm trần mọi dòng operations,
    còn reconcile_production_order() đếm riêng OP sản xuất -- hai con số khác
    nhau cho cùng một PO;
  * luật "session mang sản lượng không được nằm trên OP phụ" CHỈ có ở
    transfer_operation(); edit_session() và adjust() đi vòng qua nó, dù cả hai
    đều đổi được số lượng lẫn Operation.

Kịch bản dùng chung: một PO có đủ ba loại -- OP sản xuất, tem SETUP gắn với nó,
và bàn SỬA HÀNG do chính luồng rework thật tạo ra.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


def _setup_row_for(api, operation_id):
    assert api.put(f'{BASE_URL}/api/operations/{operation_id}/setup',
                   json={'requires_setup': True, 'setup_note': 'x'}, timeout=15).status_code == 200
    return api.get(f'{BASE_URL}/api/operations/{operation_id}/setup', timeout=15).json()['setup']


def _closed_session(api, graph, *, good=0, defect=0, rework=None, operation_id=None):
    # rework_qty = số NG công nhân KHAI LÀ SỬA ĐƯỢC (0051). Mặc định khai hết,
    # để NG vào được hàng chờ sửa -- rework=0 nghĩa là "toàn bộ là phế".
    started = api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'B2-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
        'operation_id': operation_id or graph['operation_id'],
        'station_id': graph['station_id']}, timeout=15)
    assert started.status_code == 201, started.text
    session_id = started.json()['session']['id']
    finished = api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'B2-{uuid.uuid4()}', 'good_qty': good, 'defect_qty': defect,
        'rework_qty': defect if rework is None else rework}, timeout=15)
    assert finished.status_code == 200, finished.text
    return session_id


@pytest.fixture()
def three_types(api, db, seeded_factory):
    """PO có đủ OP sản xuất + SETUP + bàn SỬA HÀNG (do luồng rework thật tạo)."""
    graph = dict(seeded_factory)
    graph['setup_id'] = _setup_row_for(api, graph['operation_id'])['id']
    # Bàn SỬA HÀNG chỉ ra đời khi có NG được xử lý -- dựng bằng đúng đường đó,
    # không INSERT tay, để bài test nói về hệ thống thật.
    graph['source_session_id'] = _closed_session(api, graph, good=10, defect=4)
    resolved = api.post(
        f'{BASE_URL}/api/rework/queue/{graph["source_session_id"]}/resolve',
        json={'request_id': f'B2-{uuid.uuid4()}', 'employee_id': graph['employee_id'],
              'repaired_qty': 3, 'scrapped_qty': 1}, timeout=20)
    assert resolved.status_code == 200, resolved.text
    bench = db.execute(
        """SELECT id,code FROM operations
           WHERE production_order_id=%s AND COALESCE(operation_type,'PRODUCTION')='REWORK'""",
        (graph['po_id'],)).fetchone()
    assert bench, 'luồng rework phải tạo ra bàn SỬA HÀNG'
    graph['rework_id'] = bench['id']
    graph['rework_code'] = bench['code']
    return graph


# --------------------------------------------------- danh sách việc quét được

def test_kiosk_work_list_offers_only_operation_types_a_scan_can_start(api, three_types):
    """Kiosk web không được bày ra bàn SỬA HÀNG.

    lock_startable_operation() từ chối mở session trên nó. Liệt kê nó ở đây là
    đưa cho xưởng một dòng việc mà máy sẽ từ chối -- đúng lỗi danh mục QR đã
    sửa từ trước bằng cùng tập loại.
    """
    payload = api.get(f'{BASE_URL}/api/kiosk-web/demo-data', timeout=25)
    assert payload.status_code == 200, payload.text
    listed = {int(x['id']) for x in payload.json()['operations']}
    assert three_types['operation_id'] in listed, 'OP sản xuất phải còn trong danh sách'
    assert three_types['setup_id'] in listed, \
        'tem SETUP phải quét được: quét nó là cách duy nhất ghi nhận chuẩn bị máy'
    assert three_types['rework_id'] not in listed, \
        'bàn SỬA HÀNG lọt vào danh sách việc của kiosk, nhưng kiosk sẽ từ chối khi chọn'


def test_offline_snapshot_carries_only_operation_types_a_scan_can_start(three_types):
    """Snapshot offline là danh sách việc khi mất mạng.

    Một bàn SỬA HÀNG trong đó nghĩa là công đã làm mà đồng bộ ngược sẽ bị từ
    chối -- đúng thứ chế độ offline sinh ra để tránh.
    """
    from mesflow.db.repositories.offline_sync import OfflineSyncRepository

    snapshot = OfflineSyncRepository().snapshot('B2-TEST-DEVICE', '')
    codes = {str(x['code']) for x in snapshot['operations']}
    assert three_types['rework_code'] not in codes, \
        'bàn SỬA HÀNG lọt vào snapshot offline của thiết bị'


# ------------------------------------------------------------ operation_count

def test_po_operation_count_counts_production_steps_only(api, db, three_types):
    """Endpoint Start và reconcile_production_order() phải trả cùng một số."""
    total = db.execute('SELECT COUNT(*) n FROM operations WHERE production_order_id=%s',
                       (three_types['po_id'],)).fetchone()['n']
    production = db.execute(
        """SELECT COUNT(*) n FROM operations WHERE production_order_id=%s
           AND COALESCE(operation_type,'PRODUCTION')='PRODUCTION'""",
        (three_types['po_id'],)).fetchone()['n']
    assert total > production, 'kịch bản phải có ít nhất một OP phụ, nếu không bài test vô nghĩa'

    started = api.post(f'{BASE_URL}/api/production-orders/{three_types["po_id"]}/start',
                       json={}, timeout=20)
    assert started.status_code == 200, started.text
    assert started.json()['operation_count'] == production, \
        'operation_count của PO đang đếm cả tem SETUP / bàn SỬA HÀNG'


# ------------------------------------- luật "OP phụ không mang sản lượng"

def test_editing_a_session_onto_a_support_operation_with_quantity_is_refused(api, three_types):
    """edit_session() phải theo đúng luật transfer_operation() đã có.

    Cả hai đều đổi được Operation của một session mang sản lượng. Nếu chỉ một
    bên chặn, số lượng biến mất khỏi tiến độ PO qua đường còn lại mà không có
    dấu vết nào.
    """
    session_id = _closed_session(api, three_types, good=5)
    response = api.patch(f'{BASE_URL}/api/supervisor/sessions/{session_id}', json={
        'reason': 'B2 regression', 'operation_id': three_types['setup_id'],
        'good_qty': 5, 'defect_qty': 0, 'rework_qty': 0}, timeout=20)
    assert response.status_code == 409, \
        f'edit_session cho phép đẩy 5 sản phẩm sang OP setup: {response.status_code} {response.text}'
    assert 'OP phụ' in response.json().get('message', '')


def test_editing_a_session_onto_a_support_operation_without_quantity_is_allowed(api, three_types):
    """Luật là về SẢN LƯỢNG, không phải cấm mọi thao tác trên OP phụ.

    Một session setup (số lượng bằng 0 theo cấu tạo) vẫn phải sửa được giờ giấc.
    """
    setup_session = _closed_session(api, three_types, operation_id=three_types['setup_id'])
    response = api.patch(f'{BASE_URL}/api/supervisor/sessions/{setup_session}', json={
        'reason': 'B2 regression', 'good_qty': 0, 'defect_qty': 0, 'rework_qty': 0,
        'note': 'sửa ghi chú'}, timeout=20)
    assert response.status_code == 200, response.text


def test_adjusting_quantity_onto_a_support_operation_session_is_refused(api, three_types):
    """adjust() là đường ghi số lượng thứ ba, và nó cũng phải qua cùng guard."""
    setup_session = _closed_session(api, three_types, operation_id=three_types['setup_id'])
    response = api.post(f'{BASE_URL}/api/supervisor/sessions/{setup_session}/adjust', json={
        'request_id': f'B2-{uuid.uuid4()}', 'reason': 'B2 regression',
        'good_qty': 7, 'defect_qty': 0, 'rework_qty': 0}, timeout=20)
    assert response.status_code == 409, \
        f'adjust ghi được 7 sản phẩm lên OP setup: {response.status_code} {response.text}'


def test_the_integrity_audit_stays_clean_for_this_scenario(three_types):
    """Không đường ghi nào ở trên được để lại "OP phụ có sản lượng"."""
    from mesflow.services.integrity_audit_service import audit_integrity

    findings = audit_integrity()
    offenders = [x for x in findings.get('support_operation_with_production_quantity', [])
                 if int(x.get('production_order_id') or 0) == three_types['po_id']]
    assert not offenders, offenders


# ----------------------------------------------- công vẫn tính, sản lượng thì không

def test_setup_labour_still_counts_while_its_quantity_never_does(api, db, three_types):
    """Loại OP phụ ra khỏi SẢN LƯỢNG, không phải ra khỏi BẢNG CÔNG.

    Loại nhầm hướng kia là hỏng nặng hơn: giờ chuẩn bị máy biến mất khỏi bảng
    công của người thợ.
    """
    setup_session = _closed_session(api, three_types, operation_id=three_types['setup_id'])
    # Session mở/đóng trong cùng mili giây thì thời lượng làm tròn về 0 và bài
    # test không nói được gì. Lùi giờ bắt đầu để có một khoảng công THẬT.
    with db.cursor() as cur:
        cur.execute("""UPDATE work_sessions SET started_at=ended_at-INTERVAL '30 minutes'
            WHERE id=%s""", (setup_session,))
        # Cố định điều kiện của phép đếm "thiếu định mức" bên dưới thay vì dựa
        # vào việc fixture chung tình cờ để 0 ở cột này (0 = chưa khai định mức).
        cur.execute('UPDATE operations SET standard_seconds_per_unit=0 WHERE id=%s',
                    (three_types['operation_id'],))

    today = db.execute("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::date d").fetchone()['d']
    productivity = api.get(
        f'{BASE_URL}/api/reports/employee-productivity?from={today}&to={today}&limit=1000',
        timeout=25)
    assert productivity.status_code == 200, productivity.text
    mine = [x for x in productivity.json()['employees']
            if int(x['employee_id']) == three_types['employee_id']]
    assert mine, 'nhân viên phải có mặt trong báo cáo năng suất'
    row = mine[0]
    assert int(row['worked_seconds']) >= 1800, \
        f"30 phút công setup không vào giờ làm việc: {row['worked_seconds']}s"
    # Ba session đã đóng: một OP sản xuất, một tem SETUP, một bàn SỬA HÀNG.
    assert int(row['completed_sessions']) == 3, dict(row)
    assert int(row['repair_sessions']) == 2, \
        f'session trên OP phụ không được đếm là công hỗ trợ: {dict(row)}'
    # "Thiếu định mức" phải giữ tính HÀNH ĐỘNG ĐƯỢC: nó nghĩa là một OP sản
    # xuất chưa khai định mức -- thứ quản đốc sửa được. OP phụ không bao giờ có
    # định mức sản xuất, nên đếm chúng ở đây là bắt người ta đi tìm một lỗi cấu
    # hình không tồn tại. Chỉ đúng MỘT session sản xuất được nằm trong đó.
    assert int(row['completed_invalid_sessions']) == 1, dict(row)

    setup_row = db.execute('SELECT done_qty,defect_qty,rework_qty,scrap_qty FROM operations WHERE id=%s',
                           (three_types['setup_id'],)).fetchone()
    assert all(int(setup_row[k] or 0) == 0 for k in setup_row), \
        f'OP setup mang sản lượng: {dict(setup_row)}'


def test_support_operations_are_absent_from_schedule_and_qr_normal_grouping(api, three_types):
    """Lập lịch và danh mục QR "việc quét được" đều không được chứa OP phụ."""
    schedule = api.get(f'{BASE_URL}/api/production-schedule?limit=2000', timeout=25)
    assert schedule.status_code == 200, schedule.text
    scheduled = {int(x['operation_id']) for x in schedule.json()['items']
                 if x.get('operation_id') is not None}
    assert three_types['setup_id'] not in scheduled, 'tem SETUP lọt vào lịch sản xuất'
    assert three_types['rework_id'] not in scheduled, 'bàn SỬA HÀNG lọt vào lịch sản xuất'

    labels = api.get(
        f'{BASE_URL}/api/qr-labels?type=OPERATION&active_only=1&production_order_id={three_types["po_id"]}',
        timeout=25)
    assert labels.status_code == 200, labels.text
    listed = {int(x['id']) for x in labels.json()['items']}
    assert three_types['setup_id'] in listed, 'tem SETUP phải in được'
    assert three_types['rework_id'] not in listed, 'bàn SỬA HÀNG không được in tem'


# ------------------------------------------------------------- rework ledger

def test_repaired_quantity_credits_the_source_operation_exactly_once(api, db, three_types):
    """3 sửa được + 1 phế trên một session có 10 đạt / 4 NG.

    Sửa được phải cộng về OP NGUỒN (10 + 3), phế là phế thật, và không có bất
    kỳ số nào rơi vào bàn SỬA HÀNG.
    """
    source = db.execute('SELECT good_qty,defect_qty,rework_qty,repaired_qty,scrap_qty FROM work_sessions WHERE id=%s',
                        (three_types['source_session_id'],)).fetchone()
    # rework_qty=4 là KHAI BÁO (cả 4 NG sửa được); 3 đã sửa + 1 phế là kết quả.
    assert int(source['rework_qty']) == 4, dict(source)
    assert int(source['repaired_qty']) == 3 and int(source['scrap_qty']) == 1, dict(source)

    operation = db.execute('SELECT done_qty,rework_qty,repaired_qty,scrap_qty FROM operations WHERE id=%s',
                           (three_types['operation_id'],)).fetchone()
    assert int(operation['done_qty']) == 13, \
        f"sửa được không credit về OP nguồn (hoặc credit hai lần): {dict(operation)}"
    assert int(operation['scrap_qty']) == 1, dict(operation)

    bench = db.execute('SELECT done_qty,defect_qty,rework_qty,repaired_qty,scrap_qty FROM operations WHERE id=%s',
                       (three_types['rework_id'],)).fetchone()
    assert all(int(bench[k] or 0) == 0 for k in bench), \
        f'bàn SỬA HÀNG giữ sản lượng riêng -- sẽ bị đếm hai lần ở đâu đó: {dict(bench)}'

    # Resolve lần hai cho phần còn lại phải không vượt quá NG đã ghi.
    again = api.post(f'{BASE_URL}/api/rework/queue/{three_types["source_session_id"]}/resolve',
                     json={'request_id': f'B2-{uuid.uuid4()}', 'employee_id': three_types['employee_id'],
                           'repaired_qty': 5, 'scrapped_qty': 0}, timeout=20)
    assert again.status_code == 409, \
        f'resolve vượt quá số NG còn chờ vẫn được chấp nhận: {again.status_code} {again.text}'
