"""Một tem QR mơ hồ phải bị TỪ CHỐI TỬ TẾ ở cả bốn đường quét.

Resolver (domain/qr_identity.py) đã làm đúng phần khó: nó phát hiện mã cũ giải
ra nhiều hơn một Operation và ném ConflictError thay vì đoán. Nhưng "ném đúng"
mới là nửa đầu. Nửa sau là mỗi nơi gọi phải BIẾN cái ném đó thành thứ người ở
xưởng và thiết bị hiểu được:

  * kiosk v1 (web) trả phong bì có error_code + action, để kiosk.js in ra câu
    hướng dẫn thay vì một màn hình lỗi trống.
  * kiosk v2 (ESP) trả đúng phong bì giao thức với MỘT mã lỗi nghiệp vụ. Đây
    là chỗ nguy hiểm nhất: nếu ConflictError rơi ra ngoài vào nhánh bắt-tất-cả
    thì thiết bị nhận INTERNAL_ERROR + action=RETRY + HTTP 503, tức là được
    BẢO HÃY THỬ LẠI một việc không bao giờ thành công. Tem trùng không tự hết
    theo thời gian; nó cần người in lại tem. Thiết bị sẽ quay vòng cho tới khi
    hết lượt, và không ai biết phải sửa gì.
  * offline sync giữ sự kiện lại (không mất công của ca làm) nhưng phải gắn
    một reason_code RIÊNG, để người trực còn tìm ra chúng.

Ca mơ hồ dựng lại bằng đúng đường vào có thật: đổi tên mã của một Operation
(operations.qr CỐ Ý không bị viết lại, tem đã in phải quét được tiếp), rồi mã
vừa giải phóng được cấp cho một Operation khác. Từ lúc đó 'WF|OP|<mã>' khớp
`qr` của hàng cũ VÀ `code` của hàng mới.
"""
from __future__ import annotations

import hashlib
import uuid

import pytest
import requests

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


@pytest.fixture
def ambiguous_legacy_qr(db):
    """Hai Operation mà một tem cũ 'WF|OP|<mã>' cùng trỏ tới.

    Trả về mã đó, id của cả hai hàng, và một kiosk v1/v2 đã đăng ký sẵn.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    code = f'AMB-{suffix}'
    device_id = f'V2-AMB-{suffix}'
    token = f'TEST-KIOSK-TOKEN-{suffix}'
    ids = {'code': code, 'suffix': suffix, 'device_id': device_id, 'token': token}
    with db.cursor() as cur:
        cur.execute("""INSERT INTO production_orders(code,product,planned_quantity,status)
            VALUES(%s,'SP',100,'IN_PROGRESS') RETURNING id""", (f'PO-AMB-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name,sort_order) VALUES(%s,'PARTA','A',0) RETURNING id",
                    (po_id,))
        part_a = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name,sort_order) VALUES(%s,'PARTB','B',1) RETURNING id",
                    (po_id,))
        part_b = cur.fetchone()['id']

        # Hàng 1 mang mã đó, rồi ĐỔI TÊN -- qr giữ nguyên 'WF|OP|<mã>'.
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Cắt A','IN_PROGRESS',%s,0) RETURNING id""",
            (po_id, part_a, code, f'WF|OP|{code}'))
        ids['old_id'] = cur.fetchone()['id']
        cur.execute("UPDATE operations SET code=%s WHERE id=%s", (f'{code}-OLD', ids['old_id']))

        # Hàng 2 nhận lại mã vừa giải phóng, với tem theo id.
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
            VALUES(%s,%s,%s,'Cắt B','IN_PROGRESS',%s,0) RETURNING id""",
            (po_id, part_b, code, f'WF|OPID|PENDING-{suffix}'))
        ids['new_id'] = cur.fetchone()['id']
        cur.execute("UPDATE operations SET qr=%s WHERE id=%s", (f"WF|OPID|{ids['new_id']}", ids['new_id']))

        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr,active)
            VALUES(%s,'Công nhân','TEST','Worker',%s,true) RETURNING id""",
            (f'EMP-AMB-{suffix}', f'WF|EMP|EMP-AMB-{suffix}'))
        ids['employee_id'] = cur.fetchone()['id']
        cur.execute("""INSERT INTO stations(code,name,workshop,production_line)
            VALUES(%s,'Trạm AMB','TEST','TEST') RETURNING id""", (f'ST-AMB-{suffix}',))
        ids['station_id'] = cur.fetchone()['id']
        ids['station_code'] = f'ST-AMB-{suffix}'

        cur.execute("""INSERT INTO kiosk_identities(device_uuid,device_name,status,token_hash,last_seen_at)
            VALUES(%s,'Kiosk AMB','ACTIVE',%s,CURRENT_TIMESTAMP)""",
            (device_id, hashlib.sha256(token.encode()).hexdigest()))
    ids['po_id'] = po_id
    yield ids
    with db.cursor() as cur:
        cur.execute("DELETE FROM kiosk_v2_events WHERE device_id=%s", (device_id,))
        cur.execute("DELETE FROM kiosk_v2_projection WHERE device_id=%s", (device_id,))
        cur.execute("DELETE FROM kiosk_identities WHERE device_uuid=%s", (device_id,))
        cur.execute("DELETE FROM kiosk_client_events WHERE kiosk_id=%s", (device_id,))
        cur.execute("DELETE FROM kiosk_events WHERE operation_id = ANY(%s)",
                    ([ids['old_id'], ids['new_id']],))
        cur.execute("DELETE FROM work_sessions WHERE employee_id=%s", (ids['employee_id'],))
        cur.execute("DELETE FROM operations WHERE id = ANY(%s)", ([ids['old_id'], ids['new_id']],))
        cur.execute("DELETE FROM parts WHERE production_order_id=%s", (po_id,))
        cur.execute("DELETE FROM production_orders WHERE id=%s", (po_id,))
        cur.execute("DELETE FROM stations WHERE id=%s", (ids['station_id'],))
        cur.execute("DELETE FROM employees WHERE id=%s", (ids['employee_id'],))


