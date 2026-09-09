"""SETUP as a linked support Operation -- the A..I matrix from the brief.

SETUP is an ordinary `operations` row (operation_type='SETUP') hanging off its
production Operation by parent_operation_id, so it reuses QR, work_sessions,
employee timeline and station unchanged. It carries no production quantity and
stays out of every production rollup, exactly as REWORK does; its TIME is real
work and stays in the employee day view.

Setup is NOT a prerequisite (changed 2026-09-09). A linked SETUP row means
only that this Operation has related setup work; production never waits for
it, nothing expires, and there is no reset. What is recorded is history: when
setup last ran and who did it.
"""
import uuid

import pytest

from conftest import BASE_URL

pytestmark = pytest.mark.postgres


def _start(api, employee_id, operation_id, station_id=None):
    return api.post(f'{BASE_URL}/api/work-sessions/start', json={
        'request_id': f'SETUP-START-{uuid.uuid4()}', 'employee_id': employee_id,
        'operation_id': operation_id, 'station_id': station_id, 'device_uuid': 'TEST-SETUP',
    }, timeout=15)


def _finish(api, session_id, good=0, defect=0):
    return api.post(f'{BASE_URL}/api/work-sessions/{session_id}/finish', json={
        'request_id': f'SETUP-FINISH-{uuid.uuid4()}', 'good_qty': good, 'defect_qty': defect,
        'rework_qty': 0}, timeout=15)


SETUP_NOTE = ("1. Lắp khuôn số 3, siết đủ lực\n"
              "2. Căn tâm theo dưỡng, sai lệch tối đa 0.05mm\n"
              "3. Chạy thử 2 sản phẩm, đo kiểm trước khi chạy loạt")


def _configure(api, operation_id, *, requires=True, minutes=15, note=SETUP_NOTE):
    return api.put(f'{BASE_URL}/api/operations/{operation_id}/setup', json={
        'requires_setup': requires, 'expected_setup_minutes': minutes,
        'setup_note': note}, timeout=15)


def _setup_of(api, operation_id):
    response = api.get(f'{BASE_URL}/api/operations/{operation_id}/setup', timeout=15)
    assert response.status_code == 200, response.text
    return response.json()


def test_A_operation_without_setup_starts_normally(api, seeded_factory):
    graph = seeded_factory
    response = _start(api, graph['employee_id'], graph['operation_id'], graph['station_id'])
    assert response.status_code == 201, response.text


def test_B_configuring_setup_creates_the_linked_row_and_blocks_nothing(api, db, seeded_factory):
    """Setup is related work, not a precondition.

    This test used to assert the opposite -- that production was refused with
    409 until setup ran. That rule was removed on 2026-09-09: one setup can
    serve many runs, and the dispatcher decides when it is worth doing.
    """
    graph = seeded_factory
    assert _configure(api, graph['operation_id']).status_code == 200
    allowed = _start(api, graph['employee_id'], graph['operation_id'], graph['station_id'])
    assert allowed.status_code == 201, allowed.text
    state = _setup_of(api, graph['operation_id'])
    assert state['setup'] is not None
    assert state['state'] == 'NEVER'
    assert state['ever_completed'] is False
    # One free-text instruction, newlines preserved for the printed sheet.
    assert state['setup']['setup_note'] == SETUP_NOTE
    assert '\n' in state['setup']['setup_note']
    row = db.execute("""SELECT operation_type,parent_operation_id,qr FROM operations WHERE id=%s""",
                     (state['setup']['id'],)).fetchone()
    assert row['operation_type'] == 'SETUP'
    assert row['parent_operation_id'] == graph['operation_id']
    # Identity is the immutable id, not a code that may repeat across Parts.
    assert row['qr'] == f"WF|OPID|{state['setup']['id']}"


