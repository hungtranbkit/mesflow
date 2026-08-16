"""V66 architecture foundation: domain error hierarchy and the in-process
event bus. Pure unit tests -- no PostgreSQL required."""
from datetime import datetime, timezone

import pytest

from mesflow.domain.errors import (
    ConflictError,
    DomainError,
    InvalidStateError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from mesflow.db.repositories.base import ConflictError as RepoConflictError
from mesflow.db.repositories.base import NotFoundError as RepoNotFoundError
from mesflow.domain.events import DomainEvent, EventBus, SessionFinished, SessionStarted
from mesflow.web.errors import api_error_response


# --- error hierarchy -------------------------------------------------------

def test_domain_errors_carry_a_stable_code():
    assert ValidationError().code == "VALIDATION_ERROR"
    assert PermissionDeniedError().code == "PERMISSION_DENIED"
    assert NotFoundError().code == "NOT_FOUND"
    assert ConflictError().code == "CONFLICT"
    assert InvalidStateError().code == "INVALID_STATE"


def test_domain_not_found_and_conflict_are_interchangeable_with_repository_errors():
    """Service code raising mesflow.domain.errors.NotFoundError/ConflictError
    must still be caught by any existing `except NotFoundError` /
    `except ConflictError` clause that imports from
    mesflow.db.repositories.base -- this is what keeps api_error_response
    (and any other existing call site) working unchanged."""
    assert isinstance(NotFoundError("x"), RepoNotFoundError)
    assert isinstance(ConflictError("x"), RepoConflictError)
    assert isinstance(InvalidStateError("x"), RepoConflictError)
    assert isinstance(NotFoundError("x"), DomainError)


def test_api_error_response_maps_new_domain_errors_to_stable_http_status(monkeypatch):
    import flask
    app = flask.Flask(__name__)
    with app.test_request_context():
        _, status = api_error_response(ValidationError("bad input"))
        assert status == 400
        _, status = api_error_response(PermissionDeniedError("nope"))
        assert status == 403
        _, status = api_error_response(NotFoundError("missing"))
        assert status == 404
        _, status = api_error_response(ConflictError("conflict"))
        assert status == 409
        _, status = api_error_response(InvalidStateError("bad transition"))
        assert status == 409


def test_api_error_response_existing_status_codes_unchanged_for_plain_repository_errors():
    """Regression guard: the pre-V66 error types must keep their exact
    pre-V66 HTTP status codes."""
    import flask
    app = flask.Flask(__name__)
    with app.test_request_context():
        _, status = api_error_response(RepoNotFoundError("missing"))
        assert status == 404
        _, status = api_error_response(RepoConflictError("conflict"))
        assert status == 409
        _, status = api_error_response(ValueError("bad"))
        assert status == 400
        _, status = api_error_response(RuntimeError("boom"))
        assert status == 500


# --- event bus ---------------------------------------------------------

def test_event_bus_dispatches_only_to_matching_subscribers():
    bus = EventBus()
    seen = []
    bus.subscribe(SessionFinished, lambda e: seen.append(("finished", e)))
    bus.subscribe(SessionStarted, lambda e: seen.append(("started", e)))

    started = SessionStarted(occurred_at=datetime.now(timezone.utc), correlation_id="corr-1",
                              session_id=1, operation_id=2, employee_id=3)
    bus.publish(started)

    assert len(seen) == 1
    assert seen[0][0] == "started"
    assert seen[0][1].correlation_id == "corr-1"


def test_event_bus_carries_correlation_id_through_to_handlers():
    bus = EventBus()
    received = {}
    bus.subscribe(SessionFinished, lambda e: received.update(correlation_id=e.correlation_id))
    event = SessionFinished(occurred_at=datetime.now(timezone.utc), correlation_id="trace-abc-123",
                             session_id=10, operation_id=20, employee_id=30,
                             good_qty=5, defect_qty=1, rework_qty=0)
    bus.publish(event)
    assert received["correlation_id"] == "trace-abc-123"


def test_event_bus_handler_failure_is_isolated_and_does_not_propagate():
    """A broken handler must never crash publish() or block other handlers --
    domain events must not be able to fail the HTTP request that produced
    them, since publish() only ever runs after the DB transaction commits."""
    bus = EventBus()
    calls = []

    def broken_handler(event):
        raise RuntimeError("handler exploded")

    def healthy_handler(event):
        calls.append(event)

    bus.subscribe(SessionStarted, broken_handler)
    bus.subscribe(SessionStarted, healthy_handler)

    event = SessionStarted(occurred_at=datetime.now(timezone.utc), correlation_id="c",
                            session_id=1, operation_id=1, employee_id=1)
    bus.publish(event)  # must not raise

    assert calls == [event]


def test_event_bus_subscribe_is_idempotent_for_the_same_handler():
    bus = EventBus()
    calls = []

    def handler(event):
        calls.append(event)

    bus.subscribe(SessionStarted, handler)
    bus.subscribe(SessionStarted, handler)  # create_app() called twice, e.g. in tests

    event = SessionStarted(occurred_at=datetime.now(timezone.utc), correlation_id="c",
                            session_id=1, operation_id=1, employee_id=1)
    bus.publish(event)

    assert len(calls) == 1


def test_domain_event_is_frozen_and_immutable():
    event = SessionStarted(occurred_at=datetime.now(timezone.utc), correlation_id="c",
                            session_id=1, operation_id=1, employee_id=1)
    with pytest.raises(Exception):
        event.session_id = 999  # type: ignore[misc]
