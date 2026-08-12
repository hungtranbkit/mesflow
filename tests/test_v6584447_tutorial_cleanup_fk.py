from pathlib import Path
import json, ast
R=Path(__file__).resolve().parents[1]
E="65.8.44.47"

def test_version_sync():
    assert (R/"VERSION.txt").read_text().strip()==E
    assert E in (R/"app/mesflow/__init__.py").read_text()
    assert json.loads((R/"release.json").read_text())["version"]==E
    assert f"image: mesflow-app:{E}" in (R/"compose.yml").read_text()

def test_tutorial_data_syntax():
    s=(R/"app/mesflow/tutorial_data.py").read_text()
    ast.parse(s)

def test_cleanup_matches_sessions_by_tutorial_operation():
    s=(R/"app/mesflow/tutorial_data.py").read_text()
    block=s[s.index("def _cleanup(cur):"):s.index("def seed()")]
    assert "ws.operation_id IN" in block
    assert "po.code LIKE 'TUT-%'" in block
    assert "DELETE FROM work_sessions" in block

def test_sessions_deleted_before_operations():
    s=(R/"app/mesflow/tutorial_data.py").read_text()
    block=s[s.index("def _cleanup(cur):"):s.index("def seed()")]
    assert block.index("DELETE FROM work_sessions") < block.index("DELETE FROM operations WHERE production_order_id")

def test_restrict_children_deleted_before_operations():
    s=(R/"app/mesflow/tutorial_data.py").read_text()
    block=s[s.index("def _cleanup(cur):"):s.index("def seed()")]
    op_pos=block.index("DELETE FROM operations WHERE production_order_id")
    for table in ["qc_inspections","operation_adjustments","penalty_tickets"]:
        assert block.index(f"DELETE FROM {table}") < op_pos