def test_C_the_instruction_sheet_prints_with_the_note_intact(api, seeded_factory):
    """Paper is the instruction: the sheet must carry the note verbatim.

    Replaces the old "cannot complete while a required step is unticked" case --
    the checklist is gone (0048). The ESP screen is small and fixed, so the
    procedure is printed and kept at the machine instead.
    """
    graph = seeded_factory
    _configure(api, graph['operation_id'])
    page = api.get(f"{BASE_URL}/print/setup/{graph['operation_id']}", timeout=15)
    assert page.status_code == 200, page.text
    html = page.text
    assert 'HƯỚNG DẪN SETUP MÁY' in html
    for line in SETUP_NOTE.split('\n'):
        assert line in html, f'missing instruction line: {line}'
    assert '15 phút' in html
    # white-space:pre-wrap is what keeps the operator's own numbering readable.
    assert 'pre-wrap' in html
    # The SETUP id resolves to the same sheet, so the button works from both.
    setup_id = _setup_of(api, graph['operation_id'])['setup']['id']
    assert api.get(f'{BASE_URL}/print/setup/{setup_id}', timeout=15).status_code == 200


def _complete_setup(api, graph):
    """start setup -> work from the printed sheet -> one confirmation."""
    setup = _setup_of(api, graph['operation_id'])
    session_id = _start(api, graph['employee_id'], setup['setup']['id'],
                        graph['station_id']).json()['session']['id']
    done = api.post(f'{BASE_URL}/api/setup-sessions/{session_id}/complete', timeout=15)
    assert done.status_code == 200, done.text
    return session_id


def test_D_production_starts_the_same_before_and_after_setup(api, seeded_factory):
    """State-independent: the answer must not depend on setup history."""
    graph = seeded_factory
    _configure(api, graph['operation_id'])
    before = _start(api, graph['employee_id'], graph['operation_id'], graph['station_id'])
    assert before.status_code == 201, before.text
    api.post(f"{BASE_URL}/api/work-sessions/{before.json()['session']['id']}/finish",
             json={'request_id': f'SETUP-FIN-{uuid.uuid4()}', 'good_qty': 1,
                   'defect_qty': 0, 'rework_qty': 0}, timeout=15)
    _complete_setup(api, graph)
    assert _setup_of(api, graph['operation_id'])['ever_completed'] is True
    after = _start(api, graph['employee_id'], graph['operation_id'], graph['station_id'])
    assert after.status_code == 201, after.text


def test_D2_setup_cannot_be_completed_twice(api, seeded_factory):
    """A retried click must not double-complete."""
    graph = seeded_factory
    _configure(api, graph['operation_id'])
    session_id = _complete_setup(api, graph)
    again = api.post(f'{BASE_URL}/api/setup-sessions/{session_id}/complete', timeout=15)
    assert again.status_code == 409, again.text


def test_E_a_second_worker_does_not_setup_again(api, db, seeded_factory):
    graph = seeded_factory
    _configure(api, graph['operation_id'])
    _complete_setup(api, graph)
    with db.cursor() as cur:
        cur.execute("""INSERT INTO employees(employee_no,name,department,position,qr)
            VALUES(%s,'Thợ thứ hai','TEST','Worker',%s) RETURNING id""",
            (f"T2-{graph['suffix']}", f"WF|EMP|T2-{graph['suffix']}"))
        second = cur.fetchone()['id']
    try:
        response = _start(api, second, graph['operation_id'], graph['station_id'])
        assert response.status_code == 201, response.text
    finally:
        with db.cursor() as cur:
            cur.execute('DELETE FROM work_sessions WHERE employee_id=%s', (second,))
            cur.execute('DELETE FROM employees WHERE id=%s', (second,))


