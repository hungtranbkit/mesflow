from pathlib import Path

# RETIRED test_running_card_declared_before_use (Codex audit Blocker 4,
# category STALE API CONTRACT, evidence below): the dashboard this test
# targeted has since been substantially redesigned. There is no
# `runningCard` function in app.js's current renderDashboard() at all --
# per-state operation rows (RUNNING/HAS_DEFECT/UPDATED/STARTED) are now
# rendered by ONE generic `row(x)` function keyed off `x.day_state` via a
# `stateLabel` map and a CSS state class, not a dedicated per-state "card"
# function. This was a real, deliberate architecture change (confirmed by
# reading the current renderDashboard() source in full), not a bug or an
# accidental removal -- there is nothing named "runningCard" left to check
# a declaration-before-use order for. The property this test actually
# cared about -- a RUNNING operation is rendered with a distinct, findable
# state -- is covered by the assertion below against the real current code.


def test_running_state_is_rendered_and_labeled():
    text = Path("app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    assert "RUNNING:'Đang chạy'" in text
    assert "x.day_state" in text
