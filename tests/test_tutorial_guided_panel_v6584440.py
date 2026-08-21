from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "tests/e2e/tutorial-detailed.spec.js").read_text(encoding="utf-8")


def test_tutorial_uses_horizontal_floating_card_not_sidebar():
    assert "#__tutorialPanel{position:fixed" in SPEC
    assert "width:min(62vw,760px)" in SPEC
    assert "padding-left:372px" not in SPEC
    assert "dataset.position=chosen.name" in SPEC


def test_tutorial_panel_has_required_step_detail():
    for text in ("Bước ${stepNumber}", "Áp dụng", "explanation", "expected"):
        assert text in SPEC


def test_tutorial_has_spotlight_without_sidebar_connector():
    assert ".__tutorialFocus" in SPEC
    assert "rgba(7,18,27,.32)" in SPEC
    assert "@keyframes __tutorialPulse" in SPEC
    assert "#__tutorialConnector" not in SPEC


def test_tutorial_uses_central_pacing_and_vietnamese_voice_contract():
    assert "tutorial/tutorial.config.json" in SPEC
    assert "tutorial/terminology.json" in SPEC
    for key in ("pause_before_step_ms", "pause_after_step_ms", "pause_after_click_ms", "pause_after_navigation_ms", "typing_delay_ms"):
        assert key in (ROOT / "tutorial/tutorial.config.json").read_text(encoding="utf-8")


def test_tutorial_failure_writes_copyable_bug_report():
    for field in ("step_id", "action", "selector", "screenshot_path", "exception", "recent_log"):
        assert field in SPEC
    assert "TUTORIAL_BUG_REPORT" in SPEC


def test_dashboard_explains_each_requested_kpi_separately():
    assert "#dailyKpis .daily-kpi:nth-child(1)" in SPEC
    assert "#dailyKpis .daily-kpi:nth-child(2)" in SPEC
    assert "#dailyKpis .daily-kpi:nth-child(3)" in SPEC
    assert "#opTimeProgress .op-time-row:not(.head) .op-dual-progress" in SPEC
    for title in ("Nhân viên có hoạt động", "Đang làm việc", "Sản lượng đạt", "Tiến độ theo công đoạn"):
        assert title in SPEC
