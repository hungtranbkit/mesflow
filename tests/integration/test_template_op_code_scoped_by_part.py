"""Operation codes are unique per Part, not per Template.

Design agreed 2026-09-09: an Operation code may repeat across different Parts
-- (Part code, Operation code) is the business key -- while Part codes stay
unique within a Template. operations.code and operations.qr remain globally
unique, so the generated code has to carry the Part whenever the Operation
code does not already name it (operation_code_suffix()).
"""
import io
import uuid

import pytest
from openpyxl import Workbook

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _template(db, *, parts_ops):
    """parts_ops: {part_code: [op_code, ...]} inserted directly."""
    suffix = uuid.uuid4().hex[:8].upper()
    with db.cursor() as cur:
        cur.execute("""INSERT INTO templates(code,name,product,version,active)
            VALUES(%s,'Tpl scope','SP','1.0',true) RETURNING id""", (f'TPL-SCOPE-{suffix}',))
        template_id = cur.fetchone()['id']
        for p_idx, (part_code, ops) in enumerate(parts_ops.items()):
            cur.execute("""INSERT INTO template_parts(template_id,code,name,sort_order)
                VALUES(%s,%s,%s,%s) RETURNING id""", (template_id, part_code, f'Part {part_code}', p_idx))
            part_id = cur.fetchone()['id']
            for o_idx, op_code in enumerate(ops):
                cur.execute("""INSERT INTO template_operations(template_id,part_id,code,name,sort_order,
                        standard_seconds_per_unit,repair_cycle_time_seconds_per_unit)
                    VALUES(%s,%s,%s,%s,%s,10,0)""",
                    (template_id, part_id, op_code, f'OP {op_code}', o_idx))
    return template_id, suffix


def _create_po(api, template_id, code):
    return api.post(f'{BASE_URL}/api/templates/{template_id}/instantiate',
                    json={'code': code, 'planned_quantity': 10}, timeout=20)


def _cleanup(db, template_id, po_code=None):
    with db.cursor() as cur:
        if po_code:
            cur.execute("""DELETE FROM operations WHERE production_order_id IN
                (SELECT id FROM production_orders WHERE code=%s)""", (po_code,))
            cur.execute("""DELETE FROM parts WHERE production_order_id IN
                (SELECT id FROM production_orders WHERE code=%s)""", (po_code,))
            cur.execute('DELETE FROM production_orders WHERE code=%s', (po_code,))
        cur.execute('DELETE FROM template_operations WHERE template_id=%s', (template_id,))
        cur.execute('DELETE FROM template_parts WHERE template_id=%s', (template_id,))
        cur.execute('DELETE FROM templates WHERE id=%s', (template_id,))


def test_same_operation_code_in_two_parts_is_allowed(db, api):
    """The feature itself: OP01 under two Parts, cloned without collision."""
    template_id, _s = _template(db, parts_ops={'PA': ['OP01', 'OP02'], 'PB': ['OP01', 'OP02']})
    po_code = f'PO-SCOPE-{uuid.uuid4().hex[:6].upper()}'
    try:
        response = _create_po(api, template_id, po_code)
        assert response.status_code in (200, 201), response.text
        rows = db.execute("""SELECT p.code part_code,o.code,o.qr FROM operations o
            JOIN parts p ON p.id=o.part_id JOIN production_orders po ON po.id=o.production_order_id
            WHERE po.code=%s ORDER BY p.code,o.sort_order""", (po_code,)).fetchall()
        assert [(r['part_code'], r['code']) for r in rows] == [
            ('PA', f'{po_code}-PA-OP01'), ('PA', f'{po_code}-PA-OP02'),
            ('PB', f'{po_code}-PB-OP01'), ('PB', f'{po_code}-PB-OP02')]
        # operations.qr is globally unique too -- it must not collide either.
        assert len({r['qr'] for r in rows}) == 4
    finally:
        _cleanup(db, template_id, po_code)


def test_code_that_already_names_its_part_is_left_alone(db, api):
    """Existing convention keeps producing exactly the codes it does today."""
    template_id, _s = _template(db, parts_ops={'KM-3172005-08': ['KM-3172005-08-OP01',
                                                                'KM-3172005-08-OP02']})
    po_code = f'PO-KEEP-{uuid.uuid4().hex[:6].upper()}'
    try:
        assert _create_po(api, template_id, po_code).status_code in (200, 201)
        codes = [r['code'] for r in db.execute("""SELECT o.code FROM operations o
            JOIN production_orders po ON po.id=o.production_order_id
            WHERE po.code=%s ORDER BY o.sort_order""", (po_code,)).fetchall()]
        assert codes == [f'{po_code}-KM-3172005-08-OP01', f'{po_code}-KM-3172005-08-OP02']
    finally:
        _cleanup(db, template_id, po_code)


