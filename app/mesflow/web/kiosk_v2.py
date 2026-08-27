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
import unicodedata
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from mesflow.db.connection import transaction, fetch_one, fetch_all
from mesflow.db.repositories.base import NotFoundError, ConflictError, RepositoryError
from mesflow.db.repositories.execution import WorkSessionRepository, _json_safe
from mesflow.db.repositories.analytics import KioskEventRepository
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


_VN_EXTRA = {'đ': 'd', 'Đ': 'D'}


def _ascii_safe(text) -> str:
    """A REAL bug found live testing against real employee data: the
    firmware's hand-rolled JSON parser (json_extract.cpp, deliberately not
    a full JSON library) does not decode \\uXXXX escape sequences, and
    Flask's jsonify() escapes non-ASCII by default -- "Le Van Ly" with real
    diacritics ("Lê Văn Lý") arrived at the device as the literal text
    "Lu00ea Vu0103n Lu00fd" on screen. Even fixing the escaping wouldn't be
    enough on its own: the renderer's font has no Vietnamese diacritic
    glyphs at all (established earlier in this project -- every hardcoded/
    bundle string is already plain ASCII). So this transliterates at the
    adapter boundary, presentation-layer only -- the real name keeps its
    correct diacritics in the database/dashboard/audit trail; only what
    THIS kiosk's view{} sends out gets the ASCII-safe rendition. 'đ'/'Đ'
    need explicit handling since they aren't decomposable via NFD like the
    other diacritics are.
    """
    if not text:
        return text
    for src, dst in _VN_EXTRA.items():
        text = text.replace(src, dst)
    normalized = unicodedata.normalize('NFD', text)
    return ''.join(c for c in normalized if not unicodedata.combining(c))


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
            return 'EMPLOYEE_NOT_FOUND', 'Nhan vien khong hop le'
        if 'operation' in msg.lower():
            return 'OPERATION_NOT_FOUND', 'Cong doan khong hop le'
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
    return 'INTERNAL_ERROR', 'Unable to process the request.'


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
        return False, 'DEVICE_NOT_ALLOWED', 'Thiet bi chua duoc phep', proj

    request_id = f'{device_id}:{event_id}'

    if event_type == 'SCAN':
        kind, key = _parse_scan(payload.get('raw', ''))
        raw = payload.get('raw', '')

        if state == _STATE_WAIT_EMPLOYEE:
            if kind != 'EMP':
                return False, 'STATE_INVALID_TRANSITION', 'Can quet the nhan vien', proj
            emp = KioskRepositoryLookup.employee(raw, key)
            if timer: timer.lap('employee_lookup_ms')
            if emp is None:
                return False, 'EMPLOYEE_NOT_FOUND', 'Nhan vien khong hop le', proj
            new_proj = _set_projection(
                device_id, proj['state_version'],
                state_name=_STATE_WAIT_OPERATION, employee_id=emp['id'], employee_name=_ascii_safe(emp['name']),
                operation_id=None, operation_code='', operation_name='', work_session_id=None,
                started_at=None, target_qty=0, produced_qty=0)
            KioskEventRepository().ingest({
                'event_uuid': f'{device_id}-SCAN-EMP-{uuid.uuid4()}', 'device_uuid': device_id,
                'event_type': 'SCAN_EMPLOYEE', 'severity': 'INFO',
                'message': f"Quet nhan vien {emp['employee_no']} (kiosk v2)",
                'employee_id': emp['id'], 'payload': {'qr': raw}})
            return True, None, None, new_proj

        if state == _STATE_WAIT_OPERATION:
            if kind != 'OP':
                return False, 'STATE_INVALID_TRANSITION', 'Can quet ma cong doan', proj
            op = KioskRepositoryLookup.operation(raw, key)
            if timer: timer.lap('operation_lookup_ms')
            if op is None:
                return False, 'OPERATION_NOT_FOUND', 'Cong doan khong hop le', proj
            if str(op.get('po_status') or '').upper() != 'IN_PROGRESS':
                return False, 'OPERATION_NOT_WORKABLE', f"PO {op.get('po_code') or ''} chua Start hoac dang tam dung", proj
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
            po_row = fetch_one('SELECT planned_quantity FROM production_orders WHERE id='
                               '(SELECT production_order_id FROM operations WHERE id=%s)', (op['id'],))
            target_qty = int((po_row or {}).get('planned_quantity') or 0)
            new_proj = _set_projection(
                device_id, proj['state_version'],
                state_name=_STATE_SESSION_ACTIVE, operation_id=op['id'], operation_code=op['code'],
                operation_name=_ascii_safe(op['name']), work_session_id=session['id'], started_at=session['started_at'],
                target_qty=target_qty, produced_qty=0)
            KioskEventRepository().ingest({
                'event_uuid': f'{device_id}-SCAN-OP-{uuid.uuid4()}', 'device_uuid': device_id,
                'event_type': 'SCAN_OPERATION', 'severity': 'INFO',
                'message': f"Quet OP {op['code']} (kiosk v2)",
                'operation_id': op['id'], 'session_id': session['id'], 'payload': {'qr': raw}})
            return True, None, None, new_proj

        if state == _STATE_SESSION_ACTIVE:
            # Real product contract (2026-08-24 diagnosis): the canonical
            # MESFlow operator flow finishes a session by scanning the SAME
            # employee card again, not by pressing a keypad key. '#' /
            # FINISH_REQUESTED stays below as an explicit optional
            # compatibility shortcut, but it must never be the ONLY way
            # this transition works -- it previously was, because this
            # branch didn't exist and any SCAN here fell through to the
            # generic STATE_INVALID_TRANSITION reject at the bottom.
            if kind != 'EMP':
                return False, 'STATE_INVALID_TRANSITION', 'Can quet lai the nhan vien de ket thuc', proj
            emp = KioskRepositoryLookup.employee(raw, key)
            if timer: timer.lap('employee_lookup_ms')
            if emp is None:
                return False, 'EMPLOYEE_NOT_FOUND', 'Nhan vien khong hop le', proj
            if emp['id'] != proj.get('employee_id'):
                # Must never collapse into a generic/network-looking error --
                # this is a real, distinct business rejection (§10/§16 of
                # the diagnosis task).
                return False, 'SESSION_EMPLOYEE_MISMATCH', 'Khong dung nhan vien dang lam', proj
            if not proj.get('work_session_id'):
                return False, 'SESSION_NOT_OPEN', 'Khong co phien dang hoat dong', proj
            session_row = fetch_one('SELECT status FROM work_sessions WHERE id=%s', (proj['work_session_id'],))
            if timer: timer.lap('session_repository_ms')
            if session_row is None or str(session_row.get('status') or '').upper() != 'OPEN':
                return False, 'SESSION_NOT_OPEN', 'Phien da ket thuc hoac khong ton tai', proj
            new_proj = _set_projection(device_id, proj['state_version'], state_name=_STATE_QUANTITY_INPUT)
            KioskEventRepository().ingest({
                'event_uuid': f'{device_id}-SCAN-EMP-FINISH-{uuid.uuid4()}', 'device_uuid': device_id,
                'event_type': 'SCAN_EMPLOYEE_FINISH', 'severity': 'INFO',
                'message': f"Quet lai the {emp['employee_no']} de ket thuc (kiosk v2)",
                'employee_id': emp['id'], 'session_id': proj['work_session_id'], 'payload': {'qr': raw}})
            return True, None, None, new_proj

        return False, 'STATE_INVALID_TRANSITION', 'Khong the quet ma o trang thai nay', proj

    if event_type == 'FINISH_REQUESTED':
        # Optional compatibility shortcut (kept per the task's own explicit
        # instruction: "retain as optional fallback ... Do not let QA use
        # '#' to accidentally hide a broken employee-rescan path" -- the
        # employee-rescan branch above is now the canonical path and is
        # exercised independently in physical E2E tests; this stays only
        # for debug-input/automation convenience).
        if state != _STATE_SESSION_ACTIVE:
            return False, 'STATE_INVALID_TRANSITION', 'Khong co phien dang hoat dong', proj
        new_proj = _set_projection(device_id, proj['state_version'], state_name=_STATE_QUANTITY_INPUT)
        return True, None, None, new_proj

    if event_type == 'QUANTITY_SUBMITTED':
        if state != _STATE_QUANTITY_INPUT:
            return False, 'STATE_INVALID_TRANSITION', 'Chua yeu cau ket thuc', proj
        quantity_good = payload.get('quantity_good')
        if quantity_good is None:
            return False, 'QUANTITY_INVALID', 'Thieu so luong', proj
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
            return False, 'QUANTITY_INVALID', 'So luong khong hop le', proj
        # §15 of the task: backend independently re-validates, never trusts
        # the device's own local check alone -- these are the SAME rules
        # the firmware enforces before ever sending, checked again here.
        if good_i < 0 or defect_i < 0 or rework_i < 0:
            return False, 'QUANTITY_INVALID', 'So luong khong duoc am', proj
        if rework_i > defect_i:
            return False, 'REWORK_EXCEEDS_DEFECT', 'So luong sua khong duoc lon hon so luong loi', proj
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
            'message': f"Nhap SL dat {session.get('good_qty', 0)} loi {session.get('defect_qty', 0)} "
                       f"sua {session.get('rework_qty', 0)} (kiosk v2)",
            'session_id': session['id'], 'operation_id': session.get('operation_id'),
            'payload': {'good_qty': good_i, 'defect_qty': defect_i, 'rework_qty': rework_i}})
        new_proj = _set_projection(
            device_id, proj['state_version'], state_name=_STATE_WAIT_EMPLOYEE,
            employee_id=None, employee_name='', operation_id=None, operation_code='', operation_name='',
            work_session_id=None, started_at=None, target_qty=0, produced_qty=0)
        return True, None, None, new_proj

    if event_type == 'CANCEL_REQUESTED':
        if state == _STATE_WAIT_EMPLOYEE:
            return False, 'STATE_INVALID_TRANSITION', 'Khong co gi de huy', proj
        if proj.get('work_session_id'):
            # A real open Work Session must not be silently abandoned --
            # CANCEL_REQUESTED isn't wired to any keypad key by the current
            # firmware (docs/PROTOCOL.md: "defined but not yet wired, Phase
            # 2 scope cut"), so this path is conservative rather than
            # guessed: refuse rather than invent a business meaning for
            # "cancel" on a real, already-open production session.
            return False, 'CANCEL_NOT_SUPPORTED', 'Huy phien dang mo chua duoc ho tro', proj
        new_proj = _set_projection(
            device_id, proj['state_version'], state_name=_STATE_WAIT_EMPLOYEE,
            employee_id=None, employee_name='', operation_id=None, operation_code='', operation_name='')
        return True, None, None, new_proj

    return False, 'PROTOCOL_DECODE_FAILED', f'unknown event type {event_type}', proj


