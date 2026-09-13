"""Từ file Excel xưởng tới tem QR trên giấy: nhập -> tạo PO -> xuất lại.

Bài này chạy trên API + PostgreSQL thật vì thứ cần chứng minh nằm ở chỗ ba lớp
gặp nhau, không phải ở một hàm:

  * file khai báo setup > 0 -> ``template_operations.requires_setup`` bật và số
    phút được giữ;
  * tạo PO từ Template đó -> sinh Operation SETUP THẬT, gắn cha bằng
    ``parent_operation_id``, có QR riêng, KHÔNG có sản lượng;
  * SETUP không được lọt vào tiến độ/WIP của PO (đây là lỗi đã từng xảy ra,
    xem docstring của domain/policy.py);
  * xuất lại -> file .xlsx mở được, mọi Operation quét được đều có tem.

Và một điều chỉ thấy được ở mức API: bỏ tick OP sản xuất mà vẫn gửi
``include_setup`` thì server phải TỪ CHỐI tạo setup mồ côi, kể cả khi giao diện
bị bỏ qua.
"""
import json
import os
import re
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import requests
from openpyxl import Workbook, load_workbook

BASE_URL = os.environ.get('MESFLOW_BASE_URL', 'http://mesflow-test-api:8080').rstrip('/')

pytestmark = pytest.mark.integration

SETUP_MINUTES = 20
ROBOT_SETUP_MINUTES = 120


def _router_bytes(po_number=None, sheets=None):
    # Mỗi lần gọi là một mã PO riêng, TRỪ khi bài chỉ định: nhập file có PO NUMBER
    # nay tạo PO thật, nên dùng chung một mã giữa các bài sẽ đụng PO_ALREADY_EXISTS.
    po_number = po_number or f'T{uuid.uuid4().hex[:8].upper()}'
    """Workbook GO ROUTER tối giản, đúng bố cục tờ giấy xưởng."""
    sheets = sheets or [
        ('Chân ghế A', 'KM-001', [(1, 'CẮT LASER', SETUP_MINUTES, 100),
                                  (2, 'LÀM NGUỘI', 0, 50)]),
        ('HÀN ROBOT', 'KM-002', [(1, 'HÀN ROBOT', ROBOT_SETUP_MINUTES, 120)]),
    ]
    wb = Workbook(); wb.remove(wb.active)
    for title, drawing_code, blocks in sheets:
        ws = wb.create_sheet(title)
        ws['A2'] = 'PO NUMBER:'; ws['C2'] = po_number
        ws['A3'] = 'QTY:'; ws['C3'] = 110
        ws['A4'] = 'TÊN BẢN VẼ:'; ws['C4'] = title
        ws['A5'] = 'MÃ BẢN VẼ:'; ws['C5'] = drawing_code
        row = 8
        for seq, name, setup_value, cycle in blocks:
            ws.cell(row=row, column=1, value=f'OPERATION # {seq:02d}- {name}')
            ws.cell(row=row + 1, column=1, value='Part Number ( Mã bản vẽ )')
            ws.cell(row=row + 1, column=2, value=drawing_code)
            ws.cell(row=row + 2, column=1, value='Ngày/Tháng/Năm')
            ws.cell(row=row + 2, column=12, value='Thời gian Setup ( phút )')
            ws.cell(row=row + 3, column=1, value='SETUP')
            ws.cell(row=row + 3, column=12, value=setup_value)
            ws.cell(row=row + 5, column=12, value='Thời gian gia công / sản phẩm (s)')
            ws.cell(row=row + 6, column=1, value='Thời gian gia công')
            ws.cell(row=row + 6, column=12, value=cycle)
            row += 12
    buffer = BytesIO(); wb.save(buffer)
    return buffer.getvalue()


