from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
VERSION = "65.8.44.56"


def test_version_declarations_are_synchronized():
    assert (ROOT / "VERSION.txt").read_text().strip() == VERSION
    assert VERSION in (ROOT / "app/mesflow/__init__.py").read_text()
    assert json.loads((ROOT / "release.json").read_text())["version"] == VERSION
    assert f"mesflow-app:{VERSION}" in (ROOT / "compose.yml").read_text()


def test_exception_source_uses_existing_session_trace_fields():
    source = (ROOT / "app/mesflow/db/repositories/analytics.py").read_text()
    block = source[source.index("def session_exceptions"):source.index("def update_session_exception_reviews")]
    assert "ws.start_request_id" in block
    assert "QA-REAL-START-%" in block and "QA-RUN-%" in block
    assert "TUTORIAL_DEMO" in block and "QA_TEST" in block
    assert "source_trace_id" in block


def test_exception_ui_displays_and_filters_evidence_backed_source():
    source = (ROOT / "app/mesflow/web/static/pages/session-exceptions.js").read_text()
    assert 'id="seDataSource"' in source
    assert "Nguồn dữ liệu" in source
    assert "QA Test" in source and "Tutorial/Demo" in source and "Không xác định" in source
    assert "x.source_trace_id" in source
