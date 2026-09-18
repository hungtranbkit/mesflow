"""Regression contract for Dashboard mobile tab typography and overflow."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / 'app/mesflow/web/static/app.js'
UI_CSS = ROOT / 'app/mesflow/web/static/ui.css'


def test_session_timeline_scroll_is_scoped_to_the_timeline_region():
    app = APP_JS.read_text(encoding='utf-8')
    assert 'class="employee-day-track-scroll"' in app
    assert 'role="region"' in app
    assert 'aria-label="Timeline phiên làm việc trong ngày"' in app

    css = UI_CSS.read_text(encoding='utf-8')
    assert '.employee-day-track-scroll{min-width:0;max-width:100%;overflow-x:auto' in css
    hotfix = css.split('/* DASHBOARD-MOBILE-TAB-FONT-20260918', 1)[1]
    mobile = hotfix.split('@media(max-width:820px){', 1)[1]
    row = mobile.split('body[data-page="dashboard"] .employee-day-row{', 1)[1].split('}', 1)[0]
    assert 'overflow:visible' in row
    assert 'max-width:100%' in row
    assert 'body[data-page="dashboard"] .employee-day-track{min-width:720px}' in mobile


def test_dashboard_tabs_share_typography_tokens_and_disable_only_autosizing():
    css = UI_CSS.read_text(encoding='utf-8')
    pane = css.split('body[data-page="dashboard"] .dashboard-tab-pane{', 1)[1].split('}', 1)[0]
    assert '--dashboard-card-title:13px' in pane
    assert '--dashboard-body:14px' in pane
    assert '--dashboard-meta:11px' in pane
    assert '-webkit-text-size-adjust:100%' in pane
    assert 'text-size-adjust:100%' in pane
    assert 'none' not in pane, '100% keeps browser/user zoom; none would disable text adjustment'

    hotfix = css.split('/* DASHBOARD-MOBILE-TAB-FONT-20260918', 1)[1]
    mobile = hotfix.split('@media(max-width:820px){', 1)[1]
    mobile_pane = mobile.split('body[data-page="dashboard"] .dashboard-tab-pane{', 1)[1].split('}', 1)[0]
    assert '--dashboard-card-title:16px' in mobile_pane
    assert '--dashboard-meta:12px' in mobile_pane
    assert ':is(.op-card-identity,.emp-op-item)' in hotfix
    assert 'font-size:var(--dashboard-card-title)' in hotfix
    assert 'font-size:var(--dashboard-body)' in hotfix
    assert 'font-size:var(--dashboard-meta)' in hotfix
    assert 'body[data-page="dashboard"] .op-card-head{margin-bottom:0}' in hotfix
    for forbidden in ('transform:scale', 'zoom:', 'overflow:hidden'):
        assert forbidden not in mobile, f'hotfix must not mask the defect with {forbidden}'