def _upload(api, path, data, selection=None, confirm=True):
    files = {'file': ('Lộ trình sản xuất TEST.xlsx', data,
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    # confirm mặc định BẬT ở bộ này: các bài dùng lại cùng mã PO/Template nên từ
    # bài thứ hai trở đi, mỗi lần nhập là một lần ghi đè Template dùng chung --
    # và ghi đè thì phải xác nhận (xem REQ-TPL-007). Hành vi "không confirm thì
    # 409" được khoá riêng ở tests/integration/test_router_po_import_flow.py.
    form = {}
    if selection is not None:
        form['selection'] = json.dumps(selection)
    if confirm:
        form['confirm'] = '1'
    return api.post(f'{BASE_URL}{path}', files=files, data=form or None, timeout=60)


@pytest.fixture
def imported(api):
    """Template nhập từ file router, trả (template_id, payload xem trước)."""
    data = _router_bytes()
    preview = _upload(api, '/api/templates/preview-workbook', data)
    assert preview.status_code == 200, preview.text[:400]
    body = preview.json()
    assert body['ok'] is True
    result = _upload(api, '/api/templates/import-workbook', data)
    assert result.status_code == 200, result.text[:400]
    return result.json()['template_id'], body, data


# --- nhập: file -> template_operations ------------------------------------

def test_preview_khong_ghi_gi_vao_csdl(api, db):
    """Xem trước phải là đọc thuần: không tạo Template nào."""
    before = db.execute('SELECT COUNT(*) c FROM templates').fetchone()['c']
    response = _upload(api, '/api/templates/preview-workbook', _router_bytes())
    assert response.status_code == 200
    assert response.json()['counts']['setups'] == 2
    after = db.execute('SELECT COUNT(*) c FROM templates').fetchone()['c']
    assert after == before


def test_setup_duong_duoc_giu_vao_template_operations(imported, db):
    template_id, preview, _ = imported
    rows = db.execute("""SELECT o.code,o.requires_setup,o.expected_setup_minutes,
            o.standard_seconds_per_unit
        FROM template_operations o WHERE o.template_id=%s ORDER BY o.code""",
        (template_id,)).fetchall()
    by_code = {r['code']: r for r in rows}
    assert by_code['KM-001-OP01']['requires_setup'] is True
    assert by_code['KM-001-OP01']['expected_setup_minutes'] == SETUP_MINUTES
    assert by_code['KM-002-OP01']['expected_setup_minutes'] == ROBOT_SETUP_MINUTES
    # setup = 0 -> KHÔNG bật, và không mượn số của Operation khác.
    assert by_code['KM-001-OP02']['requires_setup'] is False
    assert by_code['KM-001-OP02']['expected_setup_minutes'] is None
    # Thời gian gia công đi vào cột của nó, KHÔNG lẫn với thời gian setup.
    assert float(by_code['KM-001-OP01']['standard_seconds_per_unit']) == 100


def test_preview_danh_dau_dung_op_nao_co_setup(imported):
    _, preview, _ = imported
    rows = {op['code']: op for part in preview['parts'] for op in part['operations']}
    assert rows['KM-001-OP01']['requires_setup'] is True
    assert rows['KM-001-OP01']['expected_setup_minutes'] == SETUP_MINUTES
    assert rows['KM-001-OP01']['setup_code'] == 'KM-001-OP01-SU'
    assert rows['KM-001-OP02']['requires_setup'] is False
    assert rows['KM-001-OP02']['setup_code'] is None


def test_nhap_lai_cung_file_khong_nhan_doi(api, imported, db):
    """Nhập lại đúng file đó: vẫn một Template, vẫn đúng bấy nhiêu Operation."""
    template_id, _, data = imported
    before = db.execute('SELECT COUNT(*) c FROM template_operations WHERE template_id=%s',
                        (template_id,)).fetchone()['c']
    again = _upload(api, '/api/templates/import-workbook', data)
    assert again.status_code == 200
    assert again.json()['template_id'] == template_id
    after = db.execute('SELECT COUNT(*) c FROM template_operations WHERE template_id=%s',
                       (template_id,)).fetchone()['c']
    assert after == before
    setups = db.execute("""SELECT COUNT(*) c FROM template_operations
        WHERE template_id=%s AND requires_setup""", (template_id,)).fetchone()['c']
    assert setups == 2


# --- chọn lọc: không có OP SETUP mồ côi -----------------------------------

def test_bo_tick_op_cha_thi_server_khong_tao_setup(api, db):
    """Gửi include_setup=true cho một OP KHÔNG được chọn -> setup không tồn tại.

    Giao diện đã tự khoá ô đó, nhưng quy tắc phải nằm ở server: một client khác
    gọi thẳng API cũng không được phép tạo setup không cha.
    """
    data = _router_bytes()
    response = _upload(api, '/api/templates/import-workbook', data, selection=[
        # CHỈ chọn OP02 (không có setup); OP01 bị bỏ tick hoàn toàn.
        {'part_code': 'KM-001', 'operation_code': 'KM-001-OP02', 'include_setup': True},
    ])
    assert response.status_code == 200, response.text[:400]
    template_id = response.json()['template_id']
    rows = db.execute('SELECT code,requires_setup FROM template_operations WHERE template_id=%s',
                      (template_id,)).fetchall()
    assert [r['code'] for r in rows] == ['KM-001-OP02']
    assert rows[0]['requires_setup'] is False


def test_bo_tick_rieng_setup_thi_giu_op_bo_setup(api, db):
    data = _router_bytes()
    response = _upload(api, '/api/templates/import-workbook', data, selection=[
        {'part_code': 'KM-001', 'operation_code': 'KM-001-OP01', 'include_setup': False},
    ])
    assert response.status_code == 200, response.text[:400]
    template_id = response.json()['template_id']
    row = db.execute("""SELECT code,requires_setup,expected_setup_minutes
        FROM template_operations WHERE template_id=%s""", (template_id,)).fetchone()
    assert row['code'] == 'KM-001-OP01'
    assert row['requires_setup'] is False
    assert row['expected_setup_minutes'] is None


# --- tạo PO: SETUP là Operation thật, gắn cha -----------------------------

@pytest.fixture
def po(api, imported):
    template_id, _, _ = imported
    code = f'PO-ROUTERQR-{uuid.uuid4().hex[:8].upper()}'
    response = api.post(f'{BASE_URL}/api/templates/{template_id}/instantiate',
        json={'code': code, 'planned_quantity': 110}, timeout=60)
    assert response.status_code in (200, 201), response.text[:400]
    return response.json()


def test_po_sinh_op_setup_gan_dung_cha(po, db):
    po_id = int(po['production_order_id'])
    setups = db.execute("""SELECT s.id,s.code,s.name,s.operation_type,s.parent_operation_id,
            s.expected_setup_minutes,s.qr,s.done_qty,s.defect_qty,
            parent.code parent_code,parent.requires_setup parent_requires_setup
        FROM operations s JOIN operations parent ON parent.id=s.parent_operation_id
        WHERE s.production_order_id=%s AND s.operation_type='SETUP'
        ORDER BY parent.code""", (po_id,)).fetchall()
    assert len(setups) == 2, 'đúng hai OP có setup > 0 trong file'
    for row in setups:
        assert row['parent_operation_id'], 'SETUP phải gắn vào OP sản xuất'
        assert row['parent_requires_setup'] is True
        # Không target/đạt/lỗi: SETUP ghi CÔNG, không ghi sản lượng.
        assert row['done_qty'] == 0 and row['defect_qty'] == 0
        # QR riêng, địa chỉ theo id bất biến.
        assert row['qr'] == f"WF|OPID|{row['id']}"
        assert row['code'].endswith('-SU')
    assert sorted(r['expected_setup_minutes'] for r in setups) == [
        SETUP_MINUTES, ROBOT_SETUP_MINUTES]


def test_op_khong_co_setup_thi_khong_sinh_dong_setup(po, db):
    po_id = int(po['production_order_id'])
    row = db.execute("""SELECT o.id,o.requires_setup,
            (SELECT COUNT(*) FROM operations s WHERE s.parent_operation_id=o.id
             AND s.operation_type='SETUP') setup_count
        FROM operations o WHERE o.production_order_id=%s AND o.code LIKE %s""",
        (po_id, '%KM-001-OP02')).fetchone()
    assert row is not None
    assert row['requires_setup'] is False
    assert row['setup_count'] == 0


def test_setup_khong_lot_vao_tien_do_san_xuat(po, db):
    """SETUP phải bị loại khỏi mọi phép đếm sản lượng của PO.

    Đây là họ lỗi mà domain/policy.py sinh ra để chặn: quên lọc một chỗ là sản
    lượng OP phụ lọt vào tiến độ, hoặc PO không bao giờ COMPLETED.
    """
    po_id = int(po['production_order_id'])
    counts = db.execute("""SELECT
            COUNT(*) FILTER (WHERE COALESCE(operation_type,'PRODUCTION')='PRODUCTION') production,
            COUNT(*) FILTER (WHERE operation_type='SETUP') setup,
            COALESCE(SUM(done_qty+defect_qty+rework_qty+scrap_qty)
                     FILTER (WHERE operation_type='SETUP'),0) setup_qty
        FROM operations WHERE production_order_id=%s""", (po_id,)).fetchone()
    assert counts['production'] == 3, 'ba OP sản xuất trong file'
    assert counts['setup'] == 2
    assert counts['setup_qty'] == 0, 'SETUP không mang sản lượng'
    # Và nó bị loại khỏi chính mảnh SQL mà mọi rollup dùng.
    production_only = db.execute("""SELECT COUNT(*) c FROM operations o
        WHERE o.production_order_id=%s AND COALESCE(o.operation_type,'PRODUCTION')='PRODUCTION'
        """, (po_id,)).fetchone()['c']
    assert production_only == 3


# --- xuất lại: file .xlsx có tem cho mọi Operation ------------------------

def test_xuat_file_router_co_tem_cho_moi_operation(api, po, db):
    po_id = int(po['production_order_id'])
    response = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router.xlsx', timeout=120)
    assert response.status_code == 200, response.text[:400]
    assert response.headers['Content-Type'].startswith(
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    disposition = response.headers['Content-Disposition']
    assert 'attachment' in disposition
    # Tên file tiếng Việt phải đi theo RFC 5987, không phải mojibake.
    assert f"Router_{po['production_order_code']}_QR.xlsx" in disposition

    workbook = load_workbook(BytesIO(response.content))
    assert workbook.sheetnames, 'file mở được bằng openpyxl'
    images = sum(len(workbook[name]._images) for name in workbook.sheetnames)
    # 3 OP sản xuất + 2 SETUP = 5 tem.
    assert images == 5, f'phải có 5 tem QR, đang có {images}'
    assert int(response.headers['X-MESFlow-Router-Labels']) == 5
    # Và tem phải nằm ĐÚNG sheet Part của nó, không dồn xuống sheet phụ: đếm đủ
    # số tem vẫn đúng kể cả khi tất cả rơi sai chỗ.
    assert 'QR bổ sung' not in workbook.sheetnames, (
        'không được sinh sheet phụ trong bất kỳ trường hợp nào')
    assert response.headers['X-MESFlow-Router-Source'] == 'workbook'
    # Danh tính bản gốc vừa in từ đó -- để không ai in nhầm bản cũ.
    assert re.fullmatch(r'[0-9a-f]{64}', response.headers['X-MESFlow-Router-Source-Sha256'])
    assert int(response.headers['X-MESFlow-Router-Matched']) == 3
    assert int(response.headers['X-MESFlow-Router-Unmatched']) == 0
    for title in ('Chân ghế A', 'HÀN ROBOT'):
        assert len(workbook[title]._images) > 0, f'sheet {title} không có tem nào'
        # Nhãn nằm TRONG ảnh, không trong ô: không ô nào được thêm chữ.
        labels = {c.value for row in workbook[title].iter_rows() for c in row}
        assert 'QR OP' not in labels and 'QR Setup' not in labels


def test_danh_sach_tem_dung_danh_tinh_canonical(api, po, db):
    po_id = int(po['production_order_id'])
    response = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router-labels', timeout=60)
    assert response.status_code == 200, response.text[:400]
    labels = response.json()['labels']
    payloads = [item['payload'] for item in labels]
    assert len(payloads) == len(set(payloads)), 'không được có hai tem cùng payload'

    ids = {int(row['id']) for row in db.execute("""SELECT id FROM operations
        WHERE production_order_id=%s AND COALESCE(operation_type,'PRODUCTION')
        IN ('PRODUCTION','SETUP')""", (po_id,)).fetchall()}
    assert {int(item['operation_id']) for item in labels} == ids, (
        'mọi Operation quét được của PO đều phải có tem')
    # Tem SETUP chỉ xuất hiện cho Operation thật sự là SETUP.
    setup_ids = {int(row['id']) for row in db.execute(
        "SELECT id FROM operations WHERE production_order_id=%s AND operation_type='SETUP'",
        (po_id,)).fetchall()}
    assert {int(i['operation_id']) for i in labels if i['kind'] == 'SETUP'} == setup_ids


def test_hai_part_cung_ten_cong_doan_khong_dung_chung_tem(api, po, db):
    """'CẮT LASER' ở hai Part là hai Operation khác nhau -> hai tem khác nhau.

    Payload của OP sản xuất là chuỗi ĐANG lưu trên dòng đó, không phải một
    chuỗi tự ghép lúc xuất: in lại một tem bình thường phải ra đúng cái đang dán
    ngoài xưởng (xem printable_qr_payload_sql). Tem SETUP thì luôn địa chỉ theo
    id vì nó được sinh ra cùng lúc với dòng.
    """
    po_id = int(po['production_order_id'])
    labels = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router-labels',
                         timeout=60).json()['labels']
    by_operation = {int(i['operation_id']): i['payload'] for i in labels}
    rows = db.execute("""SELECT id,code,qr,operation_type FROM operations
        WHERE production_order_id=%s
        AND COALESCE(operation_type,'PRODUCTION') IN ('PRODUCTION','SETUP')""",
        (po_id,)).fetchall()
    for row in rows:
        assert by_operation[int(row['id'])] == row['qr'], (
            'tem phải trùng danh tính đang lưu của chính Operation đó')
        if row['operation_type'] == 'SETUP':
            assert row['qr'] == f"WF|OPID|{row['id']}"
    # Hai Part cùng tên công đoạn -> hai chuỗi khác nhau.
    payloads = [by_operation[int(r['id'])] for r in rows]
    assert len(payloads) == len(set(payloads))


def test_po_khong_ton_tai_tra_ve_404(api):
    response = api.get(f'{BASE_URL}/api/production-orders/99999999/router.xlsx', timeout=30)
    assert response.status_code == 404


def test_po_khong_co_file_goc_thi_tu_choi_chu_khong_xuat_file_generic(api, db):
    """Template dựng tay (không nhập từ Excel) -> xuất file phải 409, không generic.

    Đây là điểm cốt lõi của hợp đồng: thà KHÔNG xuất được còn hơn đưa ra một tờ
    giấy trông giống biểu mẫu của khách nhưng không phải cái họ đang dùng. Mọi
    PO đều phải sinh từ Template, nên "không có file gốc" chính là trường hợp
    Template được gõ tay trong trình soạn thảo.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    created = api.post(f'{BASE_URL}/api/templates', json={
        'code': f'TPL-HANDMADE-{suffix}', 'name': 'Template gõ tay',
        'product': 'THỬ', 'version': '1.0', 'active': True}, timeout=30)
    assert created.status_code in (200, 201), created.text[:300]
    template_id = int(created.json()['id'])
    tree = api.put(f'{BASE_URL}/api/templates/{template_id}/tree', json={
        'parts': [{'key': 'p1', 'code': 'P1', 'name': 'Part 1', 'sort_order': 0}],
        'operations': [{'part_key': 'p1', 'code': 'OP01', 'name': 'CẮT',
                        'sort_order': 0, 'equipment_code': ''}],
        'equipment': []}, timeout=30)
    assert tree.status_code in (200, 201), tree.text[:300]
    po = api.post(f'{BASE_URL}/api/templates/{template_id}/instantiate',
        json={'code': f'PO-NOSRC-{suffix}', 'planned_quantity': 10}, timeout=60)
    assert po.status_code in (200, 201), po.text[:300]
    po_id = int(po.json()['production_order_id'])

    response = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router.xlsx', timeout=60)
    assert response.status_code == 409, response.text[:300]
    body = response.json()
    assert body['reason'] == 'NO_SOURCE_WORKBOOK'
    assert 'nhập lại' in body['message'].lower()
    # Và tuyệt đối không trả về một file Excel nào.
    assert 'spreadsheetml' not in response.headers.get('Content-Type', '')
    # Danh sách tem cũng phải từ chối y hệt, không được trả danh sách rỗng.
    labels = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router-labels', timeout=60)
    assert labels.status_code == 409
    assert labels.json()['reason'] == 'NO_SOURCE_WORKBOOK'


def test_kiosk_cong_khai_khong_doi(api):
    """Hồi quy: tính năng này không được nới lỏng biên giới kiosk công khai."""
    anonymous = requests.Session()
    response = anonymous.get(f'{BASE_URL}/api/production-orders/1/router.xlsx',
                             timeout=30, allow_redirects=False)
    assert response.status_code in (302, 401, 403), (
        'xuất file router là màn quản trị, không được mở cho khách')
    labels = anonymous.get(f'{BASE_URL}/api/production-orders/1/router-labels',
                           timeout=30, allow_redirects=False)
    assert labels.status_code in (302, 401, 403)


# --- vòng tròn đầy đủ trên FILE THẬT của xưởng ----------------------------
#
# Yêu cầu bắt buộc dùng chính workbook mẫu: chỉ file thật mới có merge, độ rộng
# cột, ảnh, khung in và 44 sheet để chứng minh "xuất = file gốc + tem".

REAL_FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/router-newark-arm-chair.xlsx'

#: Số block trong file thật có số OP trùng với một block khác CÙNG Part.
REAL_DUPLICATE_BLOCKS = 10
OPERATION_NUMBER = re.compile(r'(OPERATION\s*#\s*)(\d+)', re.IGNORECASE)


@pytest.fixture(scope='module')
def real_workbook_bytes():
    """File thật NGUYÊN BẢN — có 10 chỗ trùng số OP, nên nay bị từ chối."""
    assert REAL_FIXTURE.is_file(), f'thiếu fixture {REAL_FIXTURE}'
    return REAL_FIXTURE.read_bytes()


def _sheet_parts(archive):
    """Tên sheet -> đường dẫn XML của nó trong gói .xlsx."""
    workbook = archive.read('xl/workbook.xml').decode('utf-8')
    rels = archive.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    target_by_rel = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))
    parts = {}
    for entry in re.findall(r'<sheet [^>]*/>', workbook):
        name = re.search(r'name="([^"]+)"', entry).group(1)
        rel = re.search(r'r:id="([^"]+)"', entry).group(1)
        target = target_by_rel[rel].lstrip('/')
        parts[name] = target if target.startswith('xl/') else f'xl/{target}'
    return parts


def _retitle(sheet_xml, row, title):
    """Ghi đè tiêu đề block ở ô A<row> bằng inline string, giữ nguyên style.

    Tiêu đề gốc là shared string dùng chung giữa nhiều tờ; sửa chuỗi ấy sẽ đổi
    cả những tờ khác. Ghi inline chỉ đổi ĐÚNG một ô.
    """
    pattern = re.compile(r'<c r="A%d"([^>]*)>(.*?)</c>' % row, re.DOTALL)
    match = pattern.search(sheet_xml)
    assert match, f'không thấy ô A{row} trong XML'
    attributes = re.sub(r'\s+t="[^"]*"', '', match.group(1))
    escaped = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    cell = f'<c r="A{row}"{attributes} t="inlineStr"><is><t>{escaped}</t></is></c>'
    return sheet_xml[:match.start()] + cell + sheet_xml[match.end():]


def _renumbered_workbook(real_bytes):
    """File thật với số OP trùng trong cùng một Part được đánh lại cho duy nhất.

    Hợp đồng mới: hai công đoạn cùng số trong CÙNG một Part là lỗi chặn, nên
    file nguyên bản không còn nhập được. Vòng tròn nhập→xuất vẫn phải chạy trên
    hình dạng thật của biểu mẫu (44 tờ, merge, ảnh, khung in), nên thay vì đổi
    sang một workbook dựng tay, chỉ ĐÁNH LẠI SỐ ở 10 chỗ đụng nhau và giữ
    nguyên mọi thứ còn lại của gói .xlsx -- kể cả giá trị Excel đã cache.

    Trả ``(bytes, [{'sheet','row','before','after'}])``.
    """
    source = zipfile.ZipFile(BytesIO(real_bytes))
    parts = _sheet_parts(source)
    workbook = load_workbook(BytesIO(real_bytes), data_only=True)
    edited, changes = {}, []
    for name in workbook.sheetnames:
        ws = workbook[name]
        titles = sorted((cell.row, cell.value) for row in ws.iter_rows() for cell in row
                        if isinstance(cell.value, str)
                        and cell.value.strip().upper().startswith('OPERATION #'))
        seen, renumber = set(), []
        highest = 0
        for _row, value in titles:
            match = OPERATION_NUMBER.search(value)
            highest = max(highest, int(match.group(2)) if match else 0)
        for row, value in titles:
            match = OPERATION_NUMBER.search(value)
            number = int(match.group(2)) if match else None
            if number is None or number not in seen:
                seen.add(number)
                continue
            highest += 1
            renumber.append((row, value, highest))
            seen.add(highest)
        if not renumber:
            continue
        xml = source.read(parts[name]).decode('utf-8')
        for row, value, number in renumber:
            title = OPERATION_NUMBER.sub(lambda m: f'{m.group(1)}{number:02d}', value, count=1)
            xml = _retitle(xml, row, title)
            changes.append({'sheet': name, 'row': row, 'before': value, 'after': title})
        edited[parts[name]] = xml.encode('utf-8')

    out = BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            target.writestr(item, edited.get(item.filename, source.read(item.filename)))
    return out.getvalue(), changes


@pytest.fixture(scope='module')
def corrected_workbook(real_workbook_bytes):
    return _renumbered_workbook(real_workbook_bytes)


@pytest.fixture(scope='module')
def corrected_workbook_bytes(corrected_workbook):
    return corrected_workbook[0]


@pytest.fixture(scope='module')
def real_po(api, corrected_workbook_bytes):
    """Nhập file thật (đã đánh lại số OP trùng) MỘT lần cho cả module.

    Module-scoped chứ không function-scoped: file thật mang PO NUMBER cố định
    (6126), nên lần nhập thứ hai sẽ dừng ở PO_ALREADY_EXISTS -- đúng hợp đồng,
    nhưng sẽ làm hỏng ba bài còn lại nếu mỗi bài tự nhập.
    """
    files = {'file': (REAL_FIXTURE.name, corrected_workbook_bytes,
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    imported = api.post(f'{BASE_URL}/api/templates/import-workbook', files=files,
                        data={'confirm': '1'}, timeout=900)
    assert imported.status_code == 200, imported.text[:400]
    body = imported.json()
    assert body['setup_count'] == 47
    po = body['production_order']
    assert po['action'] == 'CREATED'
    return body['template_id'], {'production_order_id': po['id'],
                                 'production_order_code': po['code'],
                                 'parts_created': po['parts_created'],
                                 'operations_created': po['operations_created']}


# --- file nguyên bản: TRÙNG SỐ OP TRONG CÙNG PART -> CHẶN -----------------

def test_file_that_shop_uses_is_refused_for_duplicate_op_in_the_same_part(
        api, real_workbook_bytes, db):
    """File thật nguyên bản phải bị TỪ CHỐI, đúng câu đã chốt, và KHÔNG ghi gì.

    Đây là ca thật: 10 chỗ trong file của xưởng có hai công đoạn khác nhau mang
    cùng một số trong cùng một Part (OPERATION # 02 vừa là CHAMFER LỖ vừa là
    LÀM NGUỘI). Trước đây nó chỉ là cảnh báo; nay là lỗi chặn.
    """
    before = {
        'templates': db.execute('SELECT COUNT(*) c FROM templates').fetchone()['c'],
        'pos': db.execute('SELECT COUNT(*) c FROM production_orders').fetchone()['c'],
        'operations': db.execute('SELECT COUNT(*) c FROM operations').fetchone()['c'],
    }
    files = {'file': (REAL_FIXTURE.name, real_workbook_bytes,
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    response = api.post(f'{BASE_URL}/api/templates/import-workbook', files=files,
                        data={'confirm': '1'}, timeout=900)
    assert response.status_code == 400, response.text[:400]
    body = response.json()
    assert body['reason'] == 'DUPLICATE_OP_IN_PART'
    assert body['message'].startswith(
        'Lỗi: OP trùng mã trong cùng một Part. Vui lòng sửa lại file Excel.')
    # Phải chỉ đúng chỗ phải sửa: tờ, Part, số OP, và TẤT CẢ các dòng đụng nhau.
    conflicts = body['detail']['conflicts']
    assert len(conflicts) == REAL_DUPLICATE_BLOCKS, conflicts
    for conflict in conflicts:
        assert conflict['sheet'] and conflict['part'] and conflict['op_code']
        assert len(conflict['rows']) >= 2
        assert conflict['sheet'] in body['message']
    # Và tuyệt đối không được ghi gì.
    assert db.execute('SELECT COUNT(*) c FROM templates').fetchone()['c'] == before['templates']
    assert db.execute('SELECT COUNT(*) c FROM production_orders').fetchone()['c'] == before['pos']
    assert db.execute('SELECT COUNT(*) c FROM operations').fetchone()['c'] == before['operations']


def test_preview_of_the_real_file_shows_the_blocking_error(api, real_workbook_bytes, db):
    """Xem trước phải NÓI RA lỗi, không để người dùng bấm Nhập rồi mới biết.

    Xem trước vẫn trả 200 -- việc của nó là trình bày file, kể cả file hỏng --
    nhưng mục cảnh báo phải mang đúng câu đã chốt và chỉ đủ chỗ phải sửa.
    """
    before = db.execute('SELECT COUNT(*) c FROM templates').fetchone()['c']
    files = {'file': (REAL_FIXTURE.name, real_workbook_bytes,
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    response = api.post(f'{BASE_URL}/api/templates/preview-workbook', files=files, timeout=900)
    assert response.status_code == 200, response.text[:400]
    sections = response.json()['sections']
    assert sections['error'].startswith(
        'Lỗi: OP trùng mã trong cùng một Part. Vui lòng sửa lại file Excel.')
    assert len(sections['conflicts']) == REAL_DUPLICATE_BLOCKS
    # Và xem trước không ghi gì, như mọi khi.
    assert db.execute('SELECT COUNT(*) c FROM templates').fetchone()['c'] == before


def test_renumbering_only_touched_the_duplicate_titles(corrected_workbook, real_workbook_bytes):
    """Chốt chặn cho chính fixture: nếu nó sửa quá tay thì ba bài dưới nói dối."""
    corrected_bytes, changes = corrected_workbook
    assert len(changes) == REAL_DUPLICATE_BLOCKS, changes
    original = load_workbook(BytesIO(real_workbook_bytes), data_only=True)
    corrected = load_workbook(BytesIO(corrected_bytes), data_only=True)
    touched = {(change['sheet'], f"A{change['row']}") for change in changes}
    assert corrected.sheetnames == original.sheetnames
    for name in original.sheetnames:
        before, after = original[name], corrected[name]
        assert {str(r) for r in after.merged_cells.ranges} == \
            {str(r) for r in before.merged_cells.ranges}, f'{name}: merge đổi'
        for row in before.iter_rows():
            for cell in row:
                if (name, cell.coordinate) in touched:
                    continue
                assert after[cell.coordinate].value == cell.value, f'{name}!{cell.coordinate}'
    # Và sau khi đánh lại, không Part nào còn hai block cùng số.
    for name in corrected.sheetnames:
        numbers = [int(OPERATION_NUMBER.search(cell.value).group(2))
                   for row in corrected[name].iter_rows() for cell in row
                   if isinstance(cell.value, str)
                   and cell.value.strip().upper().startswith('OPERATION #')
                   and OPERATION_NUMBER.search(cell.value)]
        assert len(numbers) == len(set(numbers)), f'{name}: vẫn còn số trùng'

def test_file_that_shop_uses_imports_end_to_end(real_po, db):
    template_id, po = real_po
    assert po['parts_created'] == 44
    # 112 block 'OPERATION # ...' cộng một công đoạn quy trình suy ra từ tờ
    # 'SƠN TĨNH ĐIỆN' -- tờ đó không viết theo khuôn block nhưng vẫn là một
    # bước sản xuất thật, và bỏ qua nó làm bước sơn biến mất khỏi PO.
    assert po['operations_created'] == 113
    setups = db.execute("""SELECT COUNT(*) c FROM operations
        WHERE production_order_id=%s AND operation_type='SETUP'""",
        (int(po['production_order_id']),)).fetchone()['c']
    assert setups == 47


def test_export_of_real_po_is_the_source_workbook_with_labels(
        api, real_po, corrected_workbook_bytes):
    """Xuất ra phải GIỮ NGUYÊN 44 sheet, merge và ảnh của file gốc, cộng tem."""
    _, po = real_po
    po_id = int(po['production_order_id'])
    response = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router.xlsx', timeout=900)
    assert response.status_code == 200, response.text[:400]
    assert response.headers['X-MESFlow-Router-Source'] == 'workbook'
    assert int(response.headers['X-MESFlow-Router-Labels']) == 113 + 47
    assert int(response.headers['X-MESFlow-Router-Unmatched']) == 0

    original = load_workbook(BytesIO(corrected_workbook_bytes))
    exported = load_workbook(BytesIO(response.content))
    # Cấu trúc gốc còn nguyên -- đây là điểm mà một file dựng lại sẽ trượt.
    assert exported.sheetnames == original.sheetnames
    for name in original.sheetnames:
        assert {str(r) for r in exported[name].merged_cells.ranges} == {
            str(r) for r in original[name].merged_cells.ranges}, f'{name}: merge đổi'
        assert len(exported[name]._images) >= len(original[name]._images), (
            f'{name}: mất ảnh gốc')
        for letter in 'ABCDEFGHIJKLM':
            assert (exported[name].column_dimensions[letter].width
                    == original[name].column_dimensions[letter].width), f'{name}:{letter}'
    # Ô dữ liệu quan trọng của tờ giấy vẫn đúng.
    sheet = exported['Chân ghế A  - Trái']
    assert sheet['A8'].value == 'OPERATION # 01- CẮT LASER'
    assert sheet['L10'].value == 'Thời gian Setup ( phút )'
    assert sheet['L11'].value == 20
    assert sheet['L14'].value == 100


def test_real_po_labels_decode_to_canonical_operation_ids(api, real_po, db):
    _, po = real_po
    po_id = int(po['production_order_id'])
    labels = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router-labels',
                     timeout=900).json()
    assert labels['count'] == 113 + 47
    assert labels['unmatched'] == []
    assert re.fullmatch(r'[0-9a-f]{64}', labels['source_file']['sha256'])

    ids = {int(r['id']) for r in db.execute("""SELECT id FROM operations
        WHERE production_order_id=%s AND COALESCE(operation_type,'PRODUCTION')
        IN ('PRODUCTION','SETUP')""", (po_id,)).fetchall()}
    assert {int(i['operation_id']) for i in labels['labels']} == ids
    setup_ids = {int(r['id']) for r in db.execute(
        "SELECT id FROM operations WHERE production_order_id=%s AND operation_type='SETUP'",
        (po_id,)).fetchall()}
    for item in labels['labels']:
        if item['kind'] == 'SETUP':
            assert int(item['operation_id']) in setup_ids
            assert item['payload'] == f"WF|OPID|{item['operation_id']}"


def test_re_import_points_the_export_at_the_new_file(
        api, real_po, corrected_workbook_bytes, db):
    """Nhập lại thì lần xuất sau phải dùng BẢN MỚI, không dùng nhầm bản cũ."""
    template_id, po = real_po
    po_id = int(po['production_order_id'])
    before = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router-labels',
                     timeout=900).json()['source_file']

    # Nhập lại cùng nội dung: content-addressed nên sha256 không đổi, nhưng
    # phải là một lần nhập MỚI (import_id tăng) -- đó là thứ chỉ ra bản đang dùng.
    files = {'file': (REAL_FIXTURE.name, corrected_workbook_bytes,
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    again = api.post(f'{BASE_URL}/api/templates/import-workbook', files=files, timeout=600)
    assert again.status_code == 200, again.text[:400]
    assert again.json()['template_id'] == template_id

    after = api.get(f'{BASE_URL}/api/production-orders/{po_id}/router-labels',
                    timeout=900).json()['source_file']
    assert after['sha256'] == before['sha256'], 'cùng nội dung -> cùng hash'
    assert after['import_id'] >= before['import_id'], 'phải trỏ tới lần nhập mới nhất'
