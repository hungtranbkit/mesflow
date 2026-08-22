"""Kiosk trình chiếu năng suất nhân viên -- completed-session-only contract
at the JS/CSS source level (2026-08-22 revision). No Docker needed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js():
    return (ROOT / 'app/mesflow/web/static/wallboard-employee-productivity.js').read_text(encoding='utf-8')


def _css():
    return (ROOT / 'app/mesflow/web/static/wallboard.css').read_text(encoding='utf-8')


def test_no_realtime_worker_state_anywhere_in_wallboard_js():
    js = _js()
    for forbidden in ('running_sessions', 'active_employee_count', 'x.running', 'wb-running-dot'):
        assert forbidden not in js, f'{forbidden!r} must not appear -- Kiosk is completed-session-only (Section 7)'


def test_running_dot_css_removed():
    assert 'wb-running-dot' not in _css()


def test_kpis_match_the_four_required_completed_session_cards():
    js = _js()
    for label in ('Năng suất trung bình', 'Nhân viên có dữ liệu', 'Session đã kết thúc', 'Tổng sản lượng đạt'):
        assert label in js


def test_sample_size_still_shown_next_to_percent():
    """Not a realtime concern -- still required so a lone 100%/1-session
    score doesn't read the same as a well-sampled one."""
    js = _js()
    assert 'sampleNote' in js
    assert 'Không đủ dữ liệu' in js
