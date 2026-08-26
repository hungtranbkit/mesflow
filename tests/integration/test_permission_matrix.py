"""Reliability Validation Round 2, Gate 18 -- role permission matrix
(anonymous/operator/supervisor/manager/admin) against real, significant
mutation endpoints, over real HTTP against the real running app.

Two things this checks that a purely static/structural test (like
tests/test_v6584432_rbac.py) cannot: (1) that the ACTUAL enforced
permission for a route matches what its @roles_required(...)/
@permission_required(...) decorator visually promises -- auth.py's
roles_required() has a "permission compatibility layer"
(_permission_for_request()) that silently OVERRIDES a route's own literal
allowed-roles list whenever the request path matches a coarser path-prefix
rule, and (2) that a rejected role gets exactly 403 (not a 500, not a
silent 200) while an anonymous caller gets 401.

test_manager_cannot_force_delete_production_order is a REAL confirmed bug
this file's investigation found and a fix (auth.py::_permission_for_request)
verified: /production-orders/<id>/force is its own explicit
@roles_required('admin')-only route, but the generic '/api/production-orders'
prefix rule mapped it to the coarse 'po.edit' permission instead, which
'manager' also holds -- a manager account could reach and complete a full
PO force-delete (verified live, HTTP 200, PO actually removed from the DB)
despite the route's explicit admin-only intent.

2026-08-26, Gate 18 second pass (final reliability gates round): the same
static-audit technique applied to EVERY @roles_required route (not just
/force in isolation) found three more real mismatches of the exact same
class, all fixed via the same auth.py carve-out mechanism and covered
below:
  - POST /production-orders/<id>/start -- 'po.edit' narrowed the route's
    own admin/manager/supervisor list down to admin/manager only;
    supervisors got a wrongful 403 starting production.
  - POST /templates/demo/seed, DELETE /templates/demo -- 'template.edit'
    widened an admin-only route to include manager (privilege escalation,
    same class as the force-delete bug, just non-destructive demo data).
  - GET /templates/<id>/export-workbook -- 'template.view' widened an
    admin/manager-only route to include viewer (read-only, low risk, but
    still not what the route's own decorator says).
"""
from __future__ import annotations

import uuid

import pytest
import requests
from werkzeug.security import generate_password_hash

pytestmark = pytest.mark.postgres
BASE = 'http://mesflow-test-api:8080'
ROLES = ('admin', 'manager', 'supervisor', 'operator', 'viewer')


def _create_user(db, role, password='Test@123456'):
    username = f'permtest-{role}-{uuid.uuid4().hex[:10]}'
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO users(username,display_name,password_hash,role,active,must_change_password) VALUES(%s,%s,%s,%s,TRUE,FALSE) RETURNING id",
            (username, role, generate_password_hash(password), role))
        user_id = cur.fetchone()['id']
    return username, password, user_id


@pytest.fixture(scope='module')
def role_sessions(db):
    """One logged-in requests.Session per role, plus a raw (unauthenticated)
    session for the anonymous case. Created once for the whole module --
    login itself isn't what's under test here."""
    sessions = {}
    created_user_ids = []
    for role in ROLES:
        username, password, user_id = _create_user(db, role)
        created_user_ids.append(user_id)
        s = requests.Session()
        r = s.post(f'{BASE}/api/auth/login', json={'username': username, 'password': password}, timeout=15)
        assert r.status_code == 200, f'{role} login failed: {r.text}'
        sessions[role] = s
    sessions['anonymous'] = requests.Session()
    yield sessions
    with db.cursor() as cur:
        cur.execute('DELETE FROM users WHERE id=ANY(%s)', (created_user_ids,))


