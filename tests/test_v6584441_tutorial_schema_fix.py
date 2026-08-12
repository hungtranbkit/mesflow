from pathlib import Path
import ast,json
R=Path(__file__).resolve().parents[1]
EXPECTED="65.8.44.41"
def test_release_sync():
 assert (R/"VERSION.txt").read_text().strip()==EXPECTED
 assert EXPECTED in (R/"app/mesflow/__init__.py").read_text()
 assert json.loads((R/"release.json").read_text())["version"]==EXPECTED
 assert f"image: mesflow-app:{EXPECTED}" in (R/"compose.yml").read_text()
def test_no_legacy_plan_qty_in_inserts():
 s=(R/"app/mesflow/tutorial_data.py").read_text(); ast.parse(s)
 assert "template_operations(template_id,part_id,code,name,plan_qty" not in s
 assert "operations(production_order_id,part_id,code,name,plan_qty" not in s
def test_current_status_names():
 s=(R/"app/mesflow/tutorial_data.py").read_text()
 assert "'RUNNING'" not in s and '"RUNNING"' not in s
 assert "IN_PROGRESS" in s
def test_schema_preflight():
 s=(R/"app/mesflow/tutorial_data.py").read_text()
 assert "def _assert_schema(cur):" in s
 assert "information_schema.columns" in s
 assert "Legacy schema detected" in s
def test_0012_is_source_of_truth():
 s=(R/"app/migrations/versions/0012_single_planned_quantity.py").read_text()
 assert "op.drop_column('operations', 'plan_qty')" in s
 assert "op.drop_column('template_operations', 'plan_qty')" in s
def test_preparer_shows_revision():
 assert "alembic current" in (R/"scripts/prepare-tutorial-data.sh").read_text()
