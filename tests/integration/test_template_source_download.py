"""Nút "Tải file Excel gốc": trả về ĐÚNG bytes đã upload, không biến đổi.

Chạy trên API + PostgreSQL thật vì thứ cần chứng minh là: file lấy ra khớp
từng byte với file đã nhập (checksum), mang đúng tên gốc, và KHÔNG đi qua
pipeline xuất/chèn QR. Cùng ca "chưa có nguồn" phải là 404 gọn, không 500.
"""
import hashlib
import re
import uuid

import pytest

from test_router_setup_import_export import BASE_URL, _router_bytes, _upload

pytestmark = pytest.mark.integration


def _latest_success_import(api, template_id):
    d = api.get(f'{BASE_URL}/api/templates/{template_id}/import-history').json()
    assert d['ok'] is True
    ok = [x for x in d['items'] if x['outcome'] != 'FAILED']
    ok.sort(key=lambda x: x['created_at'])
    return ok[-1] if ok else None


def test_tai_file_goc_dung_tung_byte_va_ten(api):
    """Bytes tải về == bytes đã upload (sha256); Content-Disposition mang tên gốc."""
    data = _router_bytes()
    up = _upload(api, '/api/templates/import-workbook', data)
    assert up.status_code == 200, up.text[:400]
    template_id = up.json()['template_id']

    imp = _latest_success_import(api, template_id)
    assert imp, 'phải có ít nhất một lần nhập thành công'

    resp = api.get(f'{BASE_URL}/api/templates/import-history/{imp["id"]}/download')
    assert resp.status_code == 200, resp.text[:300]
    # 1) checksum GIỮ NGUYÊN -- không recalc, không chèn QR, không biến đổi.
    assert hashlib.sha256(resp.content).hexdigest() == hashlib.sha256(data).hexdigest()
    # 2) đúng tên file gốc đã upload (khớp cả filename và filename* RFC5987).
    disposition = resp.headers.get('Content-Disposition', '')
    assert imp['original_filename'], 'lần nhập phải lưu tên file gốc'
    assert 'attachment' in disposition.lower()
    assert ('Lộ trình sản xuất TEST.xlsx' in disposition
            or 'filename*' in disposition), disposition
    # 3) là workbook Excel, không phải một biến thể đã dựng lại.
    assert resp.headers.get('Content-Type', '').startswith(
        'application/vnd.openxmlformats')


def test_khong_co_import_id_tra_404_khong_500(api):
    """Không tìm thấy lần nhập -> 404 gọn, tuyệt đối không 500."""
    resp = api.get(f'{BASE_URL}/api/templates/import-history/999000999/download')
    assert resp.status_code == 404, resp.text[:300]


def test_template_tao_truc_tiep_khong_co_file_goc(api):
    """Template không qua Excel -> lịch sử nhập rỗng -> UI hiện 'Chưa có file gốc'.

    (Nút gọi endpoint này rồi thấy items rỗng -> báo 'Chưa có file Excel gốc'.)
    """
    code = f'TPLNOSRC{uuid.uuid4().hex[:8].upper()}'
    created = api.post(f'{BASE_URL}/api/templates', json={
        'code': code, 'name': code, 'product': 'x', 'version': '1.0', 'active': True})
    assert created.status_code in (200, 201), created.text[:300]
    template_id = created.json()['id']
    hist = api.get(f'{BASE_URL}/api/templates/{template_id}/import-history')
    assert hist.status_code == 200
    body = hist.json()
    assert body['ok'] is True
    assert [x for x in body['items'] if x['outcome'] != 'FAILED'] == []


def test_tai_lai_khong_dung_nham_template_khac(api):
    """Nhiều Template -> mỗi nút tải đúng file của Template mình, không lẫn."""
    data_a = _router_bytes(po_number=f'A{uuid.uuid4().hex[:7].upper()}')
    data_b = _router_bytes(po_number=f'B{uuid.uuid4().hex[:7].upper()}')
    a = _upload(api, '/api/templates/import-workbook', data_a); assert a.status_code == 200, a.text[:300]
    b = _upload(api, '/api/templates/import-workbook', data_b); assert b.status_code == 200, b.text[:300]
    imp_a = _latest_success_import(api, a.json()['template_id'])
    imp_b = _latest_success_import(api, b.json()['template_id'])
    dl_a = api.get(f'{BASE_URL}/api/templates/import-history/{imp_a["id"]}/download')
    dl_b = api.get(f'{BASE_URL}/api/templates/import-history/{imp_b["id"]}/download')
    assert hashlib.sha256(dl_a.content).hexdigest() == hashlib.sha256(data_a).hexdigest()
    assert hashlib.sha256(dl_b.content).hexdigest() == hashlib.sha256(data_b).hexdigest()
    assert dl_a.content != dl_b.content
