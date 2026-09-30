"""Tổng quan active-only hotfix (2026-09-30).

The Overview shows only employees with an OPEN session on each Operation.
A finished (or AUTO_CLOSED) worker drops out on the next refresh; the
others on the same Operation stay; an Operation with nobody active has no
"Hôm nay" block at all. Display only -- the backend lists are unchanged.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app/mesflow/web/static/core/overview-active.js"
PAGE = ROOT / "app/mesflow/web/static/pages/overview.js"
APP_HTML = ROOT / "app/mesflow/web/templates/app.html"
REPO = ROOT / "app/mesflow/db/repositories/analytics.py"

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is required for the overview projection tests")


def _run(expr: str):
    script = (
        f"const A=require({json.dumps(str(MODULE))});"
        f"const out=(()=>{{{expr}}})();process.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run([NODE, "-e", script], check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


W = lambda i, name, **extra: {"employee_id": i, "employee_no": f"NV{i:03d}", "name": name, "session_count": 1,
                              "started_at": f"2026-09-30T0{i}:00:00Z", **extra}


@needs_node
def test_two_workers_one_finishes_only_the_finished_one_disappears():
    before = {"active_worker_list": [W(1, "An"), W(2, "Bình")], "today_worker_list": []}
    # Next refresh: Bình's session closed -> backend moves her to today_worker_list.
    after = {"active_worker_list": [W(1, "An")], "today_worker_list": [W(2, "Bình", last_ended_at="2026-09-30T09:00:00Z")]}
    got = _run(
        f"return {{before:A.activeWorkers({json.dumps(before)}).map(w=>w.name),"
        f"after:A.activeWorkers({json.dumps(after)}).map(w=>w.name),"
        f"show:A.hasActiveWork({json.dumps(after)})}};"
    )
    assert got == {"before": ["An", "Bình"], "after": ["An"], "show": True}


@needs_node
def test_last_worker_finishes_the_whole_block_is_hidden():
    rows = [
        {"active_worker_list": [], "today_worker_list": [W(1, "An", last_ended_at="2026-09-30T09:00:00Z")],
         "today": {"session_count": 3}},
        {"active_worker_list": None, "today": None},
        {},
    ]
    got = _run(f"return {json.dumps(rows)}.map(r=>[A.hasActiveWork(r),A.activeWorkers(r).length]);")
    assert got == [[False, 0], [False, 0], [False, 0]]


@needs_node
def test_closed_or_auto_closed_entries_never_count_as_active():
    row = {"active_worker_list": [
        W(1, "An"),
        W(2, "Bình", status="CLOSED", close_reason="AUTO_SHIFT_END"),
        W(3, "Chi", ended_at="2026-09-30T10:00:00Z"),
        W(4, "Dũng", session_count=0),
        W(5, "Em", status="open"),
        None,
    ]}
    got = _run(f"return A.activeWorkers({json.dumps(row)}).map(w=>w.name);")
    assert got == ["An", "Em"]


@needs_node
def test_multi_session_worker_is_one_entry_with_earliest_start():
    row = {"active_worker_list": [
        W(1, "An", started_at="2026-09-30T08:30:00Z", session_count=1),
        W(2, "Bình"),
        W(1, "An", started_at="2026-09-30T07:15:00Z", session_count=2),
    ]}
    got = _run(f"return A.activeWorkers({json.dumps(row)});")
    assert [w["name"] for w in got] == ["An", "Bình"]
    assert got[0]["session_count"] == 3 and got[0]["started_at"] == "2026-09-30T07:15:00Z"


@needs_node
def test_projection_does_not_mutate_the_api_row():
    row = {"active_worker_list": [W(1, "An"), W(1, "An", session_count=1)]}
    got = _run(f"const r={json.dumps(row)};A.activeWorkers(r);return r;")
    assert got == row


def test_page_uses_the_projection_and_draws_no_placeholder():
    page = PAGE.read_text(encoding="utf-8")
    block = page.split("const todayMetrics=", 1)[1].split("const poToday=", 1)[0]
    assert "const active=activeWorkers(x);if(!active.length)return '';" in block
    assert "is-empty" not in block and "Chưa có phiên làm việc</span>" not in block
    workers = page.split("const workerRows=workers=>", 1)[1].split("const dur=", 1)[0]
    assert "is-active" in workers and "is-finished" not in workers and "Đã kết thúc" not in workers
    # Active employee count, not the day's total, next to the names.
    assert "todayM('employees','',N(active.length),'Nhân viên đang làm Operation này','','NV')" in block
    # Module loaded before the page that uses it; 60s refresh untouched.
    html = APP_HTML.read_text(encoding="utf-8")
    assert html.index("/static/core/overview-active.js") < html.index("/static/pages/overview.js")
    assert "},60000);" in page


def test_backend_lists_are_unchanged():
    repo = REPO.read_text(encoding="utf-8")
    active = repo.split("def active_workers_by_operation", 1)[1].split("def today_activity_by_operation", 1)[0]
    assert "WHERE ws.status='OPEN'" in active
    assert "row['today_worker_list']=history" in repo  # still produced for other consumers
