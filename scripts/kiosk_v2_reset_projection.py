#!/usr/bin/env python3
"""Kiosk v2 projection reset -- LOCAL_TEST only.

Fixes a real footgun hit earlier this session: an ad-hoc `UPDATE
kiosk_v2_projection SET state_name='WAIT_EMPLOYEE'...` was run to reset a
device's idle state for testing, without first checking whether a real,
OPEN Work Session was already pointed to by that projection row -- the
device had just been used for a real physical scan, and the reset briefly
orphaned that session from the device's view (caught and corrected in the
same session, but only by luck of noticing immediately).

This script is the deliberate, safe replacement for that raw UPDATE:
  - REFUSES to touch a projection row that points to an OPEN Work Session,
    by default. No silent overwrite, ever.
  - Only with --force-close-zero (an explicit, named opt-in) does it close
    that session -- and even then it goes through the REAL
    WorkSessionRepository.finish() (real validation, real idempotency, real
    audit trail), submitting GOOD=0/DEFECT=0/REWORK=0, never a raw UPDATE
    that bypasses business logic.
  - The CLI entry point (main(), below reset_projection()) hard-refuses to
    run against anything that doesn't look like the LOCAL_TEST environment
    (SERVER_ROLE=LOCAL_TEST required) -- reset_projection() itself has no
    opinion on environment naming, so tests/kiosk_v2_reset_projection_test.py
    can exercise the actual safety logic against whatever test database a
    CI run provides, without needing that database named "local_test".

Usage:
  DATABASE_URL=postgresql://... SERVER_ROLE=LOCAL_TEST \\
    python3 scripts/kiosk_v2_reset_projection.py KIOSK-LASER-01
  ... --force-close-zero --yes-i-am-sure   # only if you explicitly intend to close an open session
"""
import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


class OpenSessionRefused(RuntimeError):
    """Raised by reset_projection() when an OPEN Work Session blocks the reset
    and force_close_zero was not requested."""


def reset_projection(device_id: str, force_close_zero: bool = False) -> dict:
    """Core safety logic, no CLI/env concerns -- see module docstring.

    Returns a small result dict describing what happened. Raises
    OpenSessionRefused if an OPEN session blocks the reset and
    force_close_zero is False.
    """
    from mesflow.db.connection import fetch_one
    from mesflow.db.repositories.execution import WorkSessionRepository
    from mesflow.web.kiosk_v2 import _set_projection

    proj = fetch_one('SELECT * FROM kiosk_v2_projection WHERE device_id=%s', (device_id,))
    if proj is None:
        return {'action': 'noop', 'reason': 'no projection row'}

    closed_session_id = None
    session_id = proj.get('work_session_id')
    if session_id:
        session = fetch_one('SELECT id, status, employee_id, operation_id FROM work_sessions WHERE id=%s',
                            (session_id,))
        if session and session['status'] == 'OPEN':
            if not force_close_zero:
                raise OpenSessionRefused(
                    f"session {session_id} (employee_id={session['employee_id']} "
                    f"operation_id={session['operation_id']}) is OPEN")
            request_id = f'admin-reset:{device_id}:{uuid.uuid4()}'
            result = WorkSessionRepository().finish(session_id, {
                'request_id': request_id, 'good_qty': 0, 'defect_qty': 0, 'rework_qty': 0,
                'note': 'kiosk_v2_reset_projection.py --force-close-zero (deliberate admin reset)',
            })
            closed_session_id = session_id
            assert result['session']['status'] == 'CLOSED'

    new_proj = _set_projection(
        device_id, proj['state_version'], state_name='WAIT_EMPLOYEE',
        employee_id=None, employee_name='', operation_id=None, operation_code='', operation_name='',
        work_session_id=None, started_at=None, target_qty=0, produced_qty=0)
    return {'action': 'reset', 'closed_session_id': closed_session_id, 'state_version': new_proj['state_version']}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('device_id')
    parser.add_argument('--force-close-zero', action='store_true',
                        help='If an OPEN Work Session exists, close it via the REAL '
                             'WorkSessionRepository.finish() with GOOD=0/DEFECT=0/REWORK=0, '
                             'then reset the projection. Requires --yes-i-am-sure too.')
    parser.add_argument('--yes-i-am-sure', action='store_true',
                        help='Required alongside --force-close-zero -- a real Work Session '
                             'will be closed with zero quantities, which cannot be undone.')
    args = parser.parse_args()

    if os.environ.get('SERVER_ROLE') != 'LOCAL_TEST':
        print('REFUSED: SERVER_ROLE=LOCAL_TEST is not set in this shell. '
              'This script never runs against anything else -- set it explicitly '
              'to confirm you are pointed at the LOCAL_TEST database.', file=sys.stderr)
        sys.exit(1)

    db_url = os.environ.get('DATABASE_URL', '')
    if 'local_test' not in db_url and 'localtest' not in db_url.lower():
        print(f'REFUSED: DATABASE_URL does not look like LOCAL_TEST (got: '
              f'{db_url.split("@")[-1] if "@" in db_url else "<unset>"}). '
              'Refusing to guess -- pass the real LOCAL_TEST DATABASE_URL explicitly.',
              file=sys.stderr)
        sys.exit(1)

    if args.force_close_zero and not args.yes_i_am_sure:
        print('REFUSED: --force-close-zero requires --yes-i-am-sure too (this closes a '
              'real Work Session with zero quantities -- not reversible).', file=sys.stderr)
        sys.exit(1)

    try:
        result = reset_projection(args.device_id, force_close_zero=args.force_close_zero)
    except OpenSessionRefused as exc:
        print(f'OPEN Work Session found: {exc}', file=sys.stderr)
        print('REFUSED: refusing to reset the projection while a real Work Session is OPEN. '
              'Let the device finish it normally, or re-run with --force-close-zero '
              '--yes-i-am-sure to deliberately close it with zero quantities via the '
              'real business service.', file=sys.stderr)
        sys.exit(1)

    if result['action'] == 'noop':
        print(f"No projection row for device_id={args.device_id!r} -- nothing to reset.")
        return
    if result.get('closed_session_id'):
        print(f"Closed session {result['closed_session_id']} via real WorkSessionRepository.finish()")
    print(f"Projection reset: device_id={args.device_id} -> WAIT_EMPLOYEE "
          f"state_version={result['state_version']}")


if __name__ == '__main__':
    main()
