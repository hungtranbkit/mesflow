"""V66 transactional audit helper.

MESFlow already has `mesflow.db.repositories.analytics.AuditRepository`,
used by ~10 existing routes (`AuditRepository().log(...)`). That helper
opens its *own* transaction, so it is fine for routes that log after their
mutation has already committed, but it cannot make the audit row atomic
with the mutation it describes.

`record_audit()` is the transactionally-consistent sibling: it takes an
*existing* open cursor (the same one the caller used for its business
mutation) and inserts into the same `audit_logs` table the existing
`AuditRepository` uses, using the additive columns from migration
`0030_v66_audit_foundation` (correlation_id, actor_user_id, employee_id,
before_json, after_json, source). Existing rows/readers of `audit_logs` are
unaffected -- the new columns are nullable/defaulted and old call sites
that only set actor_username/action/entity_type/entity_id/details_json
keep working unchanged.

Policy: audit failure must not silently corrupt the business mutation, but
it also must not stay hidden. Because this helper is called with the
caller's own cursor/transaction, a failed audit insert raises like any
other statement in that transaction -- the whole business command rolls
back together with it (no half-applied mutation with a missing audit
trail). Call sites that intentionally want a business mutation to succeed
even if audit logging fails should catch the exception around
`record_audit()` explicitly and log the failure instead of using it inline.
"""
from __future__ import annotations

import json
from typing import Any


def record_audit(
    cur,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_username: str = "",
    actor_user_id: int | None = None,
    employee_id: int | None = None,
    correlation_id: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    source: str = "",
) -> dict:
    """Insert one audit_logs row using the caller's existing cursor/transaction.

    `before`/`after`/`metadata` must already be JSON-safe (see
    `mesflow.db.repositories.execution._json_safe` for the helper existing
    repositories use to convert datetimes/Decimals/UUIDs before this call).
    Never pass secrets/tokens/passwords/cookies in any of these fields.
    """
    cur.execute(
        """INSERT INTO audit_logs(
             actor_username, action, entity_type, entity_id, details_json,
             actor_user_id, employee_id, correlation_id, before_json, after_json, source
           ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (
            actor_username or "",
            action,
            entity_type,
            entity_id,
            json.dumps(metadata or {}, ensure_ascii=False, default=str),
            actor_user_id,
            employee_id,
            correlation_id or "",
            json.dumps(before or {}, ensure_ascii=False, default=str),
            json.dumps(after or {}, ensure_ascii=False, default=str),
            source or "",
        ),
    )
    return cur.fetchone()
