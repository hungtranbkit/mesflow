from pathlib import Path

# RETIRED test_running_card_declared_before_use (Codex audit Blocker 4,
# category STALE API CONTRACT, evidence below): the dashboard this test
# targeted has since been substantially redesigned. There is no
# `runningCard` function in app.js's current renderDashboard() at all --
# per-state operation rows are now rendered by ONE generic `row(x)`
# function keyed off `x.day_state` via a `stateLabel` map and a CSS state
# class, not a dedicated per-state "card" function. This was a real,
# deliberate architecture change (confirmed by reading the current
# renderDashboard() source in full), not a bug or an accidental removal
# -- there is nothing named "runningCard" left to check a
# declaration-before-use order for. The property this test actually
# cared about -- a RUNNING operation is rendered with a distinct,
# findable state -- is covered by the assertion below against the real
# current code.
#
# day_state values were later changed again (MESFlow Production/Operation
# overview UI fix): the old HAS_DEFECT state incorrectly mapped
# "defect_qty > 0" to a red "Có lỗi" warning even though NG/defect
# quantity is normal production data, not an error condition. HAS_DEFECT
# was removed; day_state now describes operational/session state only
# (RUNNING/NEEDS_REVIEW/UPDATED/IDLE), where NEEDS_REVIEW is reserved for
# a real actionable exception (an auto-closed session whose quantity was
# never confirmed by a human), not merely NG > 0.


def test_running_state_is_rendered_and_labeled():
    text = Path("app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    assert "RUNNING:'Đang chạy'" in text
    assert "x.day_state" in text


def test_defect_quantity_no_longer_drives_a_derived_error_state():
    text = Path("app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    # The old bug: day_defect_qty > 0 alone mapped to state HAS_DEFECT,
    # rendered as a red "Có lỗi" badge. Neither should exist anymore.
    # (Note: "Có lỗi" also appears elsewhere in app.js as a genuine kiosk
    # hardware-error status label -- unrelated to defect quantity and out
    # of scope -- so this checks the day_state label maps specifically,
    # not every occurrence of the phrase in the file.)
    assert "HAS_DEFECT" not in text
    assert ":'Có lỗi'" not in text
    # NEEDS_REVIEW is the real actionable-exception state that replaced it,
    # and it must still be labeled and rendered.
    assert "NEEDS_REVIEW:'Cần xử lý ngoại lệ'" in text
    assert "daily-state" in text


def test_ng_quantity_is_still_shown_plainly_not_as_an_error():
    text = Path("app/mesflow/web/static/app.js").read_text(encoding="utf-8")
    # Defect/NG quantity must remain visible -- just relabeled from the
    # misleading "Lỗi" to "NG", with no error styling implied by the label.
    assert "NG ${Number(x.day_defect_qty||0).toLocaleString('vi-VN')}" in text
