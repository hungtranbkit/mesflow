"""V67 typed commands and application services for exception decisions."""
from __future__ import annotations
from dataclasses import dataclass
from mesflow.db.repositories.exceptions import ExceptionRepository
from mesflow.domain.events import EventBus, ExceptionDetected, ExceptionStateChanged, event_bus, utcnow

@dataclass(frozen=True)
class ExceptionDecisionCommand:
    exception_id:int
    expected_version:int
    actor_id:int|None
    actor_username:str
    reason:str=''
    correlation_id:str=''

class ExceptionDetectionService:
    def __init__(self,repository=None,bus:EventBus|None=None):
        self.repository=repository or ExceptionRepository();self.bus=bus or event_bus
    def reconcile(self,correlation_id=''):
        created=self.repository.reconcile(self.repository.detected_conditions(),correlation_id)
        for row in created:
            self.bus.publish(ExceptionDetected(utcnow(),correlation_id,row['id'],row['exception_type'],row['severity']))
        return created

class ExceptionService:
    def __init__(self,repository=None,bus:EventBus|None=None):
        self.repository=repository or ExceptionRepository();self.bus=bus or event_bus
    def _transition(self,command,target,action):
        before=self.repository.get(command.exception_id)
        row=self.repository.transition(command.exception_id,target,command.expected_version,command.actor_id,command.actor_username,command.reason,command.correlation_id)
        self.bus.publish(ExceptionStateChanged(utcnow(),command.correlation_id,row['id'],action,before['status'],row['status']))
        return row
    def acknowledge(self,command): return self._transition(command,'ACKNOWLEDGED','ACKNOWLEDGED')
    def resolve(self,command): return self._transition(command,'RESOLVED','RESOLVED')
    def ignore(self,command): return self._transition(command,'MANUAL_IGNORED','IGNORED')