def test_the_fixture_really_is_ambiguous(ambiguous_legacy_qr):
    """Chốt lại tiền đề: nếu resolver hết mơ hồ thì mọi bài dưới đây vô nghĩa."""
    from mesflow.db.repositories.base import ConflictError
    from mesflow.domain.qr_identity import resolve_operation_id

    with pytest.raises(ConflictError):
        resolve_operation_id(f"WF|OP|{ambiguous_legacy_qr['code']}")
    # Và cả hai vẫn giải được tuyệt đối bằng id.
    assert resolve_operation_id(f"WF|OPID|{ambiguous_legacy_qr['old_id']}") == ambiguous_legacy_qr['old_id']
    assert resolve_operation_id(f"WF|OPID|{ambiguous_legacy_qr['new_id']}") == ambiguous_legacy_qr['new_id']


def test_kiosk_v1_scan_returns_the_error_envelope_not_a_crash(api, ambiguous_legacy_qr):
    """kiosk v1: phải là phong bì lỗi có error_code + action, không phải 500 trống."""
    response = api.post(f'{BASE_URL}/api/kiosk-web/scan',
                        json={'qr': f"WF|OP|{ambiguous_legacy_qr['code']}"}, timeout=10)
    assert response.status_code == 409, (
        f'mong đợi 409 (đụng độ nghiệp vụ), nhận {response.status_code}: {response.text[:300]}')
    body = response.json()
    assert body.get('ok') is False
    # kiosk.js tra bảng theo error_code để in câu hướng dẫn; thiếu nó thì màn
    # hình kiosk không nói được gì.
    assert body.get('error_code'), f'thiếu error_code: {body}'
    assert body.get('error') == 'AMBIGUOUS_QR', body
    action = str(body.get('action') or '')
    assert 'in lại tem' in action.lower(), f'action phải chỉ ra việc cần làm: {body}'


def test_kiosk_v2_scan_is_a_business_rejection_never_a_retry(api, ambiguous_legacy_qr):
    """kiosk v2: KHÔNG được biến thành INTERNAL_ERROR + RETRY.

    Đây là bài quan trọng nhất của file. Bảo thiết bị thử lại một tem trùng là
    bảo nó quay vòng vô ích cho tới RETRY_EXHAUSTED, trong khi thứ duy nhất
    chữa được là người in lại tem.
    """
    device_id = ambiguous_legacy_qr['device_id']
    headers = {'X-Kiosk-Token': ambiguous_legacy_qr['token']}

    def send(scan_value):
        body = {
            'protocol_version': 1,
            'device': {'device_id': device_id, 'hardware_id': device_id},
            'event': {'event_id': uuid.uuid4().hex, 'type': 'SCAN', 'device_seq': 1},
            'context': {},
            'payload': {'raw': scan_value, 'station_code': ambiguous_legacy_qr['station_code']},
        }
        return requests.post(f'{BASE_URL}/api/kiosk/v2/events', json=body, headers=headers, timeout=10)

    # Quét thẻ nhân viên trước để máy vào đúng trạng thái chờ Operation.
    employee_scan = send(f"WF|EMP|EMP-AMB-{ambiguous_legacy_qr['suffix']}")
    assert employee_scan.status_code == 200, employee_scan.text
    assert employee_scan.json().get('accepted') is True, employee_scan.text

    response = send(f"WF|OP|{ambiguous_legacy_qr['code']}")
    assert response.status_code == 200, (
        f'phải là phong bì giao thức 200 với accepted=false, nhận {response.status_code}: '
        f'{response.text[:300]}')
    body = response.json()
    assert body.get('accepted') is False, body
    assert body.get('event_id'), f'phong bì thiếu event_id: {body}'
    error = body.get('error') or {}
    assert error.get('code') != 'INTERNAL_ERROR', (
        'tem trùng bị xếp thành lỗi hệ thống -- thiết bị sẽ thử lại mãi: ' + str(body))
    assert body.get('action') != 'RETRY', (
        'thiết bị được bảo RETRY một việc không bao giờ thành công: ' + str(body))
    assert error.get('code') == 'AMBIGUOUS_QR', body
    assert body.get('state', {}).get('version'), f'phong bì thiếu state.version: {body}'
    # Máy vẫn đứng ở WAIT_OPERATION: người quét vẫn đang đăng nhập, chỉ cần
    # quét đúng tem là chạy tiếp -- không bắt họ quét lại thẻ nhân viên.
    assert body['state']['name'] == 'WAIT_OPERATION', body


