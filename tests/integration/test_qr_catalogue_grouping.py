"""The QR catalogue has to carry enough structure for a human to find a job.

The screen groups by PO -> Part and sorts by routing order, and people search
by the Vietnamese name of the work ("Chấn mép"), not by a code. None of that is
possible unless the API returns the Part and the sequence as real fields --
before 2026-09-09 the Part existed only inside one pre-formatted `detail`
string and SETUP was detectable only by finding the words ' · Setup máy' in it.
"""
from __future__ import annotations

import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _labels(api, **params):
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    response = api.get(f'{BASE_URL}/api/qr-labels?type=OPERATION&limit=3000&{query}', timeout=25)
    assert response.status_code == 200, response.text
    return response.json()['items']


@pytest.fixture
def routing_graph(db):
    """One PO, two Parts, operations deliberately numbered so that sorting by
    code and sorting by routing sequence give DIFFERENT answers."""
    suffix = uuid.uuid4().hex[:8].upper()
    po_code = f'PO-QR-{suffix}'
    with db.cursor() as cur:
        cur.execute("INSERT INTO production_orders(code,product,planned_quantity,status) "
                    "VALUES(%s,'Thùng rác',100,'IN_PROGRESS') RETURNING id", (po_code,))
        po_id = cur.fetchone()['id']
        parts = {}
        for order, (code, name) in enumerate((('THAN', 'Thân thùng'), ('NAP', 'Nắp thùng'))):
            cur.execute("INSERT INTO parts(production_order_id,code,name,sort_order) "
                        "VALUES(%s,%s,%s,%s) RETURNING id", (po_id, f'{code}-{suffix}', name, order))
            parts[code] = cur.fetchone()['id']
        # sort_order 0,1,2 but codes OP10, OP2, OP1 -- sorting by code would
        # invert the real sequence, which is the bug this guards.
        ops = {}
        for part_code, rows in (
            ('THAN', [('OP10', 'Cắt phôi', 0), ('OP2', 'Chấn mép', 1), ('OP1', 'Hàn khung', 2)]),
            ('NAP', [('OP1', 'Dập nắp', 0)]),
        ):
            for code, name, order in rows:
                cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,status,qr,sort_order)
                    VALUES(%s,%s,%s,%s,'IN_PROGRESS',%s,%s) RETURNING id""",
                    (po_id, parts[part_code], f'{part_code}-{suffix}-{code}', name,
                     f'WF|OP|{part_code}-{suffix}-{code}', order))
                ops[f'{part_code}/{code}'] = cur.fetchone()['id']
    graph = dict(suffix=suffix, po_id=po_id, po_code=po_code, parts=parts, ops=ops)
    yield graph
    with db.cursor() as cur:
        cur.execute('DELETE FROM operations WHERE production_order_id=%s', (po_id,))
        cur.execute('DELETE FROM parts WHERE production_order_id=%s', (po_id,))
        cur.execute('DELETE FROM production_orders WHERE id=%s', (po_id,))


def test_catalogue_carries_part_and_sequence_as_real_fields(api, routing_graph):
    rows = [x for x in _labels(api, production_order_id=routing_graph['po_id'])]
    assert rows, 'the seeded PO must produce labels'
    for row in rows:
        for field in ('part_code', 'part_name', 'part_sort', 'operation_sort', 'operation_type'):
            assert field in row, f'{field} missing -- the screen cannot group or sort without it'
    than = next(x for x in rows if x['name'] == 'Chấn mép')
    assert than['part_name'] == 'Thân thùng'
    assert than['part_code'].startswith('THAN-')
    assert than['operation_type'] == 'PRODUCTION'


def test_catalogue_is_ordered_by_routing_not_by_code(api, routing_graph):
    """Sorting by code puts OP1 before OP2 before OP10 — the reverse of how the
    Part is actually machined."""
    rows = [x for x in _labels(api, production_order_id=routing_graph['po_id'])
            if x['part_name'] == 'Thân thùng']
    assert [x['name'] for x in rows] == ['Cắt phôi', 'Chấn mép', 'Hàn khung'], rows
    assert [x['operation_sort'] for x in rows] == [0, 1, 2]


def test_search_finds_work_by_its_vietnamese_name(api, routing_graph):
    """The whole point: somebody looks for 'Chấn mép', not for a code."""
    by_name = _labels(api, production_order_id=routing_graph['po_id'], q='Ch%E1%BA%A5n')
    assert [x['name'] for x in by_name] == ['Chấn mép'], by_name

    # ...and by the Part's Vietnamese name, which used to match nothing.
    by_part = _labels(api, production_order_id=routing_graph['po_id'], q='N%E1%BA%AFp')
    assert {x['name'] for x in by_part} == {'Dập nắp'}, by_part


def test_setup_labels_are_identifiable_without_reading_vietnamese_prose(api, db, routing_graph):
    """A SETUP label belongs in its own section under the Part, so the client
    has to be able to tell one apart from a field, not from a substring."""
    main_id = routing_graph['ops']['THAN/OP2']
    assert api.put(f'{BASE_URL}/api/operations/{main_id}/setup',
                   json={'requires_setup': True, 'setup_note': 'x'}, timeout=20).status_code == 200
    rows = _labels(api, production_order_id=routing_graph['po_id'])
    setups = [x for x in rows if x['operation_type'] == 'SETUP']
    assert len(setups) == 1, rows
    setup = setups[0]
    assert setup['parent_operation_id'] == main_id, 'the client groups it under its parent'
    assert setup['part_code'] == next(x['part_code'] for x in rows if x['id'] == main_id), \
        'a SETUP label must sit in the same Part as the Operation it prepares'
    assert setup['code'].endswith('-SU')


def test_setup_labels_are_named_after_the_work_not_the_suffix(api, routing_graph):
    """A person picking a tem must read what it is, not decode '-SU'."""
    main_id = routing_graph['ops']['THAN/OP2']          # "Chấn mép"
    api.put(f'{BASE_URL}/api/operations/{main_id}/setup',
            json={'requires_setup': True, 'setup_note': 'x'}, timeout=20)
    rows = _labels(api, production_order_id=routing_graph['po_id'])
    setup = next(x for x in rows if x['operation_type'] == 'SETUP')
    assert setup['parent_name'] == 'Chấn mép', \
        'the client renders "Setup · <parent name>" and needs the parent name'

    # ...and the word "setup" finds it, as does the parent's own name.
    assert any(x['operation_type'] == 'SETUP'
               for x in _labels(api, production_order_id=routing_graph['po_id'], q='setup'))
    by_parent = _labels(api, production_order_id=routing_graph['po_id'], q='Ch%E1%BA%A5n')
    assert {x['operation_type'] for x in by_parent} == {'PRODUCTION', 'SETUP'}, by_parent


def test_no_screen_or_api_still_says_setup_is_required(api, seeded_factory):
    """Wording regression: the prerequisite vocabulary is gone for good.

    Cheap to assert, and it is the part most likely to creep back — a state
    called PENDING or a label saying 'Cần setup' re-teaches the removed rule to
    whoever reads the code next.
    """
    graph = seeded_factory
    api.put(f"{BASE_URL}/api/operations/{graph['operation_id']}/setup",
            json={'requires_setup': True, 'setup_note': 'x'}, timeout=20)
    state = api.get(f"{BASE_URL}/api/operations/{graph['operation_id']}/setup", timeout=15).json()
    assert state['state'] in ('NONE', 'NEVER', 'RUNNING', 'DONE'), state
    assert 'PENDING' not in str(state), state
    assert 'NOT_REQUIRED' not in str(state), state

    app_js = (__import__('pathlib').Path(__file__).resolve().parents[2]
              / 'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    for banned in ('Yêu cầu setup máy trước khi sản xuất', 'Cần setup',
                   'Sản xuất đang bị chặn', 'Sản xuất đã được mở khóa', 'Yêu cầu setup lại'):
        assert banned not in app_js, f'prerequisite wording is back: {banned!r}'
