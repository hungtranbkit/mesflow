"""Authenticated support shares the fast public helper and controller."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_authenticated_app_shell_includes_shared_support_widget_assets():
    app = (ROOT / 'app/mesflow/web/templates/app.html').read_text(encoding='utf-8')
    assert "{% include 'support_widget.html' %}" in app
    assert '/static/support-widget.css' in app
    assert app.index('/support/assistant.js') < app.index('/static/support-widget.js')
    partial = (ROOT / 'app/mesflow/web/templates/support_widget.html').read_text()
    assert 'support-facts' not in partial
    assert 'support-optin' in partial


def test_app_controller_is_shared_and_has_no_direct_network_requests():
    script = (ROOT / 'app/mesflow/web/static/support-widget.js').read_text()
    assert script == (ROOT / 'services/public-support/widget.js').read_text()
    assert 'window.MESFlowSupport' in script
    assert 'assistant.deeper(plan,signal)' in script
    for forbidden in ('fetch(', 'document.cookie', 'localStorage', 'sessionStorage', 'innerHTML', 'sendBeacon'):
        assert forbidden not in script


def test_shared_helper_omits_credentials_and_sends_only_opted_in_plan():
    script = (ROOT / 'services/public-support/assistant.js').read_text()
    assert "credentials:'omit'" in script
    assert 'body:JSON.stringify(plan)' in script
