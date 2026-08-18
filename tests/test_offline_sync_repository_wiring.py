"""Mocked wiring tests for OfflineSyncRepository.reconcile() and the
duplicate-counting path in process_event() -- verifies the DB-facing glue
around the already-unit-tested pure algorithm in
mesflow.services.kiosk_reconciliation (see test_kiosk_reconciliation.py).

No PostgreSQL connection: mesflow.db.repositories.offline_sync's
fetch_one/fetch_all/transaction are patched. This checks that reconcile()
queries the right table/columns and returns the shape
web/execution.py's /api/kiosk/reconcile route expects, not the gap
algorithm itself (already covered elsewhere).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mesflow.db.repositories.offline_sync import OfflineSyncRepository

pytestmark = pytest.mark.unit


def _fake_conn():
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


class TestReconcileWiring:
    def test_reconcile_reports_gap_from_mocked_rows_and_updates_generation(self):
        # Server B: only sequences 100-105 recorded for this kiosk.
        known_rows = [{'local_sequence': n, 'client_event_id': f'K-{n:010d}'} for n in range(100, 106)]
        tx_ctx, cur = _fake_conn()
        with patch('mesflow.db.repositories.offline_sync.fetch_all', return_value=known_rows) as fetch_all_mock, \
             patch('mesflow.db.repositories.offline_sync.transaction', return_value=tx_ctx):
            result = OfflineSyncRepository().reconcile(
                'KIOSK-01', 100, 110,
                [f'K-{n:010d}' for n in range(100, 111)],
            )
        assert result['missing_sequences'] == [106, 107, 108, 109, 110]
        assert result['missing_ranges'] == [[106, 110]]
        assert result['missing_event_ids'] == [f'K-{n:010d}' for n in range(106, 111)]
        # First fetch_all call is the sequence-range query, scoped to this kiosk.
        first_call_sql = fetch_all_mock.call_args_list[0].args[0]
        assert 'kiosk_client_events' in first_call_sql
        assert 'local_sequence BETWEEN' in first_call_sql
        # The generation bookkeeping UPDATE ran against kiosk_identities.
        update_sql = cur.execute.call_args_list[0].args[0]
        assert 'UPDATE kiosk_identities' in update_sql
        assert 'last_generation_id' in update_sql

    def test_reconcile_bounds_absurd_ranges_to_5000(self):
        tx_ctx, _cur = _fake_conn()
        with patch('mesflow.db.repositories.offline_sync.fetch_all', return_value=[]) as fetch_all_mock, \
             patch('mesflow.db.repositories.offline_sync.transaction', return_value=tx_ctx):
            OfflineSyncRepository().reconcile('KIOSK-01', 0, 10_000_000, [])
        params = fetch_all_mock.call_args_list[0].args[1]
        seq_min, seq_max = params[1], params[2]
        assert seq_max - seq_min == 5000

    def test_reconcile_with_no_events_in_range_returns_full_gap(self):
        tx_ctx, _cur = _fake_conn()
        with patch('mesflow.db.repositories.offline_sync.fetch_all', return_value=[]), \
             patch('mesflow.db.repositories.offline_sync.transaction', return_value=tx_ctx):
            result = OfflineSyncRepository().reconcile('KIOSK-99', 5, 7, ['K-A', 'K-B'])
        assert result['missing_sequences'] == [5, 6, 7]
        assert result['missing_event_ids'] == ['K-A', 'K-B']


class TestDuplicateCounting:
    def test_duplicate_replay_increments_counter_and_sequence_high_water_mark(self):
        existing = {'payload_hash': 'abc123', 'server_session_id': 42, 'local_sequence': 7}
        tx_ctx, cur = _fake_conn()
        with patch.object(OfflineSyncRepository, '_existing', return_value=existing), \
             patch('mesflow.db.repositories.offline_sync._canonical_hash', return_value='abc123'), \
             patch('mesflow.db.repositories.offline_sync.transaction', return_value=tx_ctx):
            result = OfflineSyncRepository().process_event(
                'KIOSK-01', 1, {'client_event_id': 'E7', 'local_sequence': 7, 'event_type': 'START'},
            )
        assert result == {'client_event_id': 'E7', 'status': 'duplicate', 'server_session_id': 42}
        update_sql = cur.execute.call_args_list[0].args[0]
        assert 'duplicate_replay_count=duplicate_replay_count+1' in update_sql
        assert 'last_sequence_received=GREATEST' in update_sql

    def test_payload_conflict_is_rejected_not_treated_as_duplicate(self):
        existing = {'payload_hash': 'DIFFERENT-HASH', 'server_session_id': 42, 'local_sequence': 7}
        with patch.object(OfflineSyncRepository, '_existing', return_value=existing), \
             patch('mesflow.db.repositories.offline_sync._canonical_hash', return_value='abc123'):
            result = OfflineSyncRepository().process_event(
                'KIOSK-01', 1, {'client_event_id': 'E7', 'local_sequence': 7, 'event_type': 'START'},
            )
        assert result == {'client_event_id': 'E7', 'status': 'rejected', 'reason_code': 'IDEMPOTENCY_PAYLOAD_CONFLICT'}