def test_kiosk_v2_still_accepts_the_id_based_label_for_the_same_operation(api, ambiguous_legacy_qr):
    """Tem theo id vẫn chạy bình thường -- chỉ tem cũ trùng mới bị chặn."""
    device_id = ambiguous_legacy_qr['device_id']
    headers = {'X-Kiosk-Token': ambiguous_legacy_qr['token']}

    def send(scan_value):
        body = {
            'protocol_version': 1,
            'device': {'device_id': device_id, 'hardware_id': device_id},
            'event': {'event_id': uuid.uuid4().hex, 'type': 'SCAN', 'device_seq': 1},
            'context': {},
            'payload': {'raw': scan_value, 'station_code': ambiguous_legacy_qr['station_code']},
        }
        return requests.post(f'{BASE_URL}/api/kiosk/v2/events', json=body, headers=headers, timeout=10)

    assert send(f"WF|EMP|EMP-AMB-{ambiguous_legacy_qr['suffix']}").json().get('accepted') is True
    response = send(f"WF|OPID|{ambiguous_legacy_qr['new_id']}")
    assert response.status_code == 200, response.text
    assert response.json().get('accepted') is True, response.text


def test_offline_event_with_ambiguous_qr_is_kept_and_labelled(api, db, ambiguous_legacy_qr):
    """Offline: giữ sự kiện lại (không mất công của ca) và gắn nhãn tìm được.

    Mất một sự kiện offline là mất công có thật của một người đã làm. Nhưng
    'retryable' chung chung thì không ai tìm ra chúng -- reason_code phải nói
    rõ đây là tem trùng, việc cần làm là in lại tem.
    """
    kiosk = ambiguous_legacy_qr['device_id']
    suffix = ambiguous_legacy_qr['suffix']
    event_id = f'{kiosk}-AMB-000001'
    event = {
        'schema_version': 1,
        'client_event_id': event_id,
        'local_sequence': 1,
        'local_session_id': f'LOCAL-{suffix}',
        'session_trace_id': f'LOCAL-{suffix}',
        'event_type': 'START',
        'worker_qr': f'WF|EMP|EMP-AMB-{suffix}',
        'operation_qr': f"WF|OP|{ambiguous_legacy_qr['code']}",
        'good_qty': 0, 'defect_qty': 0, 'repairable_qty': 0, 'scrap_qty': 0,
        'time_quality': 'unknown', 'boot_id': 'TEST-BOOT', 'device_uptime_ms': 100,
        'offline_snapshot_revision': 'TEST-REVISION', 'offline': True,
    }
    response = api.post(f'{BASE_URL}/api/kiosk/offline-sync', json={
        'device_id': kiosk, 'station_code': ambiguous_legacy_qr['station_code'], 'events': [event],
    }, timeout=30)
    assert response.status_code == 200, response.text

    with db.cursor() as cur:
        cur.execute("SELECT status,reason_code,reason FROM kiosk_client_events WHERE client_event_id=%s",
                    (event_id,))
        row = cur.fetchone()
    assert row, 'sự kiện offline biến mất -- đó là mất dữ liệu sản xuất'
    assert row['status'] != 'accepted', (
        'sự kiện mơ hồ được CHẤP NHẬN -- nghĩa là nó vừa ghi vào một Operation đoán bừa')
    assert row['reason_code'] == 'AMBIGUOUS_OPERATION_QR', (
        f"reason_code phải nói rõ là tem trùng, đang là {row['reason_code']!r}: {row['reason']!r}")

    # Và tuyệt đối không có session nào được mở trên một trong hai Operation.
    with db.cursor() as cur:
        cur.execute("""SELECT COUNT(*) n FROM work_sessions
            WHERE operation_id = ANY(%s)""", ([ambiguous_legacy_qr['old_id'], ambiguous_legacy_qr['new_id']],))
        assert cur.fetchone()['n'] == 0, 'đã mở session trên một Operation đoán bừa'


