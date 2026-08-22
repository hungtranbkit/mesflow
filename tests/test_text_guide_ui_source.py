"""Hướng dẫn bằng chữ -- UI wiring contract.

The text guide (pages/text-guide.js) is deliberately additive: it never
edits app.js, only reassigns two globals app.js already declares
(renderTutorials, attachGuideTabs) after the script loads, the same
monkey-patch technique pages/production-trace.js already uses for openPage.
These tests lock that contract down so a future edit doesn't accidentally
start editing app.js's existing video-tutorial code instead.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js():
    return (ROOT / 'app/mesflow/web/static/pages/text-guide.js').read_text(encoding='utf-8')


def _app_js():
    return (ROOT / 'app/mesflow/web/static/app.js').read_text(encoding='utf-8')


def test_app_js_video_tutorial_system_is_untouched():
    """The existing video system must stay byte-for-byte in app.js -- this
    feature only adds a new file, per the task's 'không xóa/chỉnh video
    tutorial đang có' requirement."""
    js = _app_js()
    assert 'async function renderTutorials()' in js
    assert 'async function renderEspKioskTutorial()' in js
    assert 'function attachGuideTabs(active){' in js
    # The KIMEX/ESP inner tab bar body app.js declares is what text-guide.js
    # captures and then overrides at runtime -- it must still exist as-is.
    assert "data-tab=\"mesflow\">KIMEX" in js
    assert "data-tab=\"esp\">ESP Kiosk" in js
    # Regression guard for the renderEspKioskTutorial<->renderSimple
    # adjacency an existing legacy test (test_v6584454_esp_kiosk_tutorial.py)
    # relies on -- new code must never be inserted between them.
    start = js.index('async function renderEspKioskTutorial')
    end = js.index('async function renderSimple')
    assert 'x.filename' not in js[start:end]


def test_app_html_loads_text_guide_after_app_js():
    html = (ROOT / 'app/mesflow/web/templates/app.html').read_text(encoding='utf-8')
    app_pos = html.index('src="/static/app.js')
    guide_pos = html.index('src="/static/pages/text-guide.js')
    assert guide_pos > app_pos


def test_text_guide_repoints_the_right_globals_without_editing_app_js():
    js = _js()
    # Captures the ORIGINAL renderTutorials (KIMEX video body) before
    # repointing the name -- must happen before any reassignment.
    capture_pos = js.index('const renderVideoGuideKimex = renderTutorials;')
    reassign_pos = js.index('renderTutorials = function')
    assert capture_pos < reassign_pos
    # New default entry defaults to the text guide, only going to video on
    # an explicit ?tab=video deep link.
    assert "renderTextGuide()" in js[reassign_pos:]
    # attachGuideTabs is fully overridden (not merely wrapped), retargeted
    # at renderVideoGuideKimex so the inner KIMEX button never calls back
    # into the now-repointed renderTutorials.
    assert 'attachGuideTabs = function' in js
    assert 'renderVideoGuideKimex()' in js
    # Every attachGuideTabs call (KIMEX and ESP tabs alike) also gets the
    # new outer Text/Video wrap.
    assert "attachTopGuideTabs('video')" in js


def test_text_guide_renders_from_the_json_data_file_only():
    js = _js()
    assert "/static/guides/user-guide.vi.json" in js
    # No inline HTML dump of guide content -- content always comes from the
    # fetched JSON via guideBlockHtml(), matching the "tách nội dung ra file
    # riêng" requirement.
    assert 'function guideBlockHtml(block)' in js


def test_text_tab_is_default_and_search_toc_wired():
    js = _js()
    assert 'id="guideSearch"' in js
    assert 'id="guideToc"' in js
    assert 'search.oninput = draw' in js
    assert 'gotoSection(a.dataset.goto)' in js


def test_guide_css_present_and_responsive_breakpoint_defined():
    css = (ROOT / 'app/mesflow/web/static/ui.css').read_text(encoding='utf-8')
    assert '.text-guide-layout{' in css
    assert '.guide-card{' in css
    assert '@media(max-width:900px){' in css
    section = css[css.index('.text-guide-shell{'):]
    assert '.text-guide-layout{display:block}' in section
