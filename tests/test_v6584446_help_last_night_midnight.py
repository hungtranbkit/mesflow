from pathlib import Path
import json
from datetime import date
R=Path(__file__).resolve().parents[1]

def test_version():
    version=(R/"VERSION.txt").read_text().strip()
    assert json.loads((R/"release.json").read_text())["version"]==version

def test_tutorial_is_last_menu_item():
    s=(R/"app/mesflow/web/static/app.js").read_text()
    block=s[s.index("const menu=["):s.index("const nav=")]
    # Label was later shortened site-wide from "Hướng dẫn sử dụng" to
    # "Hướng dẫn" -- the "tutorial is the last item" invariant is unchanged.
    assert block.rfind("Hướng dẫn") > block.rfind("Hệ thống")

def test_night_default_ends_at_midnight_not_cross_day():
    s=(R/"app/mesflow/core/working_calendar.py").read_text()
    assert '"anchor_start":"18:00","anchor_end":"00:00","cross_midnight":False,"target_minutes":300' in s
    assert '"end_minute":1440' in s

def test_ui_midnight_is_end_of_day():
    s=(R/"app/mesflow/web/static/app.js").read_text()
    assert "Number(m)===1440?'24:00'" in s
    assert "24:00 (kết thúc trong ngày)" in s
    assert "isEndOfDay" in s

def test_migration_only_targets_legacy_default():
    s=(R/"app/migrations/versions/0026_night_shift_same_day_midnight.py").read_text()
    assert 'down_revision = "0025_rbac_permissions"' in s
    assert "anchor_start='18:00'::time" in s
    assert "anchor_end='03:00'::time" in s
    assert "end_minute=1620" in s
    assert "end_minute=1440" in s
