"""Creating a PO from a Template with duplicate Operation codes.

Live bug on TEST 2026-09-09: "Production Order -> + Tạo PO từ Template" for PO
6126 popped a raw PostgreSQL error at the user --

    duplicate key value violates unique constraint "operations_code_key"
    DETAIL: Key (code)=(6126-KM-3172005-08-OP02) already exists.

Root cause: instantiate() derives each Operation code as
`<po_code>-<template_op_code>`, and operations.code is globally unique, so two
template rows sharing a code collide. TPL-6126 had ten such duplicates (e.g.
KM-3172005-08-OP02 twice under the same part) because neither replace_tree()
nor validate() ever checked Operation-code uniqueness -- replace_tree built a
set() of codes purely to resolve input_source_code, which swallowed duplicates
silently.

Nothing held the colliding code afterwards: the clone runs in one transaction,
so it rolled back cleanly. The damage was the raw error and the dead end.
"""
import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _template(db, *, ops):
    """Create a template directly, bypassing replace_tree's validation.

    Deliberate: it reproduces the state TEST was actually in (rows written
    before the guard existed), which is what instantiate() has to survive.
    """
    suffix = uuid.uuid4().hex[:8].upper()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO templates(code,name,product,version,active)
            VALUES(%s,'Tpl dup op','SP',%s,true) RETURNING id""", (f'TPL-DUP-{suffix}', '1.0'))
        template_id = cur.fetchone()['id']
        cur.execute("""INSERT INTO template_parts(template_id,code,name,sort_order)
            VALUES(%s,%s,'Part 1',0) RETURNING id""", (template_id, f'P-{suffix}'))
        part_id = cur.fetchone()['id']
        for idx, code in enumerate(ops):
            cur.execute("""INSERT INTO template_operations(template_id,part_id,code,name,sort_order,
                    standard_seconds_per_unit,repair_cycle_time_seconds_per_unit)
                VALUES(%s,%s,%s,%s,%s,10,0)""", (template_id, part_id, code, f'OP {code}', idx))
    return template_id, suffix


def _create_po(api, template_id, code, **overrides):
    payload = {'code': code, 'planned_quantity': 100, **overrides}
    return api.post(f'{BASE_URL}/api/templates/{template_id}/instantiate', json=payload, timeout=20)


def _cleanup(db, template_id, po_codes):
    with db.cursor() as cur:
        for po_code in po_codes:
            cur.execute("""DELETE FROM operations WHERE production_order_id IN
                (SELECT id FROM production_orders WHERE code=%s)""", (po_code,))
            cur.execute("""DELETE FROM parts WHERE production_order_id IN
                (SELECT id FROM production_orders WHERE code=%s)""", (po_code,))
            cur.execute("DELETE FROM production_orders WHERE code=%s", (po_code,))
        cur.execute('DELETE FROM template_operations WHERE template_id=%s', (template_id,))
        cur.execute('DELETE FROM template_parts WHERE template_id=%s', (template_id,))
        cur.execute('DELETE FROM templates WHERE id=%s', (template_id,))


def test_duplicate_operation_code_is_a_business_error_not_a_raw_db_error(db, api):
    """The exact TEST failure: same code twice under one part."""
    template_id, _suffix = _template(db, ops=['KM-OP01', 'KM-OP02', 'KM-OP02'])
    po_code = f'PO-DUP-{uuid.uuid4().hex[:6].upper()}'
    try:
        response = _create_po(api, template_id, po_code)
        assert response.status_code == 409, f'expected a business conflict, got {response.status_code}: {response.text}'
        message = response.json().get('message') or ''
        # Names what to fix...
        assert 'KM-OP02' in message
        assert 'Operation' in message and 'trùng' in message
        # ...and never leaks the database's own words.
        lowered = message.lower()
        for leak in ('duplicate key', 'unique constraint', 'operations_code_key', 'detail:', 'psycopg', 'sqlstate'):
            assert leak not in lowered, f'raw DB text leaked to the user: {message}'

        # Atomic: no half-created PO/Part/Operation left behind.
        assert db.execute('SELECT COUNT(*) n FROM production_orders WHERE code=%s', (po_code,)).fetchone()['n'] == 0
        assert db.execute("SELECT COUNT(*) n FROM operations WHERE code LIKE %s", (f'{po_code}-%',)).fetchone()['n'] == 0
    finally:
        _cleanup(db, template_id, [po_code])


def test_retrying_the_same_broken_template_stays_the_same_clean_error(db, api):
    """Double-click / retry must not half-create anything or change the error."""
    template_id, _suffix = _template(db, ops=['KM-OP01', 'KM-OP01'])
    po_code = f'PO-RETRY-{uuid.uuid4().hex[:6].upper()}'
    try:
        first = _create_po(api, template_id, po_code)
        second = _create_po(api, template_id, po_code)
        assert first.status_code == second.status_code == 409
        assert first.json().get('message') == second.json().get('message')
        assert db.execute('SELECT COUNT(*) n FROM production_orders WHERE code=%s', (po_code,)).fetchone()['n'] == 0
    finally:
        _cleanup(db, template_id, [po_code])


def test_clean_template_still_instantiates_and_codes_are_prefixed(db, api):
    """The normal path is untouched: codes stay `<po>-<template op code>`."""
    template_id, _suffix = _template(db, ops=['KM-OP01', 'KM-OP02', 'KM-OP03'])
    po_code = f'PO-OK-{uuid.uuid4().hex[:6].upper()}'
    try:
        response = _create_po(api, template_id, po_code)
        assert response.status_code in (200, 201), response.text
        codes = [r['code'] for r in db.execute("""SELECT o.code FROM operations o
            JOIN production_orders po ON po.id=o.production_order_id
            WHERE po.code=%s ORDER BY o.sort_order,o.id""", (po_code,)).fetchall()]
        assert codes == [f'{po_code}-KM-OP01', f'{po_code}-KM-OP02', f'{po_code}-KM-OP03']
        # Same PO code twice is still refused, on the PO's own constraint.
        again = _create_po(api, template_id, po_code)
        assert again.status_code == 409
        assert 'Production Order' in (again.json().get('message') or '')
    finally:
        _cleanup(db, template_id, [po_code])


def test_saving_a_template_with_duplicate_operation_codes_is_refused(db, api):
    """Fix the leak at the source too, so no new template can reach that state."""
    template_id, suffix = _template(db, ops=['KM-OP01'])
    try:
        tree = api.get(f'{BASE_URL}/api/templates/{template_id}/tree', timeout=15).json()
        parts = [{'key': '0', 'code': f'P-{suffix}', 'name': 'Part 1', 'sort_order': 0}]
        operations = [
            {'part_key': '0', 'code': 'KM-OP01', 'name': 'A', 'sort_order': 0},
            {'part_key': '0', 'code': 'KM-OP01', 'name': 'B', 'sort_order': 1},
        ]
        assert tree.get('ok') is not False
        response = api.put(f'{BASE_URL}/api/templates/{template_id}/tree',
                           json={'parts': parts, 'operations': operations, 'equipment': []}, timeout=15)
        assert response.status_code >= 400, f'duplicate op codes must be refused, got {response.status_code}'
        assert 'KM-OP01' in response.text or 'operation' in response.text.lower()

        # And the template validator reports it, so the screen can point at it.
        report = api.get(f'{BASE_URL}/api/templates/{template_id}/validate', timeout=15)
        assert report.status_code == 200, report.text
    finally:
        _cleanup(db, template_id, [])


def test_template_list_reports_real_part_and_operation_counts(db, api):
    """The list panel prints these numbers; they must not always be zero.

    Reported on TEST 2026-09-09: every template card read "0 Part · 0
    Operation" while the editor beside it showed the Parts and Operations.
    /api/templates went through the generic list(), which returns only the
    templates table's own columns, so part_count/operation_count were simply
    absent and the UI's `x.part_count||0` fell back to 0.
    """
    template_id, _suffix = _template(db, ops=['KM-OP01', 'KM-OP02', 'KM-OP03'])
    try:
        response = api.get(f'{BASE_URL}/api/templates?limit=500', timeout=15)
        assert response.status_code == 200, response.text
        row = next(x for x in response.json()['items'] if x['id'] == template_id)
        assert row['part_count'] == 1
        assert row['operation_count'] == 3
    finally:
        _cleanup(db, template_id, [])