def test_duplicate_within_one_part_is_still_refused(db, api):
    """The TPL-6126 shape stays invalid -- one Part cannot have two OP02."""
    template_id, _s = _template(db, parts_ops={'PA': ['OP02', 'OP02']})
    po_code = f'PO-DUP1-{uuid.uuid4().hex[:6].upper()}'
    try:
        response = _create_po(api, template_id, po_code)
        assert response.status_code == 409, response.text
        message = response.json()['message']
        assert 'cùng một Part' in message
        assert db.execute('SELECT COUNT(*) n FROM production_orders WHERE code=%s',
                          (po_code,)).fetchone()['n'] == 0
    finally:
        _cleanup(db, template_id, po_code)


def test_mixed_conventions_inside_one_part_are_refused(db, api):
    """`OP01` and `PA-OP01` in the SAME Part generate one identical code.

    The pair (Part, Operation code) differs, so a naive per-pair check would
    pass this and then die on operations_code_key. Validation therefore checks
    the code that will actually be generated.
    """
    template_id, _s = _template(db, parts_ops={'PA': ['OP01', 'PA-OP01']})
    po_code = f'PO-MIX-{uuid.uuid4().hex[:6].upper()}'
    try:
        response = _create_po(api, template_id, po_code)
        assert response.status_code == 409, (
            f'both rows generate {po_code}-PA-OP01; got {response.status_code}: {response.text}')
        assert db.execute('SELECT COUNT(*) n FROM production_orders WHERE code=%s',
                          (po_code,)).fetchone()['n'] == 0
    finally:
        _cleanup(db, template_id, po_code)


def _workbook(code, rows):
    wb = Workbook()
    meta = wb.active; meta.title = 'Template'
    meta.append(['template_code', 'template_name', 'product', 'version', 'active'])
    meta.append([code, f'Tên {code}', 'SP', '1.0', 1])
    parts = wb.create_sheet('Parts'); parts.append(['part_code', 'part_name', 'sort_order'])
    for idx, part_code in enumerate(sorted({p for p, _c in rows})):
        parts.append([part_code, f'Part {part_code}', idx])
    ops = wb.create_sheet('Operations')
    ops.append(['part_code', 'operation_code', 'operation_name', 'sort_order'])
    for idx, (part_code, op_code) in enumerate(rows):
        ops.append([part_code, op_code, f'OP {op_code}', idx])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _upload(api, filename, payload):
    return api.post(f'{BASE_URL}/api/templates/import-workbook',
                    files={'file': (filename, payload,
                                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                    timeout=30)


def _drop_template(db, code):
    with db.cursor() as cur:
        cur.execute('DELETE FROM template_import_events WHERE upper(template_code)=upper(%s)', (code,))
        cur.execute("""DELETE FROM template_operations WHERE template_id IN
            (SELECT id FROM templates WHERE upper(code)=upper(%s))""", (code,))
        cur.execute("""DELETE FROM template_parts WHERE template_id IN
            (SELECT id FROM templates WHERE upper(code)=upper(%s))""", (code,))
        cur.execute('DELETE FROM templates WHERE upper(code)=upper(%s)', (code,))


def test_excel_import_accepts_the_same_code_in_different_parts(db, api):
    code = f'TPL-XOK-{uuid.uuid4().hex[:6].upper()}'
    try:
        response = _upload(api, 'ok.xlsx', _workbook(code, [('PA', 'OP01'), ('PB', 'OP01')]))
        assert response.status_code == 200, response.text
        assert response.json()['operation_count'] == 2
    finally:
        _drop_template(db, code)


def test_excel_import_refuses_a_duplicate_inside_one_part(db, api):
    """Excel used to write straight through -- this is how TPL-6126 got in."""
    code = f'TPL-XBAD-{uuid.uuid4().hex[:6].upper()}'
    try:
        response = _upload(api, 'bad.xlsx', _workbook(code, [('PA', 'OP01'), ('PA', 'OP01')]))
        assert response.status_code >= 400, response.text
        message = response.json().get('message') or ''
        assert 'cùng một Part' in message
        assert 'OP01' in message
        assert db.execute('SELECT COUNT(*) n FROM templates WHERE upper(code)=upper(%s)',
                          (code,)).fetchone()['n'] == 0, 'nothing may be written'
        # ...and the rejected workbook is still archived for inspection.
        assert db.execute('SELECT COUNT(*) n FROM template_import_events WHERE upper(template_code)=upper(%s)',
                          (code,)).fetchone()['n'] == 1
    finally:
        _drop_template(db, code)
