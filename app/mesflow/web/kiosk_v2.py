"""Real /api/kiosk/v2/* adapter for MESFlow Kiosk Runtime v2 firmware.

Architecture (per the firmware project's own explicit requirement): this is
a THIN adapter over the EXISTING authoritative business services --
KioskRepositoryLookup (real employee/operation lookup), WorkSessionRepository
(real, DB-backed, transactional Work Session start/finish -- the same one
mesflow.web.execution's /api/work-sessions/* and legacy_group_start/finish
already use). No business rule is duplicated here: PO-workable checks,
employee-active checks, dependency-chain checks, session-overlap checks all
happen inside WorkSessionRepository.start()/finish() exactly as they do for
every other caller.

    KIOSK V2 PROTOCOL (this file)
           |
    KioskRepositoryLookup / WorkSessionRepository  (existing, unchanged)
           |
    Postgres (employees/operations/production_orders/work_sessions)

What IS new here (kiosk_v2_* tables, migration 0039):
  - kiosk_v2_events: full-envelope idempotency, keyed by (device_id, event_id)
    -- independent of kiosk_idempotency (which only covers the START/FINISH
    mutations, keyed by request_id). A SCAN that doesn't reach start/finish
    (e.g. employee lookup) still needs its own replay-safe behavior.
  - kiosk_v2_projection: one row per device -- the WAIT_EMPLOYEE/
    WAIT_OPERATION/SESSION_ACTIVE/QUANTITY_INPUT/DEVICE_DISABLED/MAINTENANCE
    state machine + monotonic state_version + the view-model fields the
    firmware's StateProjection parses. This is the ONLY place kiosk v2
    "business" state lives -- it stores no quantities/session financials of
    its own, only pointers (employee_id/operation_id/work_session_id) into
    the real tables.
  - kiosk_v2_ui_bundles / kiosk_v2_ui_desired: backend-managed UI bundle
    registry (Phase 4) -- download-on-change, matches the firmware's
    ui_bundle.cpp parser exactly (TEXT/RECT/LINE components only).

Wire envelope: see mesflow-kiosk-runtime-v2/docs/PROTOCOL.md -- this file
was built directly against that document plus a byte-for-byte comparison
against tools/mock_backend/mock_backend.py (the reference implementation
the firmware was originally proven against), not guessed independently.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from mesflow import __version__
from mesflow.core.config import settings
from mesflow.db.connection import transaction, fetch_one, fetch_all
from mesflow.db.repositories.base import NotFoundError, ConflictError, RepositoryError
from mesflow.db.repositories.execution import WorkSessionRepository, KioskRepository, _json_safe
from mesflow.db.repositories.analytics import KioskEventRepository
from mesflow.domain.errors import PermissionDeniedError
from mesflow.web.execution import _legacy_kiosk_identity, KioskRepositoryLookup

bp = Blueprint('kiosk_v2', __name__, url_prefix='/api/kiosk/v2')

_sessions = WorkSessionRepository()

# EVENT type vocabulary (docs/PROTOCOL.md "event{} -- identity/ordering"):
# SCAN's raw QR payload is parsed HERE, server-side, never by the device
# (invariant: "§17" in the firmware's own mock reference).
_STATE_WAIT_EMPLOYEE = 'WAIT_EMPLOYEE'
_STATE_WAIT_OPERATION = 'WAIT_OPERATION'
_STATE_SESSION_ACTIVE = 'SESSION_ACTIVE'
_STATE_QUANTITY_INPUT = 'QUANTITY_INPUT'

# Latency diagnosis (2026-08-24 task): per-request backend timing is only
# ever exposed to the caller in local_test -- production protocol/behavior
# must never depend on this, it's pure observability. Gated on this specific
# env var (the one this LOCAL_TEST container already runs with) rather than
# app.debug, which reflects Flask config, not "am I the isolated diagnostic
# environment" -- the two happen to differ in other deployments.
_TIMING_ENABLED = os.environ.get('MESFLOW_ENV') == 'local_test'


class _Timer:
    """Tiny perf_counter checkpoint recorder -- time.perf_counter() per
    Part A §1 of the task ("Backend internal durations: use
    time.monotonic/perf_counter"), never wall-clock. A no-op-cost wrapper:
    when _TIMING_ENABLED is False the caller still constructs one (cheap:
    a dict + a few float subtractions) but nothing reads .marks afterward."""
    __slots__ = ('marks', '_last')

    def __init__(self):
        self.marks: dict[str, float] = {}
        self._last = time.perf_counter()

    def lap(self, label: str):
        now = time.perf_counter()
        self.marks[label] = round((now - self._last) * 1000, 3)
        self._last = now

    def total_since(self, start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 3)


def _json_response(data, status=200):
    """A REAL bug found live testing against real employee data (2026-08,
    fixed 2026-08-24): the firmware's hand-rolled JSON parser
    (json_extract.cpp, deliberately not a full JSON library) does not
    decode \\uXXXX escape sequences, and Flask's jsonify() escapes
    non-ASCII by default -- "Le Van Ly" with real diacritics ("Lê Văn Lý")
    arrived at the device as the literal text "Lu00ea Vu0103n Lu00fd" on
    screen. This project's OLD fix transliterated employee_name/
    operation_name to plain ASCII at this adapter boundary (see git
    history), which sidestepped the escaping bug but hid a SECOND, more
    fundamental gap: the renderer had no Vietnamese diacritic glyphs at
    all. kiosk_runtime_v2 0.6.0 added a real Vietnamese-capable glyph font
    (a UTF-8 decoder + bitmap glyph table, see that project's
    src/protocol/vn_font_core.h) -- json_extract.cpp already passes raw
    UTF-8 bytes through byte-for-byte unchanged (verified: it only special-
    cases '\\\\' and '"', both ASCII, so any byte >=0x80 is copied as-is).
    That means the ONLY remaining piece was this response's own encoding:
    serializing with ensure_ascii=False sends real UTF-8 bytes over the
    wire instead of \\uXXXX escapes, which the firmware can now decode and
    render correctly. Real names now keep their correct diacritics all the
    way to the physical screen, not just the database/dashboard/audit
    trail.

    Deliberately NOT a global `app.json.ensure_ascii = False` change -- that
    would affect every other blueprint sharing this Flask app; scoped here
    to just the kiosk_v2 responses that can carry these fields. (Excludes
    _bundle_json_bytes()/ui_bundle(), which must keep using jsonify() as
    the single source of truth its own hash is computed from -- see that
    function's docstring.)
    """
    resp = current_app.response_class(json.dumps(data, ensure_ascii=False, default=str),
                                      mimetype='application/json')
    resp.status_code = status
    return resp


def _now_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _parse_scan(raw: str):
    """"WF|EMP|<key>" / "WF|OP|<key>" -- same wire shape the real legacy
    /api/lookup endpoint (mesflow.web.execution.legacy_lookup) already
    parses; kept as a tiny local helper rather than importing that route
    function directly, since it also does HTTP-response-shaping we don't
    want here."""
    parts = str(raw or '').split('|')
    if len(parts) >= 3 and parts[0].upper() == 'WF':
        return parts[1].upper(), '|'.join(parts[2:])
    return None, None


def _device_id_from(body: dict) -> str:
    device = body.get('device') or {}
    return str(device.get('device_id') or device.get('hardware_id') or '').strip() or 'unknown'


def _get_projection(device_id: str) -> dict:
    row = fetch_one('SELECT * FROM kiosk_v2_projection WHERE device_id=%s', (device_id,))
    if row is None:
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO kiosk_v2_projection(device_id) VALUES (%s) ON CONFLICT (device_id) DO NOTHING',
                    (device_id,))
        row = fetch_one('SELECT * FROM kiosk_v2_projection WHERE device_id=%s', (device_id,))
    return dict(row)


def _build_view(proj: dict) -> dict:
    view = {}
    if proj.get('employee_name'):
        view['employee_name'] = proj['employee_name']
    if proj.get('operation_code'):
        view['operation_code'] = proj['operation_code']
        view['operation_name'] = proj['operation_name']
    if proj.get('work_session_id'):
        view['session_id'] = f"S-{proj['work_session_id']}"
        started = proj.get('started_at')
        view['started_at'] = started.strftime('%Y-%m-%dT%H:%M:%SZ') if started else None
        view['target_qty'] = int(proj.get('target_qty') or 0)
        view['produced_qty'] = int(proj.get('produced_qty') or 0)
    return view


def _snapshot(proj: dict) -> dict:
    name = proj['state_name']
    if proj.get('disabled'):
        name = 'DEVICE_DISABLED'
    elif proj.get('maintenance'):
        name = 'MAINTENANCE'
    return {
        'state': {'name': name, 'version': int(proj['state_version'])},
        'workflow': {'version': int(proj['workflow_version'])},
        'view': _build_view(proj),
    }


def _set_projection(device_id: str, expected_version: int, **fields) -> dict:
    """Bumps state_version by 1 and writes `fields`, guarded by an
    optimistic check against the version we read moments earlier -- a
    lightweight, kiosk_v2-local concurrency guard (a single physical kiosk
    rarely races itself, but two retries of the same stuck request
    shouldn't both apply). Returns the freshly-read row."""
    cols = ', '.join(f'{k}=%s' for k in fields)
    params = list(fields.values()) + [device_id, expected_version]
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE kiosk_v2_projection SET state_version=state_version+1, updated_at=CURRENT_TIMESTAMP"
                + (f", {cols}" if fields else "")
                + " WHERE device_id=%s AND state_version=%s RETURNING *",
                params,
            )
            row = cur.fetchone()
    if row is None:
        raise ConflictError('kiosk_v2 projection changed concurrently -- retry')
    return dict(row)


def _canonical_error(exc) -> tuple[str, str]:
    """Maps an exception to ONE of the canonical error codes docs/PROTOCOL.md
    and the firmware's error-classification (§9 of the online-scan
    regression task) expect -- never a generic catch-all for a business
    rejection."""
    if isinstance(exc, NotFoundError):
        msg = str(exc)
        if 'employee' in msg.lower():
            return 'EMPLOYEE_NOT_FOUND', 'Nhân viên không hợp lệ'
        if 'operation' in msg.lower():
            return 'OPERATION_NOT_FOUND', 'Công đoạn không hợp lệ'
        return 'NOT_FOUND', msg
    if isinstance(exc, ConflictError):
        msg = str(exc)
        if 'chưa Start' in msg or 'tạm dừng' in msg or 'sẵn sàng' in msg:
            return 'OPERATION_NOT_WORKABLE', msg
        if 'already has an open session' in msg or 'already been used' in msg:
            return 'EMPLOYEE_ALREADY_ACTIVE', msg
        if 'already closed' in msg:
            return 'SESSION_ALREADY_CLOSED', msg
        return 'BUSINESS_CONFLICT', msg
    if isinstance(exc, (ValueError, RepositoryError)):
        return 'INVALID_REQUEST', str(exc)
    return 'INTERNAL_ERROR', 'Không thể xử lý yêu cầu.'


def _apply_event(device_id: str, event_id: str, event_type: str, payload: dict, proj: dict,
                 timer: '_Timer | None' = None):
    """Returns (accepted: bool, error_code: str|None, error_message: str|None,
    new_proj: dict). Mutates real business data (WorkSessionRepository) only
    on the ACCEPT path -- a rejection never calls start()/finish().

    `timer`, when supplied (local_test only, see _TIMING_ENABLED), records
    employee_lookup_ms/operation_lookup_ms/session_repository_ms laps at the
    natural call boundaries below. db_commit_ms is NOT split out separately
    -- WorkSessionRepository.start()/finish() each own their own
    transaction() internally, so its cost is honestly folded into
    session_repository_ms rather than instrumenting a shared repository
    class (used by many other non-kiosk-v2 callers) just for this."""
    state = 'DEVICE_DISABLED' if proj.get('disabled') else 'MAINTENANCE' if proj.get('maintenance') else proj['state_name']
    if state in ('DEVICE_DISABLED', 'MAINTENANCE'):
        return False, 'DEVICE_NOT_ALLOWED', 'Thiết bị chưa được phép', proj

    request_id = f'{device_id}:{event_id}'

    if event_type == 'SCAN':
        kind, key = _parse_scan(payload.get('raw', ''))
        raw = payload.get('raw', '')

        # SHARED-TERMINAL FIX (2026-08-26): this file used to gate SCAN
        # entirely on `state` (WAIT_EMPLOYEE/WAIT_OPERATION/SESSION_ACTIVE),
        # which conflated two different things -- SERVER session state
        # (which employee has an OPEN work_session, tracked in
        # work_sessions, independent per employee) and KIOSK UI state (this
        # one device's current short-lived interaction, tracked in
        # kiosk_v2_projection, ONE ROW PER DEVICE). A successful OP scan
        # used to set state_name=SESSION_ACTIVE and LEAVE it there -- the
        # device stayed "occupied" by employee A's session for as long as
        # A's session stayed open (which is exactly the point of an open
        # session: it can legitimately stay open for hours). Any OTHER
        # employee scanning their own card during that window hit the
        # SESSION_ACTIVE branch below and got SESSION_EMPLOYEE_MISMATCH --
        # a shared kiosk was, in effect, single-employee-locked for the
        # duration of whoever started a session on it last.
        #
        # Fix: an EMP scan is now handled the SAME way regardless of the
        # kiosk's current state (the one exception is the "same employee
        # confirms finish" case just below, which legitimately depends on
        # what THIS device is currently showing). Every other case
        # re-resolves the JUST-SCANNED employee's own state from scratch --
        # do they have an OPEN session (server truth, queried fresh) or
        # not -- discarding whatever the kiosk was previously displaying.
        # Nothing destructive has happened in any of those prior states (no
        # session is created until a real OP scan succeeds), so nothing is
        # lost by discarding them; the kiosk belongs to the workstation, not
        # to whichever employee last touched it.
        if kind not in ('EMP', 'OP'):
            if state == _STATE_WAIT_EMPLOYEE:
                return False, 'STATE_INVALID_TRANSITION', 'Cần quét thẻ nhân viên', proj
            if state == _STATE_WAIT_OPERATION:
                return False, 'STATE_INVALID_TRANSITION', 'Cần quét mã công đoạn', proj
            return False, 'STATE_INVALID_TRANSITION', 'Không thể quét mã ở trạng thái này', proj

        if kind == 'EMP':
            emp = KioskRepositoryLookup.employee(raw, key)
            if timer: timer.lap('employee_lookup_ms')
            if emp is None:
                return False, 'EMPLOYEE_NOT_FOUND', 'Nhân viên không hợp lệ', proj

            # Canonical finish path (2026-08-24 diagnosis, preserved as-is):
            # scanning the SAME employee card again while the kiosk is
            # showing THAT employee's own freshly-resolved open session
            # confirms intent to finish. This is the one place an EMP scan's
            # outcome legitimately depends on current kiosk state -- every
            # other case below is a fresh, state-independent resolve.
            if (state == _STATE_SESSION_ACTIVE and proj.get('employee_id') == emp['id']
                    and proj.get('work_session_id')):
                session_row = fetch_one('SELECT status FROM work_sessions WHERE id=%s', (proj['work_session_id'],))
                if timer: timer.lap('active_session_lookup_ms')
                if session_row is None or str(session_row.get('status') or '').upper() != 'OPEN':
                    return False, 'SESSION_NOT_OPEN', 'Phiên đã kết thúc hoặc không tồn tại', proj
                new_proj = _set_projection(device_id, proj['state_version'], state_name=_STATE_QUANTITY_INPUT)
                KioskEventRepository().ingest({
                    'event_uuid': f'{device_id}-SCAN-EMP-FINISH-{uuid.uuid4()}', 'device_uuid': device_id,
                    'event_type': 'SCAN_EMPLOYEE_FINISH', 'severity': 'INFO',
                    'message': f"Quét lại thẻ {emp['employee_no']} để kết thúc (kiosk v2)",
                    'employee_id': emp['id'], 'session_id': proj['work_session_id'], 'payload': {'qr': raw}})
                return True, None, None, new_proj

            # Fresh resolve: does THIS employee (not whoever the kiosk was
            # previously showing) have their own OPEN session right now?
            #
            # Real field report (2026-08-27): this used to land on
            # SESSION_ACTIVE first (an info-only "here's your open session"
            # screen), requiring a SEPARATE second EMP rescan (the
            # "canonical finish path" special case above) to actually reach
            # QUANTITY_INPUT -- three total card taps to finish (open,
            # view, confirm). Explicit operator feedback: one card tap
            # should be enough once a session is already open -- there is
            # no real decision being made on the SESSION_ACTIVE screen that
            # justifies a mandatory extra tap, and the extra round trip was
            # confusing in practice ("scan, wait, see info, scan again").
            # Goes straight to QUANTITY_INPUT now; SESSION_ACTIVE is no
            # longer reachable via this path (the special case above is
            # dead code as a result, kept only because it's harmless if
            # SESSION_ACTIVE is ever reached some other way in the future).
            open_session = _find_open_session_for_employee(emp['id'])
            if timer: timer.lap('active_session_lookup_ms')
            if open_session:
                new_proj = _set_projection(
                    device_id, proj['state_version'], state_name=_STATE_QUANTITY_INPUT,
                    employee_id=emp['id'], employee_name=emp['name'],
                    operation_id=open_session['operation_id'], operation_code=open_session['operation_code'],
                    operation_name=open_session['operation_name'], work_session_id=open_session['work_session_id'],
                    started_at=open_session['started_at'], target_qty=int(open_session.get('target_qty') or 0),
                    produced_qty=0)
            else:
                new_proj = _set_projection(
                    device_id, proj['state_version'], state_name=_STATE_WAIT_OPERATION,
                    employee_id=emp['id'], employee_name=emp['name'], operation_id=None, operation_code='',
                    operation_name='', work_session_id=None, started_at=None, target_qty=0, produced_qty=0)
            KioskEventRepository().ingest({
                'event_uuid': f'{device_id}-SCAN-EMP-{uuid.uuid4()}', 'device_uuid': device_id,
                'event_type': 'SCAN_EMPLOYEE', 'severity': 'INFO',
                'message': f"Quét nhân viên {emp['employee_no']} (kiosk v2)",
                'employee_id': emp['id'], 'payload': {'qr': raw}})
            return True, None, None, new_proj

        # kind == 'OP': unlike EMP, this genuinely depends on the kiosk's
        # current short-lived interaction -- an operation code carries no
        # employee identity of its own, it only means anything in
        # combination with whichever employee the immediately-preceding EMP
        # scan selected. That 2-step (EMP then OP) interaction is expected
        # to complete within seconds; it is the one case where staying
        # kiosk-global for its brief duration is correct by the target
        # design, not a bug.
        if state != _STATE_WAIT_OPERATION:
            return False, 'STATE_INVALID_TRANSITION', 'Cần quét thẻ nhân viên trước', proj
        op = KioskRepositoryLookup.operation(raw, key)
        if timer: timer.lap('operation_lookup_ms')
        if op is None:
            return False, 'OPERATION_NOT_FOUND', 'Công đoạn không hợp lệ', proj
        if str(op.get('po_status') or '').upper() != 'IN_PROGRESS':
            return False, 'OPERATION_NOT_WORKABLE', f"PO {op.get('po_code') or ''} chưa Start hoặc đang tạm dừng", proj
        try:
            station_row = _resolve_station(payload)
            result = _sessions.start({
                'request_id': request_id, 'employee_id': proj['employee_id'], 'operation_id': op['id'],
                'station_id': station_row['id'] if station_row else None, 'device_uuid': device_id,
            })
        except (NotFoundError, ConflictError, ValueError, RepositoryError) as exc:
            if timer: timer.lap('session_repository_ms')
            code, msg = _canonical_error(exc)
            return False, code, msg, proj
        if timer: timer.lap('session_repository_ms')
        session = result['session']
        # SHARED-TERMINAL FIX: the session itself stays OPEN server-side --
        # that is the whole point, the server owns durable session state.
        # But the DEVICE's own short-lived interaction context must reset to
        # WAIT_EMPLOYEE immediately so the NEXT employee can use the kiosk
        # right away, instead of the old state_name=SESSION_ACTIVE here,
        # which held the kiosk hostage to this one employee until they
        # scanned again (see this function's own docstring/comment above for
        # the full root-cause writeup).
        new_proj = _set_projection(
            device_id, proj['state_version'], state_name=_STATE_WAIT_EMPLOYEE,
            employee_id=None, employee_name='', operation_id=None, operation_code='', operation_name='',
            work_session_id=None, started_at=None, target_qty=0, produced_qty=0)
        KioskEventRepository().ingest({
            'event_uuid': f'{device_id}-SCAN-OP-{uuid.uuid4()}', 'device_uuid': device_id,
            'event_type': 'SCAN_OPERATION', 'severity': 'INFO',
            'message': f"Quét OP {op['code']} (kiosk v2)",
            'operation_id': op['id'], 'session_id': session['id'], 'payload': {'qr': raw}})
        return True, None, None, new_proj

    if event_type == 'FINISH_REQUESTED':
        # Optional compatibility shortcut (kept per the task's own explicit
        # instruction: "retain as optional fallback ... Do not let QA use
        # '#' to accidentally hide a broken employee-rescan path" -- the
        # employee-rescan branch above is now the canonical path and is
        # exercised independently in physical E2E tests; this stays only
        # for debug-input/automation convenience).
        if state != _STATE_SESSION_ACTIVE:
            return False, 'STATE_INVALID_TRANSITION', 'Không có phiên đang hoạt động', proj
        new_proj = _set_projection(device_id, proj['state_version'], state_name=_STATE_QUANTITY_INPUT)
        return True, None, None, new_proj

    if event_type == 'QUANTITY_SUBMITTED':
        if state != _STATE_QUANTITY_INPUT:
            return False, 'STATE_INVALID_TRANSITION', 'Chưa yêu cầu kết thúc', proj
        quantity_good = payload.get('quantity_good')
        if quantity_good is None:
            return False, 'QUANTITY_INVALID', 'Thiếu số lượng', proj
        # GOOD/DEFECT/REWORK quantity flow (2026-08-24 task): firmware now
        # sends all three on the one final submit (docs/PROTOCOL.md). Absent
        # defect/rework (an OLDER firmware, or a debug-input caller that
        # only sends quantity_good) still defaults to 0 -- a real, honest
        # value, not a protocol error, so the older single-quantity flow
        # keeps working unchanged.
        quantity_defect = payload.get('quantity_defect', 0)
        quantity_rework = payload.get('quantity_rework', 0)
        try:
            good_i, defect_i, rework_i = int(quantity_good), int(quantity_defect), int(quantity_rework)
        except (TypeError, ValueError):
            return False, 'QUANTITY_INVALID', 'Số lượng không hợp lệ', proj
        # §15 of the task: backend independently re-validates, never trusts
        # the device's own local check alone -- these are the SAME rules
        # the firmware enforces before ever sending, checked again here.
        if good_i < 0 or defect_i < 0 or rework_i < 0:
            return False, 'QUANTITY_INVALID', 'Số lượng không được âm', proj
        if rework_i > defect_i:
            return False, 'REWORK_EXCEEDS_DEFECT', 'Số lượng sửa không được lớn hơn số lượng lỗi', proj
        try:
            result = _sessions.finish(proj['work_session_id'], {
                'request_id': request_id, 'good_qty': good_i, 'defect_qty': defect_i, 'rework_qty': rework_i,
                'note': 'kiosk v2',
            })
        except (NotFoundError, ConflictError, ValueError, RepositoryError) as exc:
            if timer: timer.lap('session_repository_ms')
            code, msg = _canonical_error(exc)
            return False, code, msg, proj
        if timer: timer.lap('session_repository_ms')
        session = result['session']
        KioskEventRepository().ingest({
            'event_uuid': f'{device_id}-FINISH-{uuid.uuid4()}', 'device_uuid': device_id,
            'event_type': 'QUANTITY_REPORTED', 'severity': 'INFO',
            'message': f"Nhập SL đạt {session.get('good_qty', 0)} lỗi {session.get('defect_qty', 0)} "
                       f"sửa {session.get('rework_qty', 0)} (kiosk v2)",
            'session_id': session['id'], 'operation_id': session.get('operation_id'),
            'payload': {'good_qty': good_i, 'defect_qty': defect_i, 'rework_qty': rework_i}})
        new_proj = _set_projection(
            device_id, proj['state_version'], state_name=_STATE_WAIT_EMPLOYEE,
            employee_id=None, employee_name='', operation_id=None, operation_code='', operation_name='',
            work_session_id=None, started_at=None, target_qty=0, produced_qty=0)
        return True, None, None, new_proj

    if event_type == 'CANCEL_REQUESTED':
        if state == _STATE_WAIT_EMPLOYEE:
            return False, 'STATE_INVALID_TRANSITION', 'Không có gì để hủy', proj
        if proj.get('work_session_id'):
            # A real open Work Session must not be silently abandoned --
            # CANCEL_REQUESTED isn't wired to any keypad key by the current
            # firmware (docs/PROTOCOL.md: "defined but not yet wired, Phase
            # 2 scope cut"), so this path is conservative rather than
            # guessed: refuse rather than invent a business meaning for
            # "cancel" on a real, already-open production session.
            return False, 'CANCEL_NOT_SUPPORTED', 'Hủy phiên đang mở chưa được hỗ trợ', proj
        new_proj = _set_projection(
            device_id, proj['state_version'], state_name=_STATE_WAIT_EMPLOYEE,
            employee_id=None, employee_name='', operation_id=None, operation_code='', operation_name='')
        return True, None, None, new_proj

    return False, 'PROTOCOL_DECODE_FAILED', f'unknown event type {event_type}', proj


def _bundle_json_bytes(version: int) -> bytes | None:
    """Serializes a stored bundle EXACTLY the way /ui-bundles/<version>
    actually sends it over the wire -- deliberately not a naive hash of
    Postgres's own jsonb-to-text stringification, which reorders/reformats
    keys differently and would silently drift from what the device actually
    downloads and hashes on its own end (a real, live gap found seeding
    this exact registry: a DB-side hash and the real served bytes hashed
    to two different values). Only ever called from within a Flask request
    (bootstrap/heartbeat/ui_bundle view functions), so an app/request
    context is always already active -- no extra context management needed.

    ensure_ascii=False (2026-08-25 font-audit fix): this used to go through
    plain jsonify(), which escapes non-ASCII to \\uXXXX -- fine for the
    ASCII-only bundles that existed when this was written, but a REAL bug
    for any bundle containing Vietnamese text (found live: a bundle with
    "QUÉT THẺ NHÂN VIÊN" arrived on-device as the literal text
    "QUu00c9T THu1eba..."). json_extract.cpp (the firmware's hand-rolled
    parser) only ever decoded raw UTF-8 bytes, never \\uXXXX escapes --
    exactly the same class of bug _json_response() above already fixed for
    /events /bootstrap /state, just not yet applied here. Kept as its own
    encode call (not routed through _json_response, which also sets
    mimetype/status) so the hash and the served bytes stay identically
    derived from this one function -- the "single source of truth" property
    the docstring above already required, now just with the right escaping."""
    row = fetch_one('SELECT content_json FROM kiosk_v2_ui_bundles WHERE version=%s', (version,))
    if row is None:
        return None
    return json.dumps(row['content_json'], ensure_ascii=False, sort_keys=True).encode('utf-8')


def _bundle_hash(version: int) -> str:
    data = _bundle_json_bytes(version)
    return hashlib.sha256(data).hexdigest() if data is not None else ''


def _resolve_station(payload: dict):
    code = str(payload.get('station_code') or request.headers.get('X-Station-ID') or '').strip()
    return KioskRepositoryLookup.station(code) if code else None


def _find_open_session_for_employee(employee_id: int):
    """Shared-terminal fix (2026-08-26): returns the employee's OWN currently
    OPEN work session, enriched with everything the kiosk_v2 projection
    needs to resume it (operation code/name, target quantity) -- or None.
    At most one row can ever match: DB-enforced by
    uq_open_session_per_employee, a partial UNIQUE index on
    work_sessions(employee_id) WHERE status='OPEN' (confirmed via \\d
    work_sessions -- the same "one employee = one active session" rule
    WorkSessionRepository.start() itself already relies on, see its own
    23505 -> ConflictError('employee already has an open session')
    handling). This function only ever surfaces that existing rule, never
    invents a second one. The WHERE clause here is exactly what that index
    covers, so this is a single indexed row lookup, not a table scan."""
    return fetch_one(
        """SELECT ws.id AS work_session_id, ws.operation_id, ws.started_at,
                  o.code AS operation_code, o.name AS operation_name,
                  po.planned_quantity AS target_qty
           FROM work_sessions ws
           JOIN operations o ON o.id = ws.operation_id
           LEFT JOIN production_orders po ON po.id = o.production_order_id
           WHERE ws.employee_id=%s AND ws.status='OPEN'
           LIMIT 1""",
        (employee_id,))


def _server_identity_fields() -> dict:
    """environment/server_role/version -- ESP kiosk UX-hardening pass
    (2026-08-26, §2 "Server Environment Visibility"): a real, confirmed gap
    found reading this whole file top to bottom -- none of /health,
    /bootstrap, /heartbeat, /state, /events had ever returned ANY of these,
    so a device had no way to know whether it was talking to DEV/TEST/PROD.
    Reads settings.environment/settings.server_role/__version__ exactly the
    way app.py's /api/system/ready (the browser/admin health endpoint --
    a different contract, same underlying values) already does -- no new
    logic invented here, just the same three fields on the kiosk-facing
    contract too. server_role is '' when unset (e.g. a bare local dev run
    with no SERVER_ROLE env var) -- returned as None, never a misleading
    empty string a device might render as a blank environment label."""
    return {
        'environment': settings.environment,
        'server_role': settings.server_role or None,
        'version': __version__,
    }


@bp.get('/health')
def health():
    return jsonify(ok=True, backend='postgresql', phase='kiosk_v2', **_server_identity_fields())


@bp.post('/bootstrap')
def bootstrap():
    body = request.get_json(silent=True) or {}
    device_id = str(body.get('device_id') or '').strip()
    hardware_id = str(body.get('hardware_id') or '').strip()
    # ESP kiosk physical field test (2026-08-26), §11 "401/403 test": real,
    # confirmed P1 security bug found live -- a bare `except Exception:
    # identity = None` here swallowed the PermissionDeniedError
    # _legacy_kiosk_identity() correctly raises for a DISABLED/SUSPENDED/
    # PENDING device (or an unregistered one when auto-bind is off), and
    # `identity=None` then evaluates as `not identity` in the device_status
    # ternary below -- reporting "ACTIVE" for a device an admin had
    # DELIBERATELY disabled via /kiosk-management. Verified live: setting a
    # real kiosk_identities row to SUSPENDED had zero effect on this
    # endpoint's response before this fix. Fixed by propagating the
    # intended rejection as a real 403 (FORBIDDEN), same status/shape every
    # other PermissionDeniedError caller in this codebase gets via
    # api_error_response -- routed through this file's own _json_response()
    # instead (see the except block below for why that distinction matters
    # here specifically). Only PermissionDeniedError is treated as a real
    # rejection here --
    # any other, genuinely-unexpected exception keeps the previous
    # permissive fallback (identity=None), since this endpoint's job is
    # bootstrap/config discovery, not the place to turn an unrelated bug
    # into a device-bricking failure.
    try:
        identity = _legacy_kiosk_identity({'device_uuid': device_id or hardware_id, 'device_id': device_id,
                                            'hardware_id': hardware_id})
    except PermissionDeniedError as exc:
        # Real regression caught live testing this exact fix on real
        # hardware (2026-08-26): api_error_response()/jsonify() escapes
        # non-ASCII to \uXXXX by default -- the Vietnamese rejection
        # message arrived on-device as literal "u0111ang u1edf
        # tru1ea1ng..." instead of "đang ở trạng...", the EXACT class of
        # bug _json_response() exists to prevent everywhere else in this
        # file (see its own docstring) -- this path just wasn't routed
        # through it yet. ok:false/error/message shape matches what
        # api_error_response would have produced, just correctly encoded.
        return _json_response({'ok': False, 'error': 'FORBIDDEN', 'message': str(exc)}, status=403)
    except Exception:
        identity = None

    desired_row = fetch_one('SELECT desired_version FROM kiosk_v2_ui_desired WHERE id=1') or {'desired_version': 0}
    desired_version = int(desired_row['desired_version'])
    ui_bundle_hash = _bundle_hash(desired_version) if desired_version else ''

    resp = {
        'accepted': True,
        'device_status': 'ACTIVE' if not identity or str(identity.get('status')) == 'ACTIVE' else str(identity.get('status')),
        'server_time': _now_iso(),
        'protocol': {'accepted_version': 1},
        'desired': {
            'config_version': 1, 'workflow_version': 1,
            'ui_bundle_version': desired_version,
            'ui_bundle_hash': ui_bundle_hash,
        },
        **_server_identity_fields(),
    }
    if device_id:
        proj = _get_projection(device_id)
        resp.update(_snapshot(proj))
    return _json_response(resp)


@bp.post('/heartbeat')
def heartbeat():
    # REAL BUG (found live, 2026-08-26): this endpoint only ever resolved/
    # validated the identity via _legacy_kiosk_identity() (a pure SELECT +
    # ACTIVE/PENDING/DISABLED check -- see its own docstring) and returned
    # accepted=True, but NEVER wrote to kiosk_status. system_health_service
    # .KioskProvider (and the Trạm kiosk / kiosk-management dashboard it
    # backs) computes ONLINE/DEGRADED/OFFLINE entirely from
    # kiosk_status.last_heartbeat_at. Result: a genuinely healthy, actively
    # heartbeating v2 kiosk could never show as ONLINE -- the server was
    # accepting every heartbeat (200 accepted:true) while silently never
    # recording that it happened, for the entire lifetime of the v2
    # protocol. /station/heartbeat (the legacy v1 endpoint) already does
    # this correctly via KioskRepository().heartbeat(); v2 just never
    # called it. Fixed by doing the same here.
    # §11 of the 2026-08-26 ESP kiosk physical field test: same class of
    # bug as bootstrap()'s own fix just above -- a bare `except Exception:
    # pass` here also swallowed PermissionDeniedError for a DISABLED/
    # SUSPENDED/PENDING device, then still fell through to
    # `return jsonify(accepted=True)` unconditionally. A device an admin
    # disabled kept getting accepted=True heartbeats forever. Fixed the
    # same way: PermissionDeniedError now short-circuits with a real 403
    # before ever reaching KioskRepository().heartbeat(); any other,
    # genuinely-unexpected exception keeps the previous tolerant behavior
    # (this is best-effort telemetry, not where an unrelated bug should
    # turn into a failed heartbeat).
    body = request.get_json(silent=True) or {}
    device_id = str(body.get('device_id') or '').strip()
    if device_id:
        try:
            _legacy_kiosk_identity({'device_uuid': device_id})
            KioskRepository().heartbeat(device_id, {
                'ui_state': body.get('ui_state') or 'UNKNOWN',
                'health_state': 'ERROR' if body.get('last_error') else 'OK',
                'queue_size': body.get('queue_size') or body.get('pending_events') or 0,
                'wifi_rssi': body.get('wifi_rssi'),
                'free_heap': body.get('free_heap'),
                'last_error': body.get('last_error') or '',
                'firmware_version': body.get('firmware_version') or body.get('app_version') or '',
                'firmware_build': body.get('firmware_build') or '',
                'hardware_model': body.get('hardware_model') or '',
                'ota_capable': bool(body.get('ota_capable', False)),
                'boot_id': body.get('boot_id') or '',
                'uptime_seconds': body.get('uptime_seconds') or 0,
                'boot_reason': body.get('boot_reason') or '',
            })
        except PermissionDeniedError as exc:
            # Same \uXXXX-escaping regression/fix as bootstrap()'s own
            # PermissionDeniedError branch above -- see its comment.
            return _json_response({'ok': False, 'error': 'FORBIDDEN', 'message': str(exc)}, status=403)
        except Exception:
            pass
    return jsonify(accepted=True)


@bp.get('/state')
def state():
    device_id = str(request.args.get('device_id') or '').strip()
    if not device_id:
        return jsonify(error={'code': 'PROTOCOL_DECODE_FAILED'}), 400
    proj = _get_projection(device_id)
    resp = {'device_id': device_id}
    resp.update(_snapshot(proj))
    return _json_response(resp)


@bp.post('/events')
def events():
    req_start = time.perf_counter()
    timer = _Timer() if _TIMING_ENABLED else None

    body = request.get_json(silent=True) or {}
    if body.get('protocol_version') != 1:
        return jsonify(accepted=False, error={'code': 'PROTOCOL_UNSUPPORTED_VERSION'}), 400

    device_id = _device_id_from(body)
    event = body.get('event') or {}
    context = body.get('context') or {}
    payload = body.get('payload') or {}
    event_id = str(event.get('event_id') or '')
    event_type = str(event.get('type') or '')
    expected_version = context.get('expected_state_version')
    if not event_id:
        return jsonify(accepted=False, error={'code': 'PROTOCOL_DECODE_FAILED'}), 400

    payload_hash = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    if timer: timer.lap('request_parse_ms')

    cached = fetch_one('SELECT payload_hash, response_json FROM kiosk_v2_events WHERE device_id=%s AND event_id=%s',
                       (device_id, event_id))
    if timer: timer.lap('idempotency_lookup_ms')
    if cached is not None:
        if cached['payload_hash'] == payload_hash:
            return _json_response(cached['response_json'])
        return jsonify(accepted=False, event_id=event_id, error={'code': 'IDEMPOTENCY_KEY_REUSE_MISMATCH'}), 409

    proj = _get_projection(device_id)
    if timer: timer.lap('device_lookup_ms')

    if expected_version is not None and int(expected_version) < int(proj['state_version']):
        resp = {
            'accepted': False, 'event_id': event_id, 'error': {'code': 'STATE_CONFLICT'},
            'action': 'RESYNC', 'current_state_version': int(proj['state_version']),
        }
        _store_event(device_id, event_id, payload_hash, event.get('device_seq') or 0, resp)
        return _json_response(resp)

    accepted, error_code, error_message, new_proj = _apply_event(device_id, event_id, event_type, payload, proj,
                                                                  timer=timer)
    if timer: timer.lap('business_validation_ms')  # residual: state-machine branching not already lapped above

    resp = {'accepted': accepted, 'event_id': event_id}
    resp.update(_snapshot(new_proj))
    if not accepted:
        resp['error'] = {'code': error_code, 'message': error_message}
    if timer: timer.lap('response_build_ms')

    _store_event(device_id, event_id, payload_hash, event.get('device_seq') or 0, resp)
    if timer: timer.lap('db_commit_ms')  # the kiosk_v2_events INSERT itself

    if timer:
        total_ms = timer.total_since(req_start)
        resp['timing'] = {**timer.marks, 'total_backend_ms': total_ms}
        response = _json_response(resp)
        server_timing = ','.join(f'{k.replace("_ms", "")};dur={v}' for k, v in timer.marks.items())
        response.headers['Server-Timing'] = f'{server_timing},total;dur={total_ms}'
        return response

    return _json_response(resp)


def _store_event(device_id, event_id, payload_hash, device_seq, resp):
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO kiosk_v2_events(device_id, event_id, payload_hash, device_seq, response_json) '
                'VALUES (%s,%s,%s,%s,%s) ON CONFLICT (device_id, event_id) DO NOTHING',
                (device_id, event_id, payload_hash, int(device_seq or 0), json.dumps(_json_safe(resp))))


@bp.get('/ui-bundles/<int:version>')
def ui_bundle(version: int):
    data = _bundle_json_bytes(version)
    if data is None:
        return jsonify(error={'code': 'UI_BUNDLE_NOT_FOUND'}), 404
    return data, 200, {'Content-Type': 'application/json'}
