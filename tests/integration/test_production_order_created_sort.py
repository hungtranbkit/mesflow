"""The production-order lists sort by creation time, not by edits or code."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

import pytest

from conftest import BASE_URL
from mesflow.db.repositories.master_data import ProductionOrderRepository

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


@pytest.fixture()
def created_order_cases(db):
    suffix = uuid.uuid4().hex[:8].upper()
    created = [
        # Far-future fixture timestamps keep these rows at the front of the
        # global API list even after earlier integration tests leave records.
        datetime(2999, 11, 27, 23, 0, tzinfo=timezone.utc),
        datetime(2999, 11, 28, 0, 0, tzinfo=timezone.utc),
        datetime(2999, 11, 28, 1, 0, tzinfo=timezone.utc),
        datetime(2999, 11, 28, 1, 0, tzinfo=timezone.utc),
    ]
    # Codes deliberately oppose the expected order. Updates also run in the
    # opposite direction so neither lexical PO codes nor updated_at can pass.
    codes = [f"ZZ-CREATED-{suffix}", f"AA-CREATED-{suffix}",
             f"ZZ-TIED-{suffix}", f"AA-TIED-{suffix}"]
    ids = []
    with db.cursor() as cur:
        for index, (code, created_at) in enumerate(zip(codes, created)):
            cur.execute("""INSERT INTO production_orders
                    (code,product,planned_quantity,status,created_at,updated_at)
                VALUES(%s,'Created sort fixture',1,'PLANNED',%s,%s) RETURNING id""",
                (code, created_at, datetime(2026, 11, 28-index, 12, tzinfo=timezone.utc)))
            ids.append(int(cur.fetchone()['id']))
    yield {'suffix': suffix, 'ids': ids, 'codes': codes}
    with db.cursor() as cur:
        cur.execute("DELETE FROM production_orders WHERE id=ANY(%s)", (ids,))


def test_production_order_api_defaults_to_created_at_and_paginates(api, created_order_cases):
    fixture = created_order_cases
    # Newest creation first; equal timestamps are deterministic by id DESC.
    expected = fixture['ids'][3::-1]

    first = api.get(f'{BASE_URL}/api/production-orders?limit=2&offset=0&date=2026-11-28', timeout=25)
    second = api.get(f'{BASE_URL}/api/production-orders?limit=2&offset=2&date=2026-11-28', timeout=25)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    actual = [int(row['id']) for row in first.json()['items'] + second.json()['items']]
    assert actual == expected

    # This screen does not currently apply the date query param. Keep that
    # behavior stable: page/date URL state must not silently alter the result.
    without_date = api.get(f'{BASE_URL}/api/production-orders?limit=20&offset=0', timeout=25)
    with_date = api.get(f'{BASE_URL}/api/production-orders?limit=20&offset=0&date=2026-11-28', timeout=25)
    assert without_date.status_code == with_date.status_code == 200
    ids = {int(row['id']) for row in without_date.json()['items']}
    dated_ids = {int(row['id']) for row in with_date.json()['items']}
    assert set(fixture['ids']) <= ids
    assert ids == dated_ids

    # Callers that already choose an explicit repository sort keep the
    # existing BaseRepository ascending-column behavior.
    explicitly_sorted = ProductionOrderRepository().list(limit=100, order_by='code')
    fixture_codes = [row['code'] for row in explicitly_sorted if row['id'] in fixture['ids']]
    assert fixture_codes == sorted(fixture['codes'])


def test_dashboard_overview_keeps_creation_order_for_production_orders(api, created_order_cases):
    fixture = created_order_cases
    response = api.get(f'{BASE_URL}/api/dashboard/overview?limit=500', timeout=25)
    assert response.status_code == 200, response.text
    rows = response.json()['production_orders']
    fixture_rows = [row for row in rows if int(row['po_id']) in set(fixture['ids'])]
    assert [int(row['po_id']) for row in fixture_rows] == fixture['ids'][3::-1]
