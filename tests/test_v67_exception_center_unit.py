"""Fast V67 architecture and lifecycle regression tests (no database)."""
from pathlib import Path
import pytest
from mesflow.domain.events import EventBus,ExceptionDetected,ExceptionStateChanged
from mesflow.services.exception_service import ExceptionDecisionCommand,ExceptionDetectionService,ExceptionService
ROOT=Path(__file__).parents[1]
class FakeRepository:
    def __init__(self):self.row={'id':7,'exception_type':'LONG_OPEN_SESSION','severity':'HIGH','status':'OPEN','row_version':1,'condition_active':False,'auto_ignore_reason':None}
    def detected_conditions(self):return [{'fingerprint':'LONG_OPEN_SESSION:SESSION:7'}]
    def reconcile(self,conditions,correlation_id):return [{'id':7,'exception_type':'LONG_OPEN_SESSION','severity':'HIGH'}]
    def get(self,_):return dict(self.row)
    def transition(self,exception_id,target,expected_version,actor_id,actor,reason,correlation_id):
        assert expected_version==1 and exception_id==7;self.row={**self.row,'status':target,'row_version':2};return dict(self.row)
def command(reason='đã kiểm tra'):return ExceptionDecisionCommand(7,1,3,'supervisor',reason,'trace-v67')
def test_detection_publishes_event_with_correlation_id():
    repo=FakeRepository();bus=EventBus();seen=[];bus.subscribe(ExceptionDetected,seen.append);created=ExceptionDetectionService(repo,bus).reconcile('trace-v67');assert created[0]['id']==7 and seen[0].correlation_id=='trace-v67'
@pytest.mark.parametrize(('method','expected'),[('acknowledge','ACKNOWLEDGED'),('resolve','RESOLVED'),('ignore','MANUAL_IGNORED')])
def test_typed_decisions_publish_state_event(method,expected):
    repo=FakeRepository();bus=EventBus();seen=[];bus.subscribe(ExceptionStateChanged,seen.append);row=getattr(ExceptionService(repo,bus),method)(command());assert row['status']==expected and seen[0].previous_status=='OPEN' and seen[0].new_status==expected
def test_migration_is_additive_indexed_and_append_only():
    source=(ROOT/'app/migrations/versions/0031_v67_exception_center.py').read_text();assert 'down_revision="0030_v66_audit_foundation"' in source;assert 'CREATE TABLE exception_records' in source and 'CREATE TABLE exception_history' in source;assert 'uq_exception_active_fingerprint' in source;assert 'idx_exception_status_severity_time' in source and 'idx_exception_session' in source;assert 'UPDATE exception_history' not in source
def test_routes_keep_legacy_api_and_enforce_backend_roles():
    new=(ROOT/'app/mesflow/web/exceptions.py').read_text();old=(ROOT/'app/mesflow/web/analytics.py').read_text()
    for path in ("'/exceptions'","'/exceptions/<int:exception_id>/acknowledge'","'/sessions/<int:session_id>/context'"):assert path in new
    assert "@roles_required('admin','manager','supervisor')" in new and "@bp.get('/session-exceptions')" in old
def test_repository_has_dedup_race_and_stale_write_guards():
    source=(ROOT/'app/mesflow/db/repositories/exceptions.py').read_text();assert 'FOR UPDATE' in source;assert "row_version']!=expected_version" in source;assert 'uq_exception_active_fingerprint' in (ROOT/'app/migrations/versions/0031_v67_exception_center.py').read_text();assert "severity'] in ('HIGH','CRITICAL')" in source
