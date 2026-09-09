"""Setup (chuẩn bị máy) as a linked support Operation.

The SETUP row is an ordinary `operations` record with operation_type='SETUP'
and parent_operation_id pointing at the production Operation it prepares, so
every existing mechanism -- QR, work_sessions, employee timeline, station --
works on it without a new concept. What it must never do is carry production
quantity, which is why it is excluded from rollups the same way REWORK is.

The procedure itself is ONE free-text field (`setup_note`) meant to be printed
on A4 and kept at the machine. The ESP kiosk has a small fixed screen, so it
never renders that text. Paper is the instruction; the device is the state.

HOW THE DEVICE SEES IT -- and this is the whole design constraint: the ESP is
a fixed terminal whose firmware is expensive to change, so setup must ride on
the interaction it ALREADY has. The SETUP row therefore carries its own label
and its own QR, and a worker does setup by scanning that label exactly the way
they scan any other Operation:

    scan card -> scan SETUP QR (session opens) -> scan card -> submit -> done

Not one new screen, not one new event type, zero firmware change. The backend
is what knows the session belongs to a SETUP row: it forces the quantities to
zero (a setup produces nothing) and stamps setup_completed_at on the parent --
see WorkSessionRepository._finish_within(). Whatever the operator types on the
keypad is ignored for a setup session, so the existing quantity screen needs
no special case either.

Validity rule, V1: `operations.setup_completed_at` on the PRODUCTION row is
the whole state. Finishing a setup session sets it; an admin clearing it
demands a fresh setup.

Identity note: the SETUP row gets an ID-based QR (`WF|OPID|<id>`) rather than
one derived from its code. Codes are only unique within a Part now, so a
payload built from a code cannot be a durable identifier -- see the operation
identity audit. The PRINTED text on that label is the display key instead
(`<part>-<op>-SU`), which is what makes it findable by a human.
"""
from __future__ import annotations

from mesflow.db.connection import fetch_one, transaction
from mesflow.db.repositories.base import ConflictError, NotFoundError

SETUP_QR_PREFIX = 'WF|OPID|'

# Human-readable key for screens, search and printed labels.
#
# A Template may reuse one Operation code (OP01) across several Parts, and
# operation_code_suffix() folds the Part in when instantiating them, so the
# stored code stays globally unique but is not always self-explanatory -- an
# Operation created by hand can still be a bare OP01. This pairs such a code
# with its Part while leaving alone any code that ALREADY names it
# (KM-3172005-08-OP02, or the SỬA HÀNG workbench's REWORK-41-KM-3172005-08),
# so nothing turns into a stutter. Derived and deterministic, never a key:
# identity stays operation.id, and a new label's payload stays WF|OPID|<id>.
#
# strpos(...) rather than LIKE ...||'%': psycopg reads a literal % in a
# parameterized statement as a placeholder and refuses the whole query, and
# this expression is spliced into statements that do take parameters.
DISPLAY_KEY_SQL = ("CASE WHEN strpos(upper({op}.code),upper({part}.code))>0 THEN {op}.code "
                   "ELSE {part}.code||'-'||{op}.code END")


def display_key_sql(op_alias: str = 'o', part_alias: str = 'p') -> str:
    return DISPLAY_KEY_SQL.format(op=op_alias, part=part_alias)


def setup_qr_for(operation_id: int) -> str:
    return f'{SETUP_QR_PREFIX}{int(operation_id)}'


def _load_operation(cur, operation_id: int):
    cur.execute("""SELECT o.id,o.code,o.name,o.operation_type,o.parent_operation_id,o.requires_setup,
            o.setup_completed_at,o.production_order_id,o.part_id,o.status,po.status po_status
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id
        WHERE o.id=%s FOR UPDATE OF o""", (int(operation_id),))
    row = cur.fetchone()
    if not row:
        raise NotFoundError('Không tìm thấy Operation')
    return row


# Deterministic suffix on the parent's code. Short on purpose: the label and
# the ESP's one-line operation field both have to hold it, and the display key
# it lands in is already Part-qualified (KM-3172005-08-OP02-SU).
SETUP_CODE_SUFFIX = '-SU'