@pytest.fixture(scope='module')
def fixture_graph(db):
    suffix = uuid.uuid4().hex[:10]
    with db.cursor() as cur:
        cur.execute("INSERT INTO employees(employee_no,name,department,position,qr) VALUES(%s,%s,'TEST','Worker',%s) RETURNING id",
                    (f'PERM-{suffix}', 'Perm Matrix Worker', f'WF|EMP|PERM-{suffix}'))
        employee_id = cur.fetchone()['id']
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'PERM',10,'DRAFT') RETURNING id",
                    (f'PERM-PO-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Perm Part') RETURNING id", (po_id, f'PERM-PART-{suffix}'))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,%s,'Perm Operation','PLANNED',%s) RETURNING id""", (po_id, part_id, f'PERM-OP-{suffix}', f'WF|OP|PERM-OP-{suffix}'))
        operation_id = cur.fetchone()['id']
        cur.execute("INSERT INTO kiosk_identities(device_uuid,status) VALUES(%s,'PENDING') RETURNING id", (f'PERM-KIOSK-{suffix}',))
        kiosk_identity_id = cur.fetchone()['id']
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'PERM',1,'DRAFT') RETURNING id",
                    (f'PERM-PO-START-{suffix}',))
        start_po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO templates(code,name,product,version,active) VALUES(%s,'Perm Template','PERM','1.0',TRUE) RETURNING id",
                    (f'PERM-TPL-{suffix}',))
        template_id = cur.fetchone()['id']
    g = dict(employee_id=employee_id, po_id=po_id, part_id=part_id, operation_id=operation_id, kiosk_identity_id=kiosk_identity_id,
              start_po_id=start_po_id, template_id=template_id, suffix=suffix)
    yield g
    with db.cursor() as cur:
        cur.execute('DELETE FROM kiosk_identities WHERE id=%s', (kiosk_identity_id,))
        cur.execute('DELETE FROM operations WHERE id=%s', (operation_id,))
        cur.execute('DELETE FROM parts WHERE id=%s', (part_id,))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (start_po_id,))
        cur.execute('DELETE FROM templates WHERE id=%s', (template_id,))
        cur.execute('DELETE FROM employees WHERE id=%s', (employee_id,))


def _matrix(g):
    """(method, path, body, allowed_roles) -- allowed_roles is the set of
    roles that must NOT get 403 (admin is always implicitly allowed and
    omitted from each entry below for brevity, then added back at
    assertion time)."""
    return [
        ('POST', '/api/employees', {'employee_no': f'PERM-NEW-{g["suffix"]}', 'name': 'x', 'qr': f'WF|EMP|NEW-{g["suffix"]}'}, {'manager'}),
        ('PATCH', f'/api/employees/{g["employee_id"]}', {'name': 'Renamed'}, {'manager'}),
        ('PUT', '/api/settings/work-shifts', {'items': []}, {'manager'}),
        ('POST', f'/api/operations/{g["operation_id"]}/cancel', {}, {'manager', 'supervisor'}),
        ('DELETE', f'/api/production-orders/{g["po_id"]}/force', {'confirm_code': 'WRONG'}, set()),  # admin only
        ('POST', f'/api/exceptions/999999999/acknowledge', {'expected_version': 1}, {'manager', 'supervisor'}),
        ('POST', f'/api/kiosk-identities/{g["kiosk_identity_id"]}/approve', {}, {'manager'}),
        ('POST', '/api/kiosk-management/generation/bump', {}, set()),  # admin only
        ('POST', '/api/users', {'username': f'perm-new-{g["suffix"]}', 'password': 'Xx123456!', 'role': 'viewer'}, set()),  # admin only (users.manage)
        ('PUT', '/api/roles/viewer/permissions', {'permissions': []}, set()),  # admin only (roles.manage)
        # Gate 18 second pass (2026-08-26) -- three more confirmed mismatches,
        # same class as the force-delete bug above:
        ('POST', f'/api/production-orders/{g["start_po_id"]}/start', {}, {'manager', 'supervisor'}),
        ('GET', f'/api/templates/{g["template_id"]}/export-workbook', {}, {'manager'}),
    ]


def test_role_matrix_over_real_http(role_sessions, fixture_graph):
    g = fixture_graph
    failures = []
    for method, path, body, extra_allowed in _matrix(g):
        allowed = extra_allowed | {'admin'}
        for role in ROLES:
            s = role_sessions[role]
            r = s.request(method, f'{BASE}{path}', json=body, timeout=15)
            if role in allowed:
                if r.status_code == 403:
                    failures.append(f'{role} {method} {path}: expected NOT forbidden, got 403: {r.text[:200]}')
            else:
                if r.status_code != 403:
                    failures.append(f'{role} {method} {path}: expected 403 (FORBIDDEN), got {r.status_code}: {r.text[:200]}')
        # Anonymous must be rejected with 401, never 403 (no session to
        # even evaluate a role/permission against) and never 200.
        r = role_sessions['anonymous'].request(method, f'{BASE}{path}', json=body, timeout=15)
        if r.status_code != 401:
            failures.append(f'anonymous {method} {path}: expected 401 (AUTH_REQUIRED), got {r.status_code}: {r.text[:200]}')
    assert not failures, 'Permission matrix violations:\n' + '\n'.join(failures)