def test_F_setup_time_counts_as_work_but_never_as_production(api, db, seeded_factory):
    graph = seeded_factory
    _configure(api, graph['operation_id'])
    setup_session = _complete_setup(api, graph)
    op = db.execute("""SELECT done_qty,defect_qty,status FROM operations WHERE id=%s""",
                    (graph['operation_id'],)).fetchone()
    assert (op['done_qty'], op['defect_qty']) == (0, 0), 'setup must not add production quantity'

    setup_id = _setup_of(api, graph['operation_id'])['setup']['id']
    # The session is real, closed, and carries no quantity.
    session = db.execute("""SELECT status,good_qty,defect_qty FROM work_sessions WHERE id=%s""",
                         (setup_session,)).fetchone()
    assert session['status'] == 'CLOSED'
    assert (session['good_qty'], session['defect_qty']) == (0, 0)

    # It shows up as working time in the day view...
    today = db.execute("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh')::date d").fetchone()['d']
    day = api.get(f'{BASE_URL}/api/dashboard/day?date={today}&limit=1000', timeout=20).json()
    assert [x for x in day['sessions'] if x['operation_id'] == setup_id], \
        'setup time must appear in Ngày công theo nhân viên'
    # ...and nowhere in production progress.
    assert not [x for x in day['items'] if x['operation_id'] == setup_id]

    overview = api.get(f'{BASE_URL}/api/dashboard/overview', timeout=20).json()
    assert not [x for x in overview['operations'] if x['operation_id'] == setup_id]
    po_row = next(x for x in overview['production_orders'] if x['po_id'] == graph['po_id'])
    assert po_row['operation_count'] == 1, 'SETUP must not inflate the Operation count'


def test_F2_setup_is_not_reported_as_missing_a_standard(api, db, seeded_factory):
    """Support work has no production standard by nature -- same as REWORK."""
    graph = seeded_factory
    _configure(api, graph['operation_id'])
    _complete_setup(api, graph)
    report = api.get(f'{BASE_URL}/api/reports/employee-productivity', timeout=20)
    assert report.status_code == 200, report.text
    row = next((x for x in report.json()['employees']
                if x['employee_id'] == graph['employee_id']), None)
    if row:
        assert row['repair_sessions'] >= 1, 'support work is counted in its own bucket'