def _create_setup_row(cur, parent):
    """One SETUP per production Operation; the partial unique index enforces it."""
    code = f"{parent['code']}{SETUP_CODE_SUFFIX}"
    cur.execute("""INSERT INTO operations(production_order_id,part_id,code,name,done_qty,defect_qty,
            rework_qty,scrap_qty,status,sort_order,qr,operation_type,parent_operation_id)
        VALUES(%s,%s,%s,%s,0,0,0,0,'PLANNED',%s,%s,'SETUP',%s) RETURNING id""",
        (parent['production_order_id'], parent['part_id'], code,
         f"Setup {parent['name']}", 2147483646, f'PENDING-{parent["id"]}', parent['id']))
    setup_id = cur.fetchone()['id']
    # QR is assigned from the immutable id, which only exists after the insert.
    cur.execute('UPDATE operations SET qr=%s WHERE id=%s', (setup_qr_for(setup_id), setup_id))
    return setup_id


class SetupRepository:
    def get_for_operation(self, operation_id: int):
        """Everything the OP detail card and the kiosk need about one Operation."""
        main = fetch_one(f"""SELECT o.id,o.code,o.name,o.operation_type,o.requires_setup,
                o.setup_completed_at,o.setup_completed_session_id,
                {display_key_sql('o','p')} display_key,p.code part_code
            FROM operations o LEFT JOIN parts p ON p.id=o.part_id
            WHERE o.id=%s""", (int(operation_id),))
        if not main:
            raise NotFoundError('Không tìm thấy Operation')
        setup = fetch_one(f"""SELECT o.id,o.code,o.name,o.expected_setup_minutes,o.qr,o.setup_note,
                {display_key_sql('o','p')} display_key
            FROM operations o LEFT JOIN parts p ON p.id=o.part_id
            WHERE o.parent_operation_id=%s AND o.operation_type='SETUP'""",
            (int(operation_id),))
        session = None
        if setup:
            # The latest setup session drives the card: who did it, when, how
            # long, and whether one is running right now.
            session = fetch_one("""SELECT ws.id,ws.status,ws.started_at,ws.ended_at,
                    GREATEST(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)::bigint duration_seconds,
                    e.employee_no,e.name employee_name
                FROM work_sessions ws LEFT JOIN employees e ON e.id=ws.employee_id
                WHERE ws.operation_id=%s ORDER BY ws.started_at DESC,ws.id DESC LIMIT 1""",
                (setup['id'],))
        done = bool(main.get('setup_completed_at'))
        running = bool(session and session['status'] == 'OPEN')
        state = 'NOT_REQUIRED' if not main.get('requires_setup') else (
            'DONE' if done else ('RUNNING' if running else 'PENDING'))
        return {'operation': dict(main), 'setup': dict(setup) if setup else None,
                'last_session': dict(session) if session else None,
                'state': state, 'setup_done': done}

    def configure(self, operation_id: int, data: dict):
        """Turn the requirement on/off and save its config in one transaction.

        Creating the SETUP row is the system's job, not the user's -- ticking
        the box on the production Operation is the whole interaction.
        """
        requires = bool(data.get('requires_setup'))
        minutes = data.get('expected_setup_minutes')
        minutes = int(minutes) if str(minutes or '').strip() not in ('', 'None') else None
        if minutes is not None and minutes < 0:
            raise ValueError('Thời gian setup không hợp lệ')
        note = str(data.get('setup_note') or '')
        with transaction() as conn:
            with conn.cursor() as cur:
                main = _load_operation(cur, operation_id)
                if main['operation_type'] != 'PRODUCTION':
                    raise ConflictError('Chỉ Operation sản xuất mới cấu hình được setup.')
                cur.execute("""SELECT id FROM operations
                    WHERE parent_operation_id=%s AND operation_type='SETUP' FOR UPDATE""", (main['id'],))
                existing = cur.fetchone()
                if not requires:
                    # Keep the SETUP row and its instructions: switching the
                    # requirement back on must not lose them, and any session
                    # already recorded against it is real history.
                    cur.execute('UPDATE operations SET requires_setup=FALSE,updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                                (main['id'],))
                    return {'ok': True, 'requires_setup': False,
                            'setup_operation_id': existing['id'] if existing else None}
                setup_id = existing['id'] if existing else _create_setup_row(cur, main)
                cur.execute("""UPDATE operations SET expected_setup_minutes=%s,updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s""", (minutes, setup_id))
                cur.execute('UPDATE operations SET requires_setup=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                            (main['id'],))
                cur.execute('UPDATE operations SET setup_note=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                            (note, setup_id))
                return {'ok': True, 'requires_setup': True, 'setup_operation_id': setup_id}

    def complete(self, session_id: int, *, actor_username: str = ''):
        """Finish a setup session from the web kiosk.

        Thin on purpose: the completion rule lives in
        WorkSessionRepository._finish_within(), which is what the ESP's
        ordinary quantity submit goes through too. Two screens, one rule --
        this endpoint exists only so the browser kiosk does not have to
        invent a request_id/quantity payload for a session that has neither.
        """
        session = fetch_one("""SELECT ws.id,ws.status FROM work_sessions ws
            JOIN operations o ON o.id=ws.operation_id
            WHERE ws.id=%s AND o.operation_type='SETUP'""", (int(session_id),))
        if not session:
            raise NotFoundError('Không tìm thấy phiên setup')
        if session['status'] != 'OPEN':
            raise ConflictError('Phiên setup này đã hoàn tất.')
        from mesflow.db.repositories.execution import WorkSessionRepository
        result = WorkSessionRepository().finish(int(session_id), {
            'request_id': f'setup-complete-{int(session_id)}',
            'good_qty': 0, 'defect_qty': 0, 'rework_qty': 0, 'note': 'Hoàn tất setup máy',
        }, audit_actor_username=actor_username)
        closed = result['session']
        return {'ok': True, 'session_id': int(session_id),
                'parent_operation_id': fetch_one(
                    "SELECT parent_operation_id FROM operations WHERE id=%s",
                    (closed['operation_id'],))['parent_operation_id'],
                'setup_completed': True}

    def reset(self, operation_id: int):
        """Demand a fresh setup for this Operation (admin action)."""
        with transaction() as conn:
            with conn.cursor() as cur:
                main = _load_operation(cur, operation_id)
                cur.execute("""UPDATE operations SET setup_completed_at=NULL,
                    setup_completed_session_id=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=%s""", (main['id'],))
        return {'ok': True, 'operation_id': int(operation_id), 'setup_completed': False}

    def print_sheet(self, operation_id: int):
        """Everything the printed A4 sheet shows, for a main OP or its SETUP.

        Accepts either id so the print button works from both screens.
        """
        row = fetch_one("""SELECT o.id,o.code,o.name,o.operation_type,o.parent_operation_id
            FROM operations o WHERE o.id=%s""", (int(operation_id),))
        if not row:
            raise NotFoundError('Không tìm thấy Operation')
        main_id = row['parent_operation_id'] if row['operation_type'] == 'SETUP' else row['id']
        sheet = fetch_one(f"""SELECT m.id main_id,m.code main_code,m.name main_name,
                m.requires_setup,m.setup_completed_at,
                {display_key_sql('m','p')} main_display_key,
                {display_key_sql('s','p')} setup_display_key,
                s.id setup_id,s.code setup_code,s.name setup_name,s.setup_note,
                s.expected_setup_minutes,s.qr setup_qr,s.updated_at setup_updated_at,
                p.code part_code,p.name part_name,po.code po_code,po.product,
                e.code equipment_code,e.name equipment_name
            FROM operations m
            LEFT JOIN operations s ON s.parent_operation_id=m.id AND s.operation_type='SETUP'
            LEFT JOIN parts p ON p.id=m.part_id
            LEFT JOIN production_orders po ON po.id=m.production_order_id
            LEFT JOIN equipment e ON e.id=m.equipment_id
            WHERE m.id=%s""", (int(main_id),))
        if not sheet or not sheet.get('setup_id'):
            raise NotFoundError('Operation này chưa có hướng dẫn setup')
        return dict(sheet)
