"""Default in-process handlers for V66 domain events.

Registered once at app startup (`create_app()` in `mesflow.web.app`). Keep
handlers here small and side-effect-light -- anything that needs its own
retry/queueing semantics is future work, not part of this foundation.
"""
from __future__ import annotations

import logging

from mesflow.domain.events import EventBus, ExceptionDetected, ExceptionStateChanged, SessionFinished, SessionStarted

logger = logging.getLogger("mesflow.domain.events")


def _log_session_started(event: SessionStarted) -> None:
    logger.info(
        "event=SessionStarted session_id=%s operation_id=%s employee_id=%s correlation_id=%s",
        event.session_id, event.operation_id, event.employee_id, event.correlation_id,
    )


def _log_session_finished(event: SessionFinished) -> None:
    logger.info(
        "event=SessionFinished session_id=%s operation_id=%s employee_id=%s good=%s defect=%s rework=%s correlation_id=%s",
        event.session_id, event.operation_id, event.employee_id,
        event.good_qty, event.defect_qty, event.rework_qty, event.correlation_id,
    )

def _log_exception_detected(event: ExceptionDetected) -> None:
    logger.info("event=ExceptionDetected exception_id=%s type=%s severity=%s correlation_id=%s",
                event.exception_id,event.exception_type,event.severity,event.correlation_id)

def _log_exception_changed(event: ExceptionStateChanged) -> None:
    logger.info("event=ExceptionStateChanged exception_id=%s action=%s status=%s->%s correlation_id=%s",
                event.exception_id,event.action,event.previous_status,event.new_status,event.correlation_id)


def register_default_handlers(bus: EventBus) -> None:
    """Wire the built-in handlers onto `bus`. Idempotent-ish: calling this
    twice on the same bus double-subscribes, so callers (app factory,
    tests) should call it exactly once per bus instance -- tests that need
    a clean bus should call `bus.clear()` first or use a fresh `EventBus()`.

    Future consumers (notifications, realtime dashboard, analytics, MES
    integration, QA/reconciliation) subscribe here the same way, without
    touching the services that publish these events.
    """
    bus.subscribe(SessionStarted, _log_session_started)
    bus.subscribe(SessionFinished, _log_session_finished)
    bus.subscribe(ExceptionDetected, _log_exception_detected)
    bus.subscribe(ExceptionStateChanged, _log_exception_changed)
