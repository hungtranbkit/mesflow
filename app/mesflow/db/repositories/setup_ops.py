"""Setup (chuẩn bị máy) as a linked support Operation.

The SETUP row is an ordinary `operations` record with operation_type='SETUP'
and parent_operation_id pointing at the production Operation it prepares, so
every existing mechanism -- QR, work_sessions, employee timeline, station --
works on it without a new concept. What it must never do is carry production
quantity, which is why it is excluded from rollups the same way REWORK is.

Validity rule, V1: `operations.setup_completed_at` on the PRODUCTION row is
the whole state. Finishing a setup session with every required step ticked
sets it; an admin clearing it demands a fresh setup. One sentence, one column,
testable -- no invented notion of a batch or shift.

Identity note: the SETUP row gets an ID-based QR (`WF|OPID|<id>`) rather than
one derived from its code. Codes are only unique within a Part now, so a
payload built from a code cannot be a durable identifier -- see the operation
identity audit. Nothing here relies on a globally unique code.
"""
from __future__ import annotations

from mesflow.db.connection import fetch_all, fetch_one, transaction
from mesflow.db.repositories.base import ConflictError, NotFoundError

SETUP_QR_PREFIX = 'WF|OPID|'


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


def _create_setup_row(cur, parent):
    """One SETUP per production Operation; the partial unique index enforces it."""
    code = f"{parent['code']}-SETUP"
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
        """Everything the kiosk and the admin screen need about one Operation."""
        main = fetch_one("""SELECT id,code,name,operation_type,requires_setup,setup_completed_at,
                setup_completed_session_id FROM operations WHERE id=%s""", (int(operation_id),))
        if not main:
            raise NotFoundError('Không tìm thấy Operation')
        setup = fetch_one("""SELECT id,code,name,expected_setup_minutes,qr FROM operations
            WHERE parent_operation_id=%s AND operation_type='SETUP'""", (int(operation_id),))
        steps = []
        if setup:
            steps = fetch_all("""SELECT id,sort_order,instruction,required,active FROM setup_steps
                WHERE setup_operation_id=%s AND active ORDER BY sort_order,id""", (setup['id'],))
        return {'operation': dict(main), 'setup': dict(setup) if setup else None,
                'steps': [dict(s) for s in steps],
                'setup_done': bool(main.get('setup_completed_at'))}

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
        steps = list(data.get('steps') or [])
        with transaction() as conn:
            with conn.cursor() as cur:
                main = _load_operation(cur, operation_id)
                if main['operation_type'] != 'PRODUCTION':
                    raise ConflictError('Chỉ Operation sản xuất mới cấu hình được setup.')
                cur.execute("""SELECT id FROM operations
                    WHERE parent_operation_id=%s AND operation_type='SETUP' FOR UPDATE""", (main['id'],))
                existing = cur.fetchone()
                if not requires:
                    # Keep the SETUP row and its checklist: switching the
                    # requirement back on must not lose the instructions, and
                    # any session already recorded against it is real history.
                    cur.execute('UPDATE operations SET requires_setup=FALSE,updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                                (main['id'],))
                    return {'ok': True, 'requires_setup': False,
                            'setup_operation_id': existing['id'] if existing else None}
                setup_id = existing['id'] if existing else _create_setup_row(cur, main)
                cur.execute("""UPDATE operations SET expected_setup_minutes=%s,updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s""", (minutes, setup_id))
                cur.execute('UPDATE operations SET requires_setup=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                            (main['id'],))
                if data.get('steps') is not None:
                    self._replace_steps(cur, setup_id, steps)
                return {'ok': True, 'requires_setup': True, 'setup_operation_id': setup_id}

    @staticmethod
    def _replace_steps(cur, setup_operation_id: int, steps):
        """Whole-list replace: the editor always sends the list it shows."""
        cleaned = []
        for idx, step in enumerate(steps):
            instruction = str(step.get('instruction') or '').strip()
            if not instruction:
                continue
            cleaned.append((instruction, bool(step.get('required', True)),
                            int(step.get('sort_order', idx))))
        if not cleaned:
            cur.execute('DELETE FROM setup_steps WHERE setup_operation_id=%s', (setup_operation_id,))
            return
        # Steps already ticked in a past session are referenced by
        # setup_step_results; deleting them would erase that history, so rows
        # are deactivated rather than removed once they have been used.
        cur.execute("""UPDATE setup_steps s SET active=FALSE,updated_at=CURRENT_TIMESTAMP
            WHERE s.setup_operation_id=%s""", (setup_operation_id,))
        for instruction, required, sort_order in cleaned:
            cur.execute("""SELECT id FROM setup_steps
                WHERE setup_operation_id=%s AND instruction=%s LIMIT 1""",
                (setup_operation_id, instruction))
            found = cur.fetchone()
            if found:
                cur.execute("""UPDATE setup_steps SET sort_order=%s,required=%s,active=TRUE,
                        updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                    (sort_order, required, found['id']))
            else:
                cur.execute("""INSERT INTO setup_steps(setup_operation_id,sort_order,instruction,required)
                    VALUES(%s,%s,%s,%s)""", (setup_operation_id, sort_order, instruction, required))
        cur.execute("""DELETE FROM setup_steps s WHERE s.setup_operation_id=%s AND NOT s.active
            AND NOT EXISTS(SELECT 1 FROM setup_step_results r WHERE r.setup_step_id=s.id)""",
            (setup_operation_id,))

    def mark_step(self, session_id: int, step_id: int, *, employee_id=None, done: bool = True):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT ws.id,ws.status,ws.employee_id,o.id operation_id,o.operation_type
                    FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
                    WHERE ws.id=%s FOR UPDATE OF ws""", (int(session_id),))
                session = cur.fetchone()
                if not session:
                    raise NotFoundError('Không tìm thấy phiên setup')
                if session['operation_type'] != 'SETUP':
                    raise ConflictError('Phiên này không phải phiên setup.')
                if session['status'] != 'OPEN':
                    raise ConflictError('Phiên setup đã kết thúc, không đánh dấu thêm được.')
                cur.execute('SELECT id FROM setup_steps WHERE id=%s AND setup_operation_id=%s',
                            (int(step_id), session['operation_id']))
                if not cur.fetchone():
                    raise NotFoundError('Bước setup không thuộc Operation này')
                if done:
                    cur.execute("""INSERT INTO setup_step_results(session_id,setup_step_id,employee_id)
                        VALUES(%s,%s,%s) ON CONFLICT (session_id,setup_step_id) DO NOTHING""",
                        (int(session_id), int(step_id), employee_id or session['employee_id']))
                else:
                    cur.execute('DELETE FROM setup_step_results WHERE session_id=%s AND setup_step_id=%s',
                                (int(session_id), int(step_id)))
        return self.session_progress(session_id)

    def session_progress(self, session_id: int):
        row = fetch_one("""SELECT ws.id,ws.status,o.id setup_operation_id,o.parent_operation_id
            FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
            WHERE ws.id=%s AND o.operation_type='SETUP'""", (int(session_id),))
        if not row:
            raise NotFoundError('Không tìm thấy phiên setup')
        steps = fetch_all("""SELECT s.id,s.sort_order,s.instruction,s.required,
                (r.id IS NOT NULL) done
            FROM setup_steps s
            LEFT JOIN setup_step_results r ON r.setup_step_id=s.id AND r.session_id=%s
            WHERE s.setup_operation_id=%s AND s.active ORDER BY s.sort_order,s.id""",
            (int(session_id), row['setup_operation_id']))
        missing = [dict(s) for s in steps if s['required'] and not s['done']]
        return {'session_id': row['id'], 'setup_operation_id': row['setup_operation_id'],
                'parent_operation_id': row['parent_operation_id'],
                'steps': [dict(s) for s in steps], 'missing_required': missing,
                'can_complete': not missing}

    def complete(self, session_id: int, *, actor_username: str = ''):
        """Finish a setup session and unlock its production Operation.

        Refuses while a required step is unticked, and refuses a second time
        so a retried click cannot double-complete.
        """
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT ws.id,ws.status,ws.employee_id,o.id setup_operation_id,
                        o.parent_operation_id
                    FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id
                    WHERE ws.id=%s AND o.operation_type='SETUP' FOR UPDATE OF ws""", (int(session_id),))
                session = cur.fetchone()
                if not session:
                    raise NotFoundError('Không tìm thấy phiên setup')
                if session['status'] != 'OPEN':
                    raise ConflictError('Phiên setup này đã hoàn tất.')
                cur.execute("""SELECT s.id,s.instruction FROM setup_steps s
                    WHERE s.setup_operation_id=%s AND s.active AND s.required
                      AND NOT EXISTS(SELECT 1 FROM setup_step_results r
                                     WHERE r.setup_step_id=s.id AND r.session_id=%s)
                    ORDER BY s.sort_order,s.id""", (session['setup_operation_id'], int(session_id)))
                missing = cur.fetchall()
                if missing:
                    names = ', '.join(str(m['instruction'])[:40] for m in missing[:3])
                    raise ConflictError(
                        f'Còn {len(missing)} bước bắt buộc chưa hoàn thành: {names}. '
                        'Hoàn thành đủ các bước bắt buộc rồi mới kết thúc setup.')
                cur.execute("""UPDATE work_sessions SET status='CLOSED',ended_at=CURRENT_TIMESTAMP,
                        good_qty=0,defect_qty=0,rework_qty=0,scrap_qty=0,quantity_confirmed=TRUE,
                        updated_at=CURRENT_TIMESTAMP WHERE id=%s""", (int(session_id),))
                cur.execute("""UPDATE operations SET setup_completed_at=CURRENT_TIMESTAMP,
                        setup_completed_session_id=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                    (int(session_id), session['parent_operation_id']))
        return {'ok': True, 'session_id': int(session_id),
                'parent_operation_id': session['parent_operation_id'], 'setup_completed': True}

    def reset(self, operation_id: int):
        """Demand a fresh setup for this Operation (admin action)."""
        with transaction() as conn:
            with conn.cursor() as cur:
                main = _load_operation(cur, operation_id)
                cur.execute("""UPDATE operations SET setup_completed_at=NULL,
                    setup_completed_session_id=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=%s""", (main['id'],))
        return {'ok': True, 'operation_id': int(operation_id), 'setup_completed': False}
