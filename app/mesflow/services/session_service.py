"""V66 flagship vertical: Work Session start/finish through the new
Route -> Typed Command -> Service -> Domain validation -> Repository ->
Single transaction -> Audit -> Domain Event pipeline.

`SessionService` does not re-implement business rules that already live in
`WorkSessionRepository` (session overlap, PO/operation readiness, quantity
dependency, rework<=defect, idempotent replay, row locking). Per the V66
brief ("Do NOT change MESFlow's existing business rules unless there is
clear evidence the existing implementation is inconsistent"), those stay
exactly where they are. This service only:

  - validates the *command's structural shape* (required fields, no
    negative quantities) before touching the repository,
  - calls the repository inside its existing single-transaction method,
  - publishes a domain event once the transaction has committed
    successfully (never on an idempotent replay -- that would be a
    duplicate event for a request that already happened).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mesflow.db.repositories.execution import WorkSessionRepository
from mesflow.domain.errors import ValidationError
from mesflow.domain.events import EventBus, SessionFinished, SessionStarted, event_bus, utcnow


@dataclass(frozen=True)
class StartSessionCommand:
    employee_id: int
    operation_id: int
    request_id: str
    station_id: int | None = None
    device_uuid: str = ""
    actor_username: str = ""
    actor_user_id: int | None = None
    correlation_id: str = ""


@dataclass(frozen=True)
class StartSessionResult:
    session: dict[str, Any]
    idempotent_replay: bool


@dataclass(frozen=True)
class FinishSessionCommand:
    session_id: int
    request_id: str
    good_qty: int
    defect_qty: int
    rework_qty: int = 0
    note: str = ""
    actor_username: str = ""
    actor_user_id: int | None = None
    correlation_id: str = ""


@dataclass(frozen=True)
class FinishSessionResult:
    session: dict[str, Any]
    idempotent_replay: bool


class SessionService:
    """Application service for the Work Session lifecycle."""

    def __init__(self, repository: WorkSessionRepository | None = None, bus: EventBus | None = None):
        self._repository = repository or WorkSessionRepository()
        self._bus = bus or event_bus

    def start_session(self, command: StartSessionCommand) -> StartSessionResult:
        if not command.request_id.strip():
            raise ValidationError("request_id required")
        if command.employee_id <= 0 or command.operation_id <= 0:
            raise ValidationError("employee_id and operation_id must be positive")

        data = {
            "request_id": command.request_id,
            "employee_id": command.employee_id,
            "operation_id": command.operation_id,
            "station_id": command.station_id,
            "device_uuid": command.device_uuid,
        }
        raw = self._repository.start(
            data,
            audit_actor_username=command.actor_username,
            audit_actor_user_id=command.actor_user_id,
            audit_correlation_id=command.correlation_id or command.request_id,
        )
        session = raw["session"]
        result = StartSessionResult(session=session, idempotent_replay=bool(raw.get("idempotent_replay")))

        if not result.idempotent_replay:
            self._bus.publish(SessionStarted(
                occurred_at=utcnow(),
                correlation_id=command.correlation_id or command.request_id,
                session_id=session["id"],
                operation_id=session["operation_id"],
                employee_id=session["employee_id"],
            ))
        return result

    def finish_session(self, command: FinishSessionCommand) -> FinishSessionResult:
        if not command.request_id.strip():
            raise ValidationError("request_id required")
        if command.good_qty < 0 or command.defect_qty < 0 or command.rework_qty < 0:
            raise ValidationError("quantities must be non-negative")
        if command.session_id <= 0:
            raise ValidationError("session_id must be positive")
        # rework_qty <= defect_qty is an existing MESFlow business rule
        # enforced inside WorkSessionRepository.finish(); intentionally not
        # duplicated here so there is exactly one place that rule lives.

        data = {
            "request_id": command.request_id,
            "good_qty": command.good_qty,
            "defect_qty": command.defect_qty,
            "rework_qty": command.rework_qty,
            "note": command.note,
        }
        raw = self._repository.finish(
            command.session_id,
            data,
            audit_actor_username=command.actor_username,
            audit_actor_user_id=command.actor_user_id,
            audit_correlation_id=command.correlation_id or command.request_id,
        )
        session = raw["session"]
        result = FinishSessionResult(session=session, idempotent_replay=bool(raw.get("idempotent_replay")))

        if not result.idempotent_replay:
            self._bus.publish(SessionFinished(
                occurred_at=utcnow(),
                correlation_id=command.correlation_id or command.request_id,
                session_id=session["id"],
                operation_id=session["operation_id"],
                employee_id=session["employee_id"],
                good_qty=session["good_qty"],
                defect_qty=session["defect_qty"],
                rework_qty=session.get("rework_qty", 0),
            ))
        return result
