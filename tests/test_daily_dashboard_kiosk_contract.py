"""Contract for "Kiosk điều hành" — the control-room display opened from
Dashboard theo ngày.

NEGATIVE PROOF (what makes this a real regression test, not decoration):
each test below names the single thing whose removal turns it red.

  * test_kiosk_route_is_registered_and_reachable
        -> red if the page module, its <script> tag, or its registerPage()
           call is dropped: the route becomes unreachable and deep-linking
           ?page=daily-dashboard-kiosk renders a blank screen.
  * test_dashboard_exposes_the_open_button_carrying_the_date
        -> red if the "Mở màn hình lớn" button or its date-carrying handler
           is removed from Dashboard theo ngày.
  * test_kiosk_layout_css_exists
        -> red if the kiosk's CSS block (dark full-bleed shell, KPI grid,
           two-column body, 1366 breakpoint) is deleted, which is exactly
           the failure mode "it still renders, but it is not a TV layout
           any more and it overflows".
  * test_kiosk_adds_no_new_endpoint
        -> red if someone bolts a new aggregate API onto this view instead
           of reusing the shipped ones.
  * test_kiosk_is_not_a_device_kiosk
        -> red if this control-room display starts pulling in the
           shop-floor badge-scan kiosk runtime.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PAGE=ROOT/'app/mesflow/web/static/pages/daily-dashboard-kiosk.js'
APP_JS=ROOT/'app/mesflow/web/static/app.js'
APP_HTML=ROOT/'app/mesflow/web/templates/app.html'
UI_CSS=ROOT/'app/mesflow/web/static/ui.css'
ROUTES=ROOT/'app/mesflow/web/analytics.py'


def test_kiosk_route_is_registered_and_reachable():
    assert PAGE.exists()
    page=PAGE.read_text(encoding='utf-8')
    html=APP_HTML.read_text(encoding='utf-8')
    app=APP_JS.read_text(encoding='utf-8')
    # Self-registration through the shared hook -- not a monkey-patch of openPage.
    assert "window.registerPage(PAGE_ID,renderDailyDashboardKiosk)" in page
    assert "const PAGE_ID='daily-dashboard-kiosk'" in page
    # Loaded by the shell, and AFTER app.js (which defines window.registerPage).
    assert '/static/pages/daily-dashboard-kiosk.js' in html
    assert html.index('/static/app.js')<html.index('/static/pages/daily-dashboard-kiosk.js')
    # Gated by the same permission as the dashboard it belongs to.
    assert "'daily-dashboard-kiosk':'dashboard.view'" in app
    # date= is read from the URL, validated, and written back so refresh /
    # deep-link / Back / Forward all restore the same day.
    assert "const date=validDate(query.get('date'))?query.get('date'):hcmToday()" in page
    assert "AppNav.setQuery({date})" in page
    # body[data-page] is what app.js's popstate handler compares against; the
    # kiosk must claim it or Back/Forward stops working for this screen.
    assert "document.body.dataset.page=PAGE_ID" in page


def test_dashboard_exposes_the_open_button_carrying_the_date():
    app=APP_JS.read_text(encoding='utf-8')
    assert 'id="dailyOpenKiosk"' in app
    assert 'Mở màn hình lớn' in app
    assert "document.getElementById('dailyOpenKiosk').onclick" in app
    # The selected working day must travel with the click, and exactly one
    # history entry may be pushed (page= and date= together) so a single Back
    # press returns to the dashboard.
    assert "url.searchParams.set('page','daily-dashboard-kiosk')" in app
    assert "url.searchParams.set('date',kioskDate)" in app
    assert "openPage('daily-dashboard-kiosk',null,{historyMode:'none'})" in app


def test_kiosk_layout_css_exists():
    css=UI_CSS.read_text(encoding='utf-8')
    # Scoped dark full-bleed shell: without this the page renders inside the
    # light admin chrome and is unreadable from across a workshop.
    assert 'body[data-page="daily-dashboard-kiosk"]' in css
    assert '.kiosk-display{' in css
    # The three structural blocks the TV layout depends on.
    assert '.kiosk-kpis{display:grid' in css
    assert '.kiosk-body{display:grid' in css
    assert '.kiosk-chart-plot{' in css
    # Operation NAME is the headline, code is the secondary line.
    assert '.kiosk-op b{' in css and '.kiosk-op small{' in css
    # 1366x768 must be an explicit step, not an accident.
    assert '@media(max-width:1500px)' in css


def test_kiosk_adds_no_new_endpoint():
    page=PAGE.read_text(encoding='utf-8')
    routes=ROUTES.read_text(encoding='utf-8')
    # Exactly the endpoints already shipped and already used by other pages.
    assert '/api/dashboard/day?date=' in page
    assert '/api/dashboard/overview' in page
    assert '/api/production-control' in page
    assert "@bp.get('/dashboard/day')" in routes
    assert "@bp.get('/dashboard/overview')" in routes
    assert "@bp.get('/production-control')" in routes
    # No bespoke aggregate route invented for this screen.
    assert 'kiosk-display' not in routes
    assert "@bp.get('/dashboard/kiosk" not in routes


def _code_only(source:str)->str:
    """Strip whole-line // comments.

    The page's own header comment deliberately NAMES the shop-floor kiosk
    modules to explain what this view is not; only executable code may be
    searched for references to them.
    """
    return '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('//'))


def test_kiosk_is_not_a_device_kiosk():
    """Control-room display, not the shop-floor badge-scan terminal."""
    page=_code_only(PAGE.read_text(encoding='utf-8'))
    for forbidden in ('/api/kiosk/','/api/kiosk-v2/','/station/heartbeat','device_uuid','templates/kiosk.html'):
        assert forbidden not in page, forbidden
    # Date is the only filter: ca is metadata, never a query parameter.
    assert 'shift_id=' not in page
    assert '&shift=' not in page


def test_kiosk_does_not_fabricate_an_hourly_plan():
    """No hourly plan exists in the data model -- the view must say so rather
    than draw an invented target line."""
    page=PAGE.read_text(encoding='utf-8')
    assert 'Chưa cấu hình kế hoạch theo giờ' in page
    assert 'Kế hoạch theo giờ: chưa có trong dữ liệu' in page
    # Missing dispatch sources are named explicitly, not silently omitted.
    assert 'Thiếu vật tư và phút dừng theo lý do: chưa có nguồn dữ liệu' in page


def test_kiosk_keeps_last_good_data_on_api_failure():
    """A control-room display must never go blank on a transient API error."""
    page=PAGE.read_text(encoding='utf-8')
    assert "setLive('stale'" in page
    assert 'Mất kết nối' in page
    # The paint* helpers are only called on the success path, so a failed poll
    # leaves the previous screen untouched.
    assert 'if(!alive())return;' in page
