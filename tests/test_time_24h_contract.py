from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/mesflow/web/static"

def test_all_time_formatters_force_24h():
    pat = re.compile(r"Intl\.DateTimeFormat\(([^,]+),\{([^{}]*)\}\)")
    bad = []
    for p in STATIC.rglob("*.js"):
        if "vendor" in p.parts:
            continue
        for m in pat.finditer(p.read_text()):
            opts = m.group(2).replace(" ", "")
            if ("hour:" in opts or "timeStyle:" in opts) and "hour12:false" not in opts:
                bad.append(str(p.relative_to(ROOT)))
    assert not bad, bad

def test_work_calendar_uses_explicit_24h_inputs():
    s = (STATIC / "app.js").read_text()
    assert 'type="time"' not in s
    assert s.count('class="time-24h-input"') == 4
    assert 'pattern="(?:[01][0-9]|2[0-3]):[0-5][0-9]"' in s
    assert "Không dùng AM/PM" in s

def test_material_flow_datetime_is_24h():
    s = (STATIC / "pages/material-flow.js").read_text()
    assert "new Date(v).toLocaleString('vi-VN',{hour12:false})" in s
