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


# --- Card grid / no progress bar (2026-08-23 revision) ---------------------

def test_no_progress_bar_markup_or_css():
    js, css = _js(), _css()
    for forbidden in ('wb-row-bar', 'wb-bar-track', 'barWidth'):
        assert forbidden not in js and forbidden not in css, f'{forbidden!r} must not appear -- no horizontal progress bar'


def test_card_shows_rank_name_code_pct_sessions_worked_time_band():
    js = _js()
    assert 'wb-card-rank' in js
    assert 'wb-card-name' in js
    assert 'wb-card-pct' in js
    assert 'wb-card-band' in js
    assert 'x.employee_code' in js
    assert 'dur(x.worked_seconds)' in js


def test_grid_uses_css_variable_for_column_count():
    css = _css()
    assert '--productivity-columns' in css
    assert 'repeat(var(--productivity-columns' in css
    assert 'transform' not in css  # no transform:scale anywhere in this file


def test_columns_computed_in_js_not_hardcoded():
    js = _js()
    assert 'computeProductivityColumns' in js
    assert 'PRODUCTIVITY_MIN_CARD_WIDTH' in js


# --- Configurable settings wired into the wallboard (2026-08-23) ----------

def test_wallboard_reads_display_settings_from_config():
    js = _js()
    for key in ('employees_per_page', 'auto_page_flip', 'auto_page_flip_seconds'):
        assert key in js, f'{key!r} must be read from published/preview config'


def test_manual_prev_next_controls_present():
    js = _js()
    assert 'wbPrev' in js and 'wbNext' in js
    assert 'startPaging()' in js  # manual nav must reset the auto-flip timer


def test_pauses_on_hidden_document_and_user_interaction():
    js = _js()
    assert 'document.hidden' in js
    assert 'state.paused' in js
