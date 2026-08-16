from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
from mesflow.services.production_trace_service import TraceEvent
ROOT=Path(__file__).parents[1]
def test_trace_event_normalized_contract():
    e=TraceEvent('1','SESSION_STARTED','SESSION',datetime.now(timezone.utc),1,'admin',2,3,4,5,'Bắt đầu','',None,{},'corr','session-trace','NATIVE')
    assert set(asdict(e))=={'id','event_type','category','occurred_at','actor_id','actor_name','po_id','part_id','operation_id','session_id','title','description','quantity_delta','metadata','correlation_id','session_trace_id','source'}
def test_v68_schema_is_append_only_and_indexed():
    s=(ROOT/'app/migrations/versions/0032_v68_production_trace.py').read_text()
    assert "down_revision='0031_v67_exception_center'" in s
    assert 'CREATE TABLE production_trace_events' in s and 'CREATE TABLE quantity_movements' in s
    for key in ('idx_trace_po_time','idx_trace_operation_time','idx_trace_session_time','idx_trace_correlation','idx_trace_session_trace','idx_quantity_session_time'):assert key in s
    assert 'UPDATE quantity_movements' not in s and 'UPDATE production_trace_events' not in s
def test_read_model_marks_legacy_inference_and_keeps_sources_distinct():
    s=(ROOT/'app/mesflow/services/production_trace_service.py').read_text()
    for source in ('LEGACY_DERIVED','V67_EXCEPTION','KIOSK','AUDIT','NATIVE'):assert source in s
    assert 'Input Consumption' not in s
