"""Pure unit tests for mesflow.services.session_service.SessionService --
added as a critical-unit coverage gap fix (QA Center production-policy
critical_unit suite): SessionService.start_session()/finish_session() had
no direct unit coverage. Its own module docstring is explicit that the
real business rules (session overlap, rework<=defect, idempotent replay)
intentionally live in WorkSessionRepository and are exercised at
integration level (see mes_workflows in qa-center's qualification/live.py
and tests/integration/) -- this file covers exactly the layer that DOES
belong here: command-shape validation before the repository is ever
touched, and the idempotent-replay-must-not-double-publish-an-event rule,
both pure/no-DB and mockable.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mesflow.domain.errors import ValidationError
from mesflow.domain.events import EventBus
from mesflow.services.session_service import (
    FinishSessionCommand,
    SessionService,
    StartSessionCommand,
)


def _service():
    repo = MagicMock()
    bus = MagicMock(spec=EventBus)
    return SessionService(repository=repo, bus=bus), repo, bus


# --- start_session: structural validation happens before the repository is touched ---

def test_start_session_rejects_blank_request_id_without_touching_repository():
    service, repo, bus = _service()
    with pytest.raises(ValidationError):
        service.start_session(StartSessionCommand(employee_id=1, operation_id=1, request_id="   "))
    repo.start.assert_not_called()
    bus.publish.assert_not_called()


@pytest.mark.parametrize("employee_id,operation_id", [(0, 1), (-1, 1), (1, 0), (1, -5)])
def test_start_session_rejects_non_positive_employee_or_operation_id(employee_id, operation_id):
    service, repo, bus = _service()
    with pytest.raises(ValidationError):
        service.start_session(StartSessionCommand(employee_id=employee_id, operation_id=operation_id, request_id="R1"))
    repo.start.assert_not_called()


def test_start_session_publishes_session_started_event_on_a_real_start():
    service, repo, bus = _service()
    repo.start.return_value = {"session": {"id": 42, "operation_id": 7, "employee_id": 3}, "idempotent_replay": False}
    result = service.start_session(StartSessionCommand(employee_id=3, operation_id=7, request_id="R1"))
    assert result.idempotent_replay is False
    bus.publish.assert_called_once()
    published = bus.publish.call_args[0][0]
    assert published.session_id == 42 and published.employee_id == 3 and published.operation_id == 7


def test_start_session_idempotent_replay_does_not_publish_a_duplicate_event():
    # This is the exact rule the module docstring calls out: "never on an
    # idempotent replay -- that would be a duplicate event for a request
    # that already happened." A regression here would silently double-fire
    # SessionStarted for every retried/duplicated kiosk request.
    service, repo, bus = _service()
    repo.start.return_value = {"session": {"id": 42, "operation_id": 7, "employee_id": 3}, "idempotent_replay": True}
    result = service.start_session(StartSessionCommand(employee_id=3, operation_id=7, request_id="R1"))
    assert result.idempotent_replay is True
    bus.publish.assert_not_called()


# --- finish_session: quantity-shape validation before the repository is touched ---

@pytest.mark.parametrize("good_qty,defect_qty,rework_qty", [(-1, 0, 0), (0, -1, 0), (0, 0, -1)])
def test_finish_session_rejects_negative_quantities_without_touching_repository(good_qty, defect_qty, rework_qty):
    service, repo, bus = _service()
    with pytest.raises(ValidationError):
        service.finish_session(FinishSessionCommand(session_id=1, request_id="R1", good_qty=good_qty,
                                                     defect_qty=defect_qty, rework_qty=rework_qty))
    repo.finish.assert_not_called()
    bus.publish.assert_not_called()


def test_finish_session_rejects_blank_request_id():
    service, repo, bus = _service()
    with pytest.raises(ValidationError):
        service.finish_session(FinishSessionCommand(session_id=1, request_id="", good_qty=1, defect_qty=0, rework_qty=0))
    repo.finish.assert_not_called()


def test_finish_session_rejects_non_positive_session_id():
    service, repo, bus = _service()
    with pytest.raises(ValidationError):
        service.finish_session(FinishSessionCommand(session_id=0, request_id="R1", good_qty=1, defect_qty=0, rework_qty=0))
    repo.finish.assert_not_called()


def test_finish_session_does_not_reimplement_rework_le_defect_rule_locally():
    # Deliberate: rework_qty > defect_qty must NOT be rejected by this
    # service layer -- that rule lives exactly once, in
    # WorkSessionRepository.finish() (see module docstring). If this
    # service started enforcing it too, the two enforcement points could
    # drift; the repository mock accepting the call through proves the
    # service itself imposes no such check.
    service, repo, bus = _service()
    repo.finish.return_value = {"session": {"id": 1, "operation_id": 2, "employee_id": 3,
                                             "good_qty": 0, "defect_qty": 1, "rework_qty": 5}, "idempotent_replay": False}
    service.finish_session(FinishSessionCommand(session_id=1, request_id="R1", good_qty=0, defect_qty=1, rework_qty=5))
    repo.finish.assert_called_once()


def test_finish_session_idempotent_replay_does_not_publish_a_duplicate_event():
    service, repo, bus = _service()
    repo.finish.return_value = {"session": {"id": 1, "operation_id": 2, "employee_id": 3,
                                             "good_qty": 5, "defect_qty": 0, "rework_qty": 0}, "idempotent_replay": True}
    result = service.finish_session(FinishSessionCommand(session_id=1, request_id="R1", good_qty=5, defect_qty=0, rework_qty=0))
    assert result.idempotent_replay is True
    bus.publish.assert_not_called()


def test_finish_session_passes_correlation_id_through_to_the_repository_for_dedup():
    # correlation_id is how the repository's own duplicate-request guard
    # (see WorkSessionRepository) recognizes a retried request; the service
    # must forward it (falling back to request_id when unset), never drop it.
    service, repo, bus = _service()
    repo.finish.return_value = {"session": {"id": 1, "operation_id": 2, "employee_id": 3,
                                             "good_qty": 1, "defect_qty": 0, "rework_qty": 0}, "idempotent_replay": False}
    service.finish_session(FinishSessionCommand(session_id=1, request_id="R1", good_qty=1, defect_qty=0, rework_qty=0))
    _, kwargs = repo.finish.call_args
    assert kwargs["audit_correlation_id"] == "R1"