def _bundle_json_bytes(version: int) -> bytes | None:
    """Serializes a stored bundle EXACTLY the way /ui-bundles/<version>
    actually sends it over the wire (Flask's own json.dumps, via
    jsonify().get_data()) -- deliberately not a naive hash of Postgres's
    own jsonb-to-text stringification, which reorders/reformats keys
    differently and would silently drift from what the device actually
    downloads and hashes on its own end (a real, live gap found seeding
    this exact registry: a DB-side hash and the real served bytes hashed
    to two different values). Only ever called from within a Flask request
    (bootstrap/heartbeat/ui_bundle view functions), so an app/request
    context is always already active -- no extra context management needed."""
    row = fetch_one('SELECT content_json FROM kiosk_v2_ui_bundles WHERE version=%s', (version,))
    if row is None:
        return None
    return jsonify(row['content_json']).get_data()


def _bundle_hash(version: int) -> str:
    data = _bundle_json_bytes(version)
    return hashlib.sha256(data).hexdigest() if data is not None else ''


def _resolve_station(payload: dict):
    code = str(payload.get('station_code') or request.headers.get('X-Station-ID') or '').strip()
    return KioskRepositoryLookup.station(code) if code else None


@bp.get('/health')
def health():
    return jsonify(ok=True, backend='postgresql', phase='kiosk_v2')


