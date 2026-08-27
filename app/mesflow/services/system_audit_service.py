"""Technical / privileged-action audit trail for the SUPER_ADMIN System
Console -- distinct from the business audit (audit.py/audit_presentation.py,
who changed which PO/session/quantity). This one records who did what to
MESFlow *itself*: SUPER_ADMIN grant/revoke, service restarts, repair
actions, and other configuration-changing technical operations.

Append-only by construction: no update()/delete() function exists here, and
no route ever calls raw SQL against this table outside record()/list_recent().
"""
from __future__ import annotations

import json
from typing import Any

from flask import session

from mesflow.core.config import settings
from mesflow.db.connection import fetch_all, transaction


def record(action: str, *, target: str = '', reason: str = '', result: str = '',
           correlation_id: str = '', detail: dict[str, Any] | None = None) -> None:
    """Best-effort: a failure to write the audit row must never be allowed
    to make the privileged action itself appear to fail (or, worse, silently
    swallow a real failure) -- callers still return the action's own real
    result regardless of whether this succeeds. Actor identity always comes
    from the current server-side session, never from request body input."""
    try:
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO system_audit_log
                       (actor_user_id,actor_username,actor_role,environment,action,target,reason,result,correlation_id,detail_json)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (session.get('user_id'), session.get('username', ''), session.get('role', ''),
                     settings.environment, action, target, reason, result, correlation_id,
                     json.dumps(detail or {}, ensure_ascii=False, default=str)),
                )
    except Exception:
        pass


def list_recent(limit: int = 200) -> list[dict[str, Any]]:
    limit = max(1, min(1000, int(limit)))
    return fetch_all(
        "SELECT * FROM system_audit_log ORDER BY id DESC LIMIT %s", (limit,)
    )
