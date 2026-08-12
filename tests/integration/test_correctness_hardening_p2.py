from io import BytesIO
import uuid

import pytest

from conftest import BASE_URL
from mesflow.web.app import create_app

pytestmark=pytest.mark.postgres


def _reconcile(api,po_id):
    response=api.post(f'{BASE_URL}/api/production-state/reconcile',json={'po_id':po_id})
    assert response.status_code==200,response.text
    return response.json()['production_order']['status']


def test_po_completion_matrix_does_not_treat_cancelled_as_completed(api,db,seeded_factory):
    g=seeded_factory
    with db.cursor() as cur:
        code=f'P2-COR-{g["suffix"]}'
        cur.execute("INSERT INTO operations(production_order_id,part_id,code,name,status,qr) VALUES(%s,%s,%s,'Second','PLANNED',%s) RETURNING id",(g['po_id'],g['part_id'],code,f'WF|OP|{code}'))
        second=cur.fetchone()['id']
        cur.execute("UPDATE operations SET status='COMPLETED' WHERE id IN (%s,%s)",(g['operation_id'],second))
    assert _reconcile(api,g['po_id'])=='COMPLETED'
    with db.cursor() as cur:cur.execute("UPDATE operations SET status='CANCELLED' WHERE id=%s",(second,))
    assert _reconcile(api,g['po_id'])!='COMPLETED'
    with db.cursor() as cur:cur.execute("UPDATE operations SET status='CANCELLED' WHERE id=%s",(g['operation_id'],))
    assert _reconcile(api,g['po_id'])!='COMPLETED'
    with db.cursor() as cur:cur.execute("UPDATE production_orders SET status='CANCELLED' WHERE id=%s",(g['po_id'],))
    assert _reconcile(api,g['po_id'])=='CANCELLED'
    with db.cursor() as cur:cur.execute('DELETE FROM operations WHERE id=%s',(second,))


@pytest.mark.parametrize(('name','content'),[
    ('drawing.pdf',b'%PDF-1.7\n%%EOF'),
    ('drawing.png',b'\x89PNG\r\n\x1a\n'+b'valid-image-payload'),
])
def test_valid_drawing_upload_and_download_is_attachment(api,name,content):
    response=api.post(f'{BASE_URL}/api/template-parts/upload-drawing',files={'file':(name,BytesIO(content))})
    assert response.status_code==201,response.text
    body=response.json();assert body['name']==name
    downloaded=api.get(f"{BASE_URL}{body['url']}")
    assert downloaded.status_code==200
    assert downloaded.headers['Content-Disposition'].lower().startswith('attachment;')
    assert downloaded.content==content


@pytest.mark.parametrize(('name','content','expected'),[
    ('fake.png',b'not-a-png',400),
    ('active.svg',b'<svg><script>alert(1)</script></svg>',400),
    ('script.html',b'<script>alert(1)</script>',400),
    ('archive.exe',b'MZ',400),
    ('bad.zip',b'not-a-zip',400),
])
def test_invalid_or_active_drawing_content_is_rejected(api,name,content,expected):
    response=api.post(f'{BASE_URL}/api/template-parts/upload-drawing',files={'file':(name,BytesIO(content))})
    assert response.status_code==expected,response.text
    assert response.json()['error']=='INVALID_REQUEST'


def test_upload_filename_traversal_is_not_used_as_storage_path(api):
    response=api.post(f'{BASE_URL}/api/template-parts/upload-drawing',files={'file':('../../evil.pdf',BytesIO(b'%PDF-1.7\n%%EOF'))})
    assert response.status_code==201,response.text
    body=response.json();assert body['name']=='evil.pdf' and '..' not in body['path'] and '..' not in body['url']


def test_drawing_specific_size_limit_returns_413(api):
    response=api.post(f'{BASE_URL}/api/template-parts/upload-drawing',files={'file':('large.pdf',BytesIO(b'%PDF-'+b'x'*(20*1024*1024)))})
    assert response.status_code==413,response.text
    assert response.json()['error']=='PAYLOAD_TOO_LARGE'


def test_excel_import_rejects_fake_extension_content_as_400(api):
    response=api.post(f'{BASE_URL}/api/operations/import',data={'mode':'merge'},files={'file':('fake.xlsx',BytesIO(b'not-an-office-zip'))})
    assert response.status_code==400,response.text
    assert response.json()['error']=='INVALID_REQUEST'


def test_error_semantics_cover_400_404_409_and_auth_boundaries(api,db,seeded_factory):
    invalid=api.post(f'{BASE_URL}/api/production-state/reconcile',json={})
    assert invalid.status_code==400 and invalid.json()['error']=='INVALID_REQUEST'
    missing=api.post(f'{BASE_URL}/api/production-state/reconcile',json={'operation_id':999999999})
    assert missing.status_code==404 and missing.json()['error']=='NOT_FOUND'
    with db.cursor() as cur:cur.execute("UPDATE operations SET status='COMPLETED' WHERE id=%s",(seeded_factory['operation_id'],))
    conflict=api.post(f'{BASE_URL}/api/work-sessions/start',json={'request_id':str(uuid.uuid4()),'employee_id':seeded_factory['employee_id'],'operation_id':seeded_factory['operation_id'],'station_id':seeded_factory['station_id']})
    assert conflict.status_code==409 and conflict.json()['error']=='BUSINESS_CONFLICT'


def test_unexpected_server_failure_remains_500_at_flask_boundary(db):
    app=create_app()
    app.config.update(TESTING=False,PROPAGATE_EXCEPTIONS=False)
    @app.get('/_integration/unexpected')
    def unexpected():
        raise RuntimeError('simulated internal storage failure')
    response=app.test_client().get('/_integration/unexpected')
    assert response.status_code==500
    body=response.get_json();assert body['error']=='INTERNAL_ERROR'
    assert 'simulated internal storage failure' not in body.get('message','')
