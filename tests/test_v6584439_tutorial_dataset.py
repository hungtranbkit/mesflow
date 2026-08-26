from pathlib import Path
import ast,json
R=Path(__file__).resolve().parents[1]
EXPECTED=(R/"VERSION.txt").read_text().strip()

def test_release_sync():
 assert (R/"VERSION.txt").read_text().strip()==EXPECTED
 import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
 assert json.loads((R/"release.json").read_text())["version"]==EXPECTED
 assert f"mesflow-app:{EXPECTED}" in (R/"compose.yml").read_text()

def test_dataset_module_is_guarded_and_prefix_scoped():
 s=(R/"app/mesflow/tutorial_data.py").read_text()
 ast.parse(s)
 assert "MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION" in s
 assert "PREFIX=" in s and "TUT39" in s
 assert "WHERE note LIKE 'TUT39:%'" in s
 assert "WHERE code LIKE 'TUT-%'" in s

def test_dataset_covers_key_exception_and_kiosk_cases():
 s=(R/"app/mesflow/tutorial_data.py").read_text()
 for token in ["OPEN_TOO_LONG","ZERO_QTY_LONG","MISSING_STATION","OVERLAP","INVALID_TIME",
               "OFFLINE_QUEUE","SYNC_CONFLICT","qc_inspections","operation_adjustments","penalty_tickets"]:
  assert token in s

def test_exception_video_demonstrates_workflow():
 s=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
 assert "/api/session-exceptions/workflow" in s
 assert "workflow_status:'IN_PROGRESS'" in s
 assert "workflow_status:'RESOLVED'" in s
 assert "TUT-" in s

def test_common_cases_video_and_publish():
 spec=(R/"tests/e2e/tutorial-detailed.spec.js").read_text()
 runner=(R/"scripts/make-user-guide-video.sh").read_text()
 pub=(R/"scripts/publish-user-guide-videos.sh").read_text()
 assert "commonCases:" in spec
 assert "13_common_cases:commonCases" in runner
 assert "13_common_cases" in pub

def test_seed_not_default():
 s=(R/"scripts/make-user-guide-video.sh").read_text()
 assert 'MESFLOW_TUTORIAL_SEED_DATA:-0' in s
 assert "prepare-tutorial-data.sh" in s
