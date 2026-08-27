"""V67 typed commands and application services for exception decisions."""
from __future__ import annotations
import time
from dataclasses import dataclass
import psycopg
from mesflow.db.repositories.base import ConflictError
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
        # Deadlock-retry defense in depth: ExceptionRepository.reconcile()
        # sorts its row-lock acquisition order to make a deadlock unlikely
        # (see that method's own comment), but a residual race between
        # concurrent callers at DIFFERENT phases of the transaction is still
        # possible under real concurrent load -- found live via
        # tests/integration/test_v67_exception_center.py's 5-simultaneous-
        # requests test. reconcile() is safe to retry whole: detected_conditions()
        # is a pure read, and the UPSERT/ON CONFLICT DO NOTHING + condition_active
        # bookkeeping it drives are all idempotent for the SAME underlying
        # condition set. Bounded (3 attempts, small jittered backoff) --
        # never an unbounded retry loop.
        attempts=0
        while True:
            attempts+=1
            try:
                created=self.repository.reconcile(self.repository.detected_conditions(),correlation_id)
                break
            except psycopg.errors.DeadlockDetected:
                if attempts>=3: raise
                time.sleep(0.05*attempts)
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
    def resolve(self,command):
        # Resolution verification (2026-08-27 Session Exception Management
        # task, §9/§19): "Hoàn tất"/RESOLVED must never be a blind status
        # flip -- re-run the SAME detector reconcile() every list load
        # already uses, immediately before honoring this decision, so a
        # manager can't mark something resolved without the underlying
        # condition actually having cleared. If it's still active, refuse
        # with a clear, actionable message rather than a false green light.
        #
        # Note (found live testing this exact change, not a bug -- see
        # ExceptionRepository.reconcile()'s own SESSION_ALREADY_CLOSED/
        # can_auto logic): for exception types whose condition_active
        # clears via that path (any LOW/MEDIUM-severity type, plus LONG_
        # OPEN_SESSION/OPERATION_COMPLETED_SESSION_OPEN/SESSION_PAST_
        # SHIFT_END regardless of severity), THIS SAME reconcile() call
        # will itself auto-transition the record to AUTO_IGNORED the
        # instant the fix is confirmed -- a manual "Hoàn tất" is only ever
        # actually reachable in practice for the severities that DON'T
        # auto-resolve (currently HIGH/CRITICAL types outside that special
        # list, e.g. EMPLOYEE_SESSION_CONFLICT/INVALID_DURATION), which is
        # correct: those need a human decision, the others are confirmed
        # fixed automatically and don't need one.
        ExceptionDetectionService(self.repository,self.bus).reconcile(command.correlation_id)
        current=self.repository.get(command.exception_id)
        if current['condition_active'] and current['status'] in ('OPEN','ACKNOWLEDGED'):
            raise ConflictError(
                'Bất thường vẫn còn tồn tại sau khi kiểm tra lại -- hãy mở Session và sửa dữ liệu trước, '
                'hoặc chọn Bỏ qua nếu không cần thay đổi dữ liệu.')
        return self._transition(command,'RESOLVED','RESOLVED')
    def ignore(self,command): return self._transition(command,'MANUAL_IGNORED','IGNORED')
