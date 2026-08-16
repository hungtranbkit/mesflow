"""V66 lightweight in-process domain event foundation.

This is NOT a message broker. There is no queue, no persistence, no network
hop -- `EventBus.publish()` calls each subscribed handler synchronously, in
the same process, in the same request. It exists so a service can announce
"this business fact just happened" without hard-coding every future
consumer (notifications, realtime dashboard, analytics, MES integration)
into the service method itself.

Failure policy (explicit, per V66 spec section 8/11):
  - `publish()` is only ever called *after* the owning database transaction
    has committed. An event handler must never be relied on to roll back a
    business mutation -- it is already durable by the time handlers run.
  - A handler that raises is logged and skipped; it never propagates out of
    `publish()` and never fails the HTTP request that triggered it. One
    broken handler must not take down the others or the caller.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, DefaultDict, Type, TypeVar
from collections import defaultdict

logger = logging.getLogger("mesflow.domain.events")


@dataclass(frozen=True)
class DomainEvent:
    """Common shape for every domain event.

    `correlation_id` should be the same value threaded through the HTTP
    request (`g.trace_id`, see `mesflow.web.action_logging`) and the audit
    record for the mutation that produced this event, so a single ID can
    trace: HTTP request -> service command -> database mutation -> audit
    row -> event -> logs.
    """

    occurred_at: datetime
    correlation_id: str


@dataclass(frozen=True)
class SessionStarted(DomainEvent):
    session_id: int
    operation_id: int
    employee_id: int


@dataclass(frozen=True)
class SessionFinished(DomainEvent):
    session_id: int
    operation_id: int
    employee_id: int
    good_qty: int
    defect_qty: int
    rework_qty: int

@dataclass(frozen=True)
class ExceptionDetected(DomainEvent):
    exception_id: int
    exception_type: str
    severity: str

@dataclass(frozen=True)
class ExceptionStateChanged(DomainEvent):
    exception_id: int
    action: str
    previous_status: str
    new_status: str


TEvent = TypeVar("TEvent", bound=DomainEvent)
Handler = Callable[[TEvent], None]


class EventBus:
    """Simple synchronous in-process publish/subscribe registry."""

    def __init__(self) -> None:
        self._handlers: DefaultDict[Type[DomainEvent], list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: Type[TEvent], handler: Handler) -> None:
        # Idempotent: re-subscribing the same handler (e.g. create_app()
        # called more than once in one process, as some tests do) is a
        # no-op rather than a duplicate call on every publish().
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        for handler in list(self._handlers.get(type(event), ())):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 - handler failure must never propagate
                logger.exception(
                    "Domain event handler failed: event=%s correlation_id=%s handler=%s",
                    type(event).__name__, event.correlation_id, getattr(handler, "__qualname__", handler),
                )

    def clear(self) -> None:
        """Test-only: reset all subscriptions."""
        self._handlers.clear()


#: Process-wide singleton. Services publish through this; `create_app()`
#: registers the default handlers on it once at startup (see
#: `mesflow.domain.event_handlers.register_default_handlers`).
event_bus = EventBus()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
