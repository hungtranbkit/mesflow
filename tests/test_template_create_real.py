from mesflow.web.app import create_app
import mesflow.web.master_data as master_data


class FakeTemplateRepository:
    def __init__(self):
        self.rows = []

    def list(self, limit=200, offset=0):
        return self.rows[offset:offset + limit]

    def create(self, data):
        row = {
            'id': len(self.rows) + 1,
            'code': str(data.get('code', '')).strip().upper(),
            'name': str(data.get('name', '')).strip(),
            'product': str(data.get('product', '')).strip(),
            'version': str(data.get('version') or '1.0'),
            'active': bool(data.get('active', True)),
        }
        if not row['code'] or not row['name']:
            raise ValueError('template code and name required')
        self.rows.append(row)
        return row['id']

    def get(self, entity_id):
        entity_id = int(entity_id)
        return next(row for row in self.rows if row['id'] == entity_id)


def authenticated_client(app):
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 1
        session['username'] = 'admin'
        session['role'] = 'ADMIN'
    return client


def test_post_templates_creates_and_returns_item(monkeypatch):
    repo = FakeTemplateRepository()
    monkeypatch.setitem(master_data.RESOURCES, 'templates', repo)
    app = create_app()
    app.config.update(TESTING=True)
    client = authenticated_client(app)

    response = client.post('/api/templates', json={
        'code': 'box-001',
        'name': 'Hộp điện',
        'product': 'BOX',
        'version': '1.0',
        'active': True,
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body['ok'] is True
    assert body['id'] == 1
    assert body['item']['code'] == 'BOX-001'
    assert body['item']['name'] == 'Hộp điện'


def test_template_screen_has_visible_create_form():
    js = open('app/mesflow/web/static/app.js', encoding='utf-8').read()
    assert 'newTemplateOld' in js
    assert 'id="tplCode"' in js
    assert 'id="tplName"' in js
    assert "api('/api/templates',{method:'POST'" in js
    assert 'Template mới' in js
    assert 'Cấu trúc sản phẩm' in js
