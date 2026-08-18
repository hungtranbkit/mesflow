from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

from mesflow.db.connection import fetch_all, fetch_one, transaction
from mesflow.db.repositories.base import ConflictError, NotFoundError, RepositoryError
from mesflow.db.repositories.execution import WorkSessionRepository
from mesflow.services.kiosk_reconciliation import ReconciliationResult, compute_missing, ranges


BUSINESS_ERRORS = (ValueError, ConflictError, NotFoundError, RepositoryError)


def _canonical_hash(event: dict[str, Any]) -> str:
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _event_time(value: Any, quality: str, epoch: Any = None):
    if quality != 'synced':
        return None
    if not value and epoch:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None


class OfflineSyncRepository:
    """Process durable kiosk events using production API idempotency keys.

    WorkSessionRepository owns the production transaction. Its advisory-lock +
    kiosk_idempotency row makes a lost HTTP response safe: replaying the exact
    client_event_id cannot create or finish a session twice. This ledger adds
    payload identity, kiosk ordering and offline audit metadata.
    """

    def snapshot(self, kiosk_id: str, station_code: str = '') -> dict[str, Any]:
        from mesflow.db.connection import fetch_all
        employees = fetch_all("""SELECT employee_no,employee_no code,name,qr,active
            FROM employees WHERE active=TRUE ORDER BY employee_no""")
        operations = fetch_all("""SELECT o.code,o.name,o.qr,po.code po,p.code part,
                   %s::text station_code,o.status,po.status po_status
            FROM operations o
            JOIN production_orders po ON po.id=o.production_order_id
            LEFT JOIN parts p ON p.id=o.part_id
            WHERE po.status='IN_PROGRESS' AND o.status NOT IN ('COMPLETED','CANCELLED')
            ORDER BY po.code,o.code""", (station_code,))
        revision_source = json.dumps({'e': employees, 'o': operations}, default=str, sort_keys=True, separators=(',', ':'))
        revision = hashlib.sha256(revision_source.encode()).hexdigest()[:20]
        return {
            'schema_version': 1,
            'generated_at': datetime.now().astimezone().isoformat(),
            'revision': revision,
            'kiosk_id': kiosk_id,
            'employees': employees,
            'workers': employees,
            'operations': operations,
        }

    def _existing(self, event_id: str):
        return fetch_one('SELECT * FROM kiosk_client_events WHERE client_event_id=%s', (event_id,))

    def _record(self, kiosk_id: str, event: dict[str, Any], payload_hash: str,
                status: str, result: dict[str, Any], session_id: int | None = None,
                reason_code: str = '', reason: str = '') -> None:
        quality = str(event.get('time_quality') or 'unknown').lower()
        if quality not in {'synced', 'estimated', 'unknown'}:
            quality = 'unknown'
        # 'sync_source' is set by the kiosk only when replaying a
        # previously-ACKed event during DR reconciliation (see
        # esp-kiosk/esp/mesflow_app.cpp's runGenerationReconciliation()); a
        # normal first-time sync omits it and keeps the column's own
        # 'OFFLINE_SYNC' default. This is how a reconciliation-triggered
        # conflict is told apart from an ordinary one for the Session
        # Exceptions KIOSK_SYNC_CONFLICT branch (see analytics.py) without a
        # dedicated column.
        source = 'RECONCILE_REPLAY' if str(event.get('sync_source') or '').lower() == 'reconcile_replay' else 'OFFLINE_SYNC'
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO kiosk_client_events(
                    client_event_id,payload_hash,kiosk_id,local_sequence,local_session_id,
                    session_trace_id,event_type,event_time,time_quality,device_uptime_ms,
                    boot_id,snapshot_revision,source,status,reason_code,reason,server_session_id,
                    payload_json,result_json,processed_at)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                  ON CONFLICT(client_event_id) DO NOTHING""", (
                    str(event['client_event_id']), payload_hash, kiosk_id,
                    int(event.get('local_sequence') or 0), str(event.get('local_session_id') or ''),
                    str(event.get('session_trace_id') or ''), str(event.get('event_type') or '').upper(),
                    _event_time(event.get('event_time'), quality, event.get('event_time_epoch')), quality,
                    int(event.get('device_uptime_ms') or 0), str(event.get('boot_id') or ''),
                    str(event.get('offline_snapshot_revision') or ''), source, status, reason_code, reason,
                    session_id, Jsonb(event), Jsonb(result)))
                cur.execute("""UPDATE kiosk_identities SET
                    last_sequence_received=GREATEST(last_sequence_received,%s)
                    WHERE device_uuid=%s""",
                    (int(event.get('local_sequence') or 0), kiosk_id))

    def process_event(self, kiosk_id: str, station_id: int | None, event: dict[str, Any]) -> dict[str, Any]:
        event_id = str(event.get('client_event_id') or event.get('event_id') or '').strip()
        if not event_id:
            return {'client_event_id': '', 'status': 'rejected', 'reason_code': 'CLIENT_EVENT_ID_REQUIRED'}
        event = dict(event)
        event['client_event_id'] = event_id
        payload_hash = _canonical_hash(event)
        existing = self._existing(event_id)
        if existing:
            if existing['payload_hash'] != payload_hash:
                return {'client_event_id': event_id, 'status': 'rejected', 'reason_code': 'IDEMPOTENCY_PAYLOAD_CONFLICT'}
            # A genuine replay (reboot-before-local-ACK, lost response retry,
            # or DR reconciliation resending an already-ACKed event -- see
            # audit failure case B/C/E). Not an error: this is the exact
            # protection kiosk_client_events' UNIQUE(client_event_id) exists
            # for. Tracked (not silently a no-op) so the admin view can show
            # a real duplicate count instead of the previous "invisible"
            # behavior -- audit section 11/4.
            with transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE kiosk_identities SET
                        duplicate_replay_count=duplicate_replay_count+1,
                        last_sequence_received=GREATEST(last_sequence_received,%s)
                        WHERE device_uuid=%s""",
                        (int(existing.get('local_sequence') or 0), kiosk_id))
            return {'client_event_id': event_id, 'status': 'duplicate', 'server_session_id': existing.get('server_session_id')}

        sequence = int(event.get('local_sequence') or event.get('device_sequence') or 0)
        if sequence <= 0:
            return {'client_event_id': event_id, 'status': 'rejected', 'reason_code': 'LOCAL_SEQUENCE_REQUIRED'}
        sequence_owner = fetch_one('SELECT client_event_id FROM kiosk_client_events WHERE kiosk_id=%s AND local_sequence=%s', (kiosk_id, sequence))
        if sequence_owner and sequence_owner['client_event_id'] != event_id:
            return {'client_event_id': event_id, 'status': 'rejected', 'reason_code': 'LOCAL_SEQUENCE_CONFLICT'}
        event['local_sequence'] = sequence
        kind = str(event.get('event_type') or '').upper()
        try:
            if kind == 'START':
                worker_qr = str(event.get('employee_qr') or event.get('worker_qr') or '')
                operation_qr = str(event.get('operation_qr') or '')
                employee = fetch_one("SELECT id FROM employees WHERE active=TRUE AND (upper(qr)=upper(%s) OR upper(employee_no)=upper(%s)) LIMIT 1", (worker_qr, worker_qr.split('|')[-1]))
                operation = fetch_one("SELECT id FROM operations WHERE upper(qr)=upper(%s) OR upper(code)=upper(%s) LIMIT 1", (operation_qr, operation_qr.split('|')[-1]))
                if not employee:
                    raise NotFoundError('employee missing or inactive')
                if not operation:
                    raise NotFoundError('operation missing')
                output = WorkSessionRepository().start({
                    'request_id': event_id, 'employee_id': employee['id'],
                    'operation_id': operation['id'], 'station_id': station_id,
                    'device_uuid': kiosk_id,
                })
                session_id = int(output['session']['id'])
            elif kind == 'FINISH':
                local_session_id = str(event.get('local_session_id') or '')
                if local_session_id.startswith('SERVER:'):
                    session_id = int(local_session_id.split(':', 1)[1])
                else:
                    start = fetch_one("""SELECT server_session_id FROM kiosk_client_events
                        WHERE kiosk_id=%s AND local_session_id=%s AND event_type='START'
                          AND status='accepted' ORDER BY local_sequence LIMIT 1""",
                        (kiosk_id, local_session_id))
                    if not start or not start.get('server_session_id'):
                        raise ConflictError('offline START chưa được đồng bộ')
                    session_id = int(start['server_session_id'])
                output = WorkSessionRepository().finish(session_id, {
                    'request_id': event_id,
                    'good_qty': event.get('good_qty', 0),
                    'defect_qty': event.get('defect_qty', 0),
                    'rework_qty': event.get('repairable_qty', event.get('rework_qty', 0)),
                    'note': 'OFFLINE SYNC',
                })
            else:
                raise ValueError('event_type must be START or FINISH')
        except BUSINESS_ERRORS as exc:
            result = {'client_event_id': event_id, 'status': 'rejected', 'reason_code': 'BUSINESS_REJECT', 'reason': str(exc)}
            self._record(kiosk_id, event, payload_hash, 'rejected', result,
                         reason_code='BUSINESS_REJECT', reason=str(exc))
            return result
        except Exception:
            # Unknown/database failures are transient. Do not create a terminal
            # ledger row; the ESP retains and retries the event with backoff.
            return {'client_event_id': event_id, 'status': 'transient', 'reason_code': 'TEMPORARY_FAILURE'}

        result = {'client_event_id': event_id, 'status': 'accepted', 'server_session_id': session_id}
        self._record(kiosk_id, event, payload_hash, 'accepted', result, session_id=session_id)
        return result

    def reconcile(self, kiosk_id: str, seq_min: int, seq_max: int,
                   recent_event_ids: list[str]) -> dict[str, Any]:
        """DR reconciliation manifest compare -- audit section 7.

        The kiosk sends its local sequence range plus the event_ids it
        believes are already ACKed (its retained recent-ACK replay window).
        This never trusts the kiosk's belief about WHAT was accepted --
        only compares against what kiosk_client_events actually has a row
        for, terminal status or not. A REJECTED row still counts as
        "received" (the server resolved it; it does not need replay). Only
        a true gap -- a sequence/event_id the server has never seen at all
        -- is reported missing. Bounded to a sane manifest size so a
        misbehaving/very-old device can't force an unbounded query.
        """
        seq_min = max(int(seq_min or 0), 0)
        seq_max = max(int(seq_max or 0), seq_min)
        if seq_max - seq_min > 5000:
            seq_min = seq_max - 5000
        recent_event_ids = [str(x) for x in (recent_event_ids or [])][:500]

        rows = fetch_all(
            'SELECT local_sequence, client_event_id FROM kiosk_client_events '
            'WHERE kiosk_id=%s AND local_sequence BETWEEN %s AND %s',
            (kiosk_id, seq_min, seq_max),
        ) if seq_max >= seq_min else []
        known_sequences = {int(r['local_sequence']) for r in rows}

        known_event_ids: set[str] = set()
        if recent_event_ids:
            existing_rows = fetch_all(
                'SELECT client_event_id FROM kiosk_client_events WHERE kiosk_id=%s AND client_event_id = ANY(%s)',
                (kiosk_id, recent_event_ids),
            )
            known_event_ids = {r['client_event_id'] for r in existing_rows}

        result: ReconciliationResult = compute_missing(seq_min, seq_max, known_sequences, recent_event_ids, known_event_ids)

        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE kiosk_identities SET last_generation_id=(SELECT generation_id FROM server_generation WHERE id=1) '
                    'WHERE device_uuid=%s',
                    (kiosk_id,),
                )

        return {
            'missing_sequences': result.missing_sequences,
            'missing_ranges': ranges(result.missing_sequences),
            'missing_event_ids': result.missing_event_ids,
        }