# ---------------------------------------------------------------- Thẻ nhân viên

@pytest.fixture
def ambiguous_employee_badge(db):
    """Một chuỗi thẻ trỏ tới HAI nhân viên.

    `employees.employee_no` và `employees.qr` unique riêng lẻ nhưng không
    unique chéo nhau. Dựng bằng đúng API quản trị: `qr` là cột ghi được, nên
    người A có thể mang tem 'WF|EMP|<mã của người B>' trong khi người B giữ
    một tem thẻ từ khác. Từ lúc đó chuỗi ấy khớp A theo `qr` và B theo
    `employee_no`.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    badge = f'WF|EMP|E2-{suffix}'
    ids = {'suffix': suffix, 'badge': badge}
    with db.cursor() as cur:
        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr,active)
            VALUES(%s,'Người A','TEST','Worker',%s,true) RETURNING id""",
            (f'E1-{suffix}', badge))
        ids['wrong_id'] = cur.fetchone()['id']
        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr,active)
            VALUES(%s,'Người B','TEST','Worker',%s,true) RETURNING id""",
            (f'E2-{suffix}', f'BADGE-{suffix}'))
        ids['right_id'] = cur.fetchone()['id']
    yield ids
    with db.cursor() as cur:
        cur.execute("DELETE FROM employees WHERE id = ANY(%s)", ([ids['wrong_id'], ids['right_id']],))


def test_a_badge_matching_two_employees_is_refused_not_guessed(ambiguous_employee_badge):
    """LIMIT 1 cũ chọn theo thứ tự vật lý của bảng -- tức là chọn NHẦM NGƯỜI.

    Hậu quả không phải một màn hình lỗi: công của cả ca ghi sang tên người
    khác, sai lương, sai năng suất, và không có gì bật lên vì với hệ thống thì
    mọi thứ đều hợp lệ.
    """
    from mesflow.domain.qr_identity import AmbiguousEmployeeQR, resolve_employee_id

    with pytest.raises(AmbiguousEmployeeQR) as exc:
        resolve_employee_id(ambiguous_employee_badge['badge'])
    assert f"E1-{ambiguous_employee_badge['suffix']}" in str(exc.value)
    assert f"E2-{ambiguous_employee_badge['suffix']}" in str(exc.value)


def test_kiosk_v1_employee_scan_returns_the_error_envelope(api, ambiguous_employee_badge):
    response = api.post(f'{BASE_URL}/api/kiosk-web/scan',
                        json={'qr': ambiguous_employee_badge['badge']}, timeout=10)
    assert response.status_code == 409, f'{response.status_code}: {response.text[:300]}'
    body = response.json()
    assert body.get('error') == 'AMBIGUOUS_QR', body
    assert body.get('error_code') == 'EMP-002', body
    assert body.get('action'), body


def test_an_unambiguous_badge_still_resolves_both_ways(db):
    """Không được làm hỏng đường thường: quét theo qr và theo mã NV đều chạy."""
    from mesflow.domain.qr_identity import resolve_employee_id

    suffix = uuid.uuid4().hex[:8].upper()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr,active)
            VALUES(%s,'Người thường','TEST','Worker',%s,true) RETURNING id""",
            (f'OK-{suffix}', f'WF|EMP|OK-{suffix}'))
        employee_id = cur.fetchone()['id']
    try:
        assert resolve_employee_id(f'WF|EMP|OK-{suffix}') == employee_id
        assert resolve_employee_id(f'OK-{suffix}') == employee_id
    finally:
        with db.cursor() as cur:
            cur.execute("DELETE FROM employees WHERE id=%s", (employee_id,))


def test_an_inactive_employee_is_not_resolved(db):
    """Nghỉ việc thì thẻ không còn mở được session -- hành vi cũ, giữ nguyên."""
    from mesflow.db.repositories.base import NotFoundError
    from mesflow.domain.qr_identity import resolve_employee_id

    suffix = uuid.uuid4().hex[:8].upper()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr,active)
            VALUES(%s,'Đã nghỉ','TEST','Worker',%s,false) RETURNING id""",
            (f'OFF-{suffix}', f'WF|EMP|OFF-{suffix}'))
        employee_id = cur.fetchone()['id']
    try:
        with pytest.raises(NotFoundError):
            resolve_employee_id(f'WF|EMP|OFF-{suffix}')
    finally:
        with db.cursor() as cur:
            cur.execute("DELETE FROM employees WHERE id=%s", (employee_id,))