def test_manager_cannot_force_delete_production_order(db, role_sessions):
    # Dedicated end-to-end regression for the confirmed bug: a full,
    # correctly-confirm-coded force-delete attempt by a manager must be
    # rejected before it ever touches the row, not merely fail on an
    # unrelated validation error.
    with db.cursor() as cur:
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'PERM',1,'DRAFT') RETURNING id",
                    (f'PERM-FORCE-REG-{uuid.uuid4().hex[:10]}',))
        po_id = cur.fetchone()['id']
        cur.execute('SELECT code FROM production_orders WHERE id=%s', (po_id,))
        code = cur.fetchone()['code']
    try:
        r = role_sessions['manager'].delete(f'{BASE}/api/production-orders/{po_id}/force', json={'confirm_code': code}, timeout=15)
        assert r.status_code == 403, f'manager force-delete must be rejected by role, got {r.status_code}: {r.text}'
        with db.cursor() as cur:
            cur.execute('SELECT id FROM production_orders WHERE id=%s', (po_id,))
            assert cur.fetchone() is not None, 'PO must still exist -- manager must never reach the delete logic'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))


def test_supervisor_can_actually_start_production_order(db, role_sessions):
    # Gate 18 second pass: confirmed regression -- 'po.edit' narrowed the
    # route's own admin/manager/supervisor list down to admin/manager only,
    # so a supervisor got a wrongful 403 starting production. End-to-end:
    # not just "not 403" but the PO actually transitions to IN_PROGRESS.
    suffix = uuid.uuid4().hex[:10]
    with db.cursor() as cur:
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) VALUES(%s,'PERM',1,'DRAFT') RETURNING id",
                    (f'PERM-SUP-START-{suffix}',))
        po_id = cur.fetchone()['id']
        cur.execute("INSERT INTO parts(production_order_id,code,name) VALUES(%s,%s,'Perm Part') RETURNING id", (po_id, f'PERM-SUP-PART-{suffix}'))
        part_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr)
            VALUES(%s,%s,%s,'Perm Operation','PLANNED',%s) RETURNING id""", (po_id, part_id, f'PERM-SUP-OP-{suffix}', f'WF|OP|PERM-SUP-{suffix}'))
        operation_id = cur.fetchone()['id']
    try:
        r = role_sessions['supervisor'].post(f'{BASE}/api/production-orders/{po_id}/start', json={}, timeout=15)
        assert r.status_code != 403, f'supervisor must be allowed to start a PO, got {r.status_code}: {r.text}'
        with db.cursor() as cur:
            cur.execute('SELECT status FROM production_orders WHERE id=%s', (po_id,))
            assert cur.fetchone()['status'] == 'IN_PROGRESS', f'supervisor start must actually take effect, got {r.status_code}: {r.text}'
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM operations WHERE id=%s', (operation_id,))
            cur.execute('DELETE FROM parts WHERE id=%s', (part_id,))
            cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))


def test_manager_cannot_seed_or_delete_template_demo_data(db, role_sessions):
    # Gate 18 second pass: confirmed regression -- 'template.edit' widened
    # these admin-only routes to include manager. Deliberately does NOT
    # exercise admin's positive path here (seeding real demo content as a
    # side effect of a permission test is undesirable); the negative path
    # alone is sufficient to prove the escalation is closed, and admin's
    # seed/delete round-trip (content, not permissions) is already covered
    # live by tests/test_po_template_demo_relaxed_v6588.py.
    r = role_sessions['manager'].post(f'{BASE}/api/templates/demo/seed', json={}, timeout=15)
    assert r.status_code == 403, f'manager must not seed demo templates, got {r.status_code}: {r.text}'
    r = role_sessions['manager'].delete(f'{BASE}/api/templates/demo', timeout=15)
    assert r.status_code == 403, f'manager must not delete demo templates, got {r.status_code}: {r.text}'
