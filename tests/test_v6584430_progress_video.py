from pathlib import Path
import json, ast
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/"VERSION.txt").read_text().strip()

def test_release_sync():
    assert (ROOT/"VERSION.txt").read_text().strip()==EXPECTED
    import mesflow as _mesflow_runtime; assert _mesflow_runtime.__version__==EXPECTED  # __init__.py now reads VERSION.txt at import time, not a hardcoded literal
    assert json.loads((ROOT/"release.json").read_text())["version"]==EXPECTED
    assert f"mesflow-app:{EXPECTED}" in (ROOT/"compose.yml").read_text()

def test_time_and_product_are_visually_distinct():
    js=(ROOT/"app"/"mesflow"/"web"/"static"/"app.js").read_text()
    css=(ROOT/"app"/"mesflow"/"web"/"static"/"ui.css").read_text()
    assert "op-time-timeline" in js
    assert "Tiến độ thời gian" in js
    assert "Tiến độ sản phẩm" in js
    assert "op-progress-kind time" in js
    assert "op-progress-kind product" in js
    assert "height:4px!important" in css
    assert "height:10px!important" in css

def test_tutorial_helpers_packaged():
    assert (ROOT/"scripts"/"make-user-guide-video.ps1").is_file()
    assert (ROOT/"scripts"/"make-user-guide-video.sh").is_file()
    assert (ROOT/"USER_GUIDE_VIDEO.md").is_file()
    spec=(ROOT/"tests"/"e2e"/"tutorial-video.spec.js").read_text()
    assert "Phân biệt hai loại tiến độ" in spec