@bp.post('/bootstrap')
def bootstrap():
    body = request.get_json(silent=True) or {}
    device_id = str(body.get('device_id') or '').strip()
    hardware_id = str(body.get('hardware_id') or '').strip()
    try:
        identity = _legacy_kiosk_identity({'device_uuid': device_id or hardware_id, 'device_id': device_id,
                                            'hardware_id': hardware_id})
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
    }
    if device_id:
        proj = _get_projection(device_id)
        resp.update(_snapshot(proj))
    return jsonify(resp)


@bp.post('/heartbeat')
def heartbeat():
    body = request.get_json(silent=True) or {}
    device_id = str(body.get('device_id') or '').strip()
    if device_id:
        try:
            _legacy_kiosk_identity({'device_uuid': device_id})
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
    return jsonify(resp)


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
            return jsonify(cached['response_json'])
        return jsonify(accepted=False, event_id=event_id, error={'code': 'IDEMPOTENCY_KEY_REUSE_MISMATCH'}), 409

    proj = _get_projection(device_id)
    if timer: timer.lap('device_lookup_ms')

    if expected_version is not None and int(expected_version) < int(proj['state_version']):
        resp = {
            'accepted': False, 'event_id': event_id, 'error': {'code': 'STATE_CONFLICT'},
            'action': 'RESYNC', 'current_state_version': int(proj['state_version']),
        }
        _store_event(device_id, event_id, payload_hash, event.get('device_seq') or 0, resp)
        return jsonify(resp)

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
        response = jsonify(resp)
        server_timing = ','.join(f'{k.replace("_ms", "")};dur={v}' for k, v in timer.marks.items())
        response.headers['Server-Timing'] = f'{server_timing},total;dur={total_ms}'
        return response

    return jsonify(resp)


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
