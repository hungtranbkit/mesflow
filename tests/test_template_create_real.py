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
        # Fix Plan Phase 1: session['user_id'] alone is no longer sufficient
        # -- mesflow.core.session_policy.validate_and_touch() now also
        # requires login_at/last_activity_at/absolute_expires_at (every
        # authenticated request validates idle/absolute expiry; a session
        # missing those fields fails closed as SESSION_MISSING_FIELDS, by
        # design -- see that module's own docstring). Reuse the real
        # start_session() here instead of hand-rolling the field set again,
        # so this helper can never drift from what a real login actually
        # writes.
        from mesflow.core import session_policy
        session.update(session_policy.session_fields_for_login(1, 'admin', 'ADMIN'))
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
    assert 'Cấu trúc sản xuất' in js  # later reworded from "Cấu trúc sản phẩm"