def test_G_template_clone_carries_the_setup_and_its_instructions(api, db, seeded_factory):
    graph = seeded_factory
    suffix = uuid.uuid4().hex[:6].upper()
    template_code = f'TPL-SETUP-{suffix}'
    po_code = f'PO-SETUP-{suffix}'
    try:
        with db.cursor() as cur:
            cur.execute("""INSERT INTO templates(code,name,product,version,active)
                VALUES(%s,'Tpl setup','SP','1.0',true) RETURNING id""", (template_code,))
            template_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO template_parts(template_id,code,name,sort_order)
                VALUES(%s,%s,'Part',0) RETURNING id""", (template_id, f'PS-{suffix}'))
            part_id = cur.fetchone()['id']
            cur.execute("""INSERT INTO template_operations(template_id,part_id,code,name,sort_order,
                    standard_seconds_per_unit,repair_cycle_time_seconds_per_unit,
                    requires_setup,expected_setup_minutes,setup_note)
                VALUES(%s,%s,%s,'CẮT',0,10,0,TRUE,25,%s) RETURNING id""",
                (template_id, part_id, f'PS-{suffix}-OP01', SETUP_NOTE))
            cur.fetchone()

        created = api.post(f'{BASE_URL}/api/templates/{template_id}/instantiate',
                           json={'code': po_code, 'planned_quantity': 10}, timeout=25)
        assert created.status_code in (200, 201), created.text

        rows = db.execute("""SELECT o.id,o.code,o.operation_type,o.parent_operation_id,
                o.requires_setup,o.expected_setup_minutes
            FROM operations o JOIN production_orders po ON po.id=o.production_order_id
            WHERE po.code=%s ORDER BY o.operation_type""", (po_code,)).fetchall()
        main = next(r for r in rows if r['operation_type'] == 'PRODUCTION')
        setup = next(r for r in rows if r['operation_type'] == 'SETUP')
        assert main['requires_setup'] is True
        # Parent points at the NEW operation id, not the template's.
        assert setup['parent_operation_id'] == main['id']
        assert setup['expected_setup_minutes'] == 25
        note = db.execute('SELECT setup_note FROM operations WHERE id=%s',
                          (setup['id'],)).fetchone()['setup_note']
        assert note == SETUP_NOTE, 'the printed instruction must survive the clone'
        # Exactly one SETUP -- no duplicate from a retried save.
        assert len([r for r in rows if r['operation_type'] == 'SETUP']) == 1
    finally:
        with db.cursor() as cur:
            cur.execute("""DELETE FROM operations WHERE production_order_id IN
                (SELECT id FROM production_orders WHERE code=%s)""", (po_code,))
            cur.execute("""DELETE FROM parts WHERE production_order_id IN
                (SELECT id FROM production_orders WHERE code=%s)""", (po_code,))
            cur.execute('DELETE FROM production_orders WHERE code=%s', (po_code,))
            cur.execute("""DELETE FROM template_operations WHERE template_id IN
                (SELECT id FROM templates WHERE code=%s)""", (template_code,))
            cur.execute("""DELETE FROM template_parts WHERE template_id IN
                (SELECT id FROM templates WHERE code=%s)""", (template_code,))
            cur.execute('DELETE FROM templates WHERE code=%s', (template_code,))


def test_H_configuring_setup_twice_does_not_duplicate_the_linked_row(api, db, seeded_factory):
    graph = seeded_factory
    _configure(api, graph['operation_id'])
    _configure(api, graph['operation_id'], minutes=30)
    rows = db.execute("""SELECT id FROM operations WHERE parent_operation_id=%s
        AND operation_type='SETUP'""", (graph['operation_id'],)).fetchall()
    assert len(rows) == 1, 'one SETUP per production Operation'
    assert _setup_of(api, graph['operation_id'])['setup']['expected_setup_minutes'] == 30


def test_H2_detaching_setup_keeps_the_instructions(api, seeded_factory):
    graph = seeded_factory
    _configure(api, graph['operation_id'])
    off = api.put(f"{BASE_URL}/api/operations/{graph['operation_id']}/setup",
                  json={'requires_setup': False}, timeout=15)
    assert off.status_code == 200, off.text
    # Instructions survive so switching it back on does not lose them.
    assert _setup_of(api, graph['operation_id'])['setup']['setup_note'] == SETUP_NOTE


def test_I_rework_classification_survives_the_new_operation_type(api, db, seeded_factory):
    """is_rework_op is now derived from operation_type -- it must still work."""
    graph = seeded_factory
    started = _start(api, graph['employee_id'], graph['operation_id'], graph['station_id'])
    assert _finish(api, started.json()['session']['id'], good=90, defect=6).status_code == 200
    resolved = api.post(f"{BASE_URL}/api/rework/queue/{started.json()['session']['id']}/resolve",
                        json={'request_id': f'SETUP-RW-{uuid.uuid4()}',
                              'employee_id': graph['employee_id'], 'repaired_qty': 2}, timeout=20)
    assert resolved.status_code == 200, resolved.text
    row = db.execute("""SELECT operation_type,is_rework_op FROM operations
        WHERE production_order_id=%s AND operation_type='REWORK'""", (graph['po_id'],)).fetchone()
    assert row['is_rework_op'] is True, 'the generated column must track operation_type'


def test_K_two_parts_sharing_one_template_op_code_get_distinct_setup_labels(api, db):
    """The collision case, taken through the path that actually creates it.

    A Template may use OP01 in every Part -- that is the whole point of the
    per-Part scoping. operation_code_suffix() folds the Part into the stored
    code when the PO is created, so operations.code stays globally unique (the
    DB enforces it) and the two OP01s become two different rows, each with its
    own SETUP label. Nothing anywhere resolves an Operation by a code that
    could name two rows.
    """
    suffix = uuid.uuid4().hex[:6].upper()
    template_code, po_code = f'TPL-DUP-{suffix}', f'PO-DUP-{suffix}'
    part_a, part_b = f'PA-{suffix}', f'PB-{suffix}'
    try:
        with db.cursor() as cur:
            cur.execute("""INSERT INTO templates(code,name,product,version,active)
                VALUES(%s,'Tpl trùng mã OP','SP','1.0',true) RETURNING id""", (template_code,))
            template_id = cur.fetchone()['id']
            for order, part_code in enumerate((part_a, part_b)):
                cur.execute("""INSERT INTO template_parts(template_id,code,name,sort_order)
                    VALUES(%s,%s,%s,%s) RETURNING id""", (template_id, part_code, f'Part {part_code}', order))
                tpl_part = cur.fetchone()['id']
                # The SAME Operation code in both Parts -- legal by design.
                cur.execute("""INSERT INTO template_operations(template_id,part_id,code,name,sort_order,
                        standard_seconds_per_unit,repair_cycle_time_seconds_per_unit,
                        requires_setup,expected_setup_minutes,setup_note)
                    VALUES(%s,%s,'OP01','Cắt',0,10,0,TRUE,15,%s)""", (template_id, tpl_part, SETUP_NOTE))

        created = api.post(f'{BASE_URL}/api/templates/{template_id}/instantiate',
                           json={'code': po_code, 'planned_quantity': 10}, timeout=25)
        assert created.status_code in (200, 201), created.text

        rows = db.execute("""SELECT o.id,o.code,o.operation_type,o.parent_operation_id,o.qr,p.code part_code
            FROM operations o JOIN parts p ON p.id=o.part_id
            JOIN production_orders po ON po.id=o.production_order_id
            WHERE po.code=%s ORDER BY p.code,o.operation_type""", (po_code,)).fetchall()
        mains = [r for r in rows if r['operation_type'] == 'PRODUCTION']
        setups = [r for r in rows if r['operation_type'] == 'SETUP']
        assert len(mains) == 2 and len(setups) == 2

        # One template code, two distinct stored codes: the PO and the Part are
        # both folded in, which is what keeps operations.code globally unique.
        assert len({r['code'] for r in mains}) == 2, mains
        assert {r['code'] for r in mains} == {f'{po_code}-{part_a}-OP01', f'{po_code}-{part_b}-OP01'}
        # Each SETUP hangs off its own parent, with its own label and payload.
        assert {r['code'] for r in setups} == {f'{po_code}-{part_a}-OP01-SU',
                                               f'{po_code}-{part_b}-OP01-SU'}
        assert {r['parent_operation_id'] for r in setups} == {r['id'] for r in mains}
        for setup in setups:
            assert setup['qr'] == f"WF|OPID|{setup['id']}"

        # What the screens show is the same unambiguous text, per Part.
        for main in mains:
            state = _setup_of(api, main['id'])
            assert state['operation']['display_key'] == main['code']
            assert state['setup']['display_key'] == f"{main['code']}-SU"
    finally:
        with db.cursor() as cur:
            cur.execute("""DELETE FROM operations WHERE production_order_id IN
                (SELECT id FROM production_orders WHERE code=%s)""", (po_code,))
            cur.execute("""DELETE FROM parts WHERE production_order_id IN
                (SELECT id FROM production_orders WHERE code=%s)""", (po_code,))
            cur.execute('DELETE FROM production_orders WHERE code=%s', (po_code,))
            cur.execute("""DELETE FROM template_operations WHERE template_id IN
                (SELECT id FROM templates WHERE code=%s)""", (template_code,))
            cur.execute("""DELETE FROM template_parts WHERE template_id IN
                (SELECT id FROM templates WHERE code=%s)""", (template_code,))
            cur.execute('DELETE FROM templates WHERE code=%s', (template_code,))
