from __future__ import annotations

import secrets
from typing import Any

from mesflow.db.connection import fetch_one, transaction
from mesflow.db.repositories.base import NotFoundError


class ServerGenerationRepository:
    """Durable cluster/generation identity for kiosk DR reconciliation.

    See reports/KIOSK_OFFLINE_DR_SYNC_AUDIT.md section 6. `cluster_id` is a
    stable logical name (default 'MESFLOW-PROD'), never a physical server
    IP/hostname -- Production Test/Production both point kiosks at the same
    kind of stable DNS/service URL (see bootstrap/guide_content.py's
    server-role section for the equivalent MESFlow-server-side rule); only
    `generation_id` changes, and only via an explicit admin action, never
    inferred from server state (never "the DB looks emptier than usual so
    let's assume DR happened" -- that kind of heuristic is exactly the
    silent-guess this repository exists to avoid).
    """

    def current(self) -> dict[str, Any]:
        row = fetch_one('SELECT * FROM server_generation WHERE id=1')
        if not row:
            raise NotFoundError('server_generation not seeded -- run migrations')
        return dict(row)

    def bump(self, reason: str, actor: str) -> dict[str, Any]:
        """Mint a new generation_id. Call this exactly once per real DR
        event (failover to a restored/promoted server), from an operator
        action -- see the admin endpoint POST /api/admin/server-generation/bump.
        Every bound kiosk will see its next heartbeat/bind response's
        generation_id differ from what it stored locally and enter
        RECONCILING."""
        new_generation = secrets.token_hex(8)
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE server_generation SET generation_id=%s, bumped_at=CURRENT_TIMESTAMP,
                       bumped_by=%s, reason=%s WHERE id=1 RETURNING *""",
                    (new_generation, str(actor or ''), str(reason or '')),
                )
                row = cur.fetchone()
                if not row:
                    raise NotFoundError('server_generation not seeded -- run migrations')
                return dict(row)
