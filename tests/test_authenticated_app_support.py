"""The public support widget is available inside the authenticated app shell."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_authenticated_app_shell_includes_shared_support_widget_assets():
    app = (ROOT / 'app/mesflow/web/templates/app.html').read_text(encoding='utf-8')
    assert "{% include 'support_widget.html' %}" in app
    assert '/static/support-widget.css' in app
    assert '/static/support-widget.js' in app
    assert 'id="support-launch"' not in app  # markup stays in the shared partial


def test_shared_widget_sends_only_approved_topics_without_session_credentials():
    script = (ROOT / 'app/mesflow/web/static/support-widget.js').read_text(encoding='utf-8')
    assert "fetch('/support/chat'" in script
    assert "credentials:'omit'" in script
    assert 'JSON.stringify({topics:[reply.id]})' in script
    for forbidden in ('document.cookie', 'localStorage', 'sessionStorage', 'innerHTML', 'sendBeacon'):
        assert forbidden not in script


def test_public_landing_reuses_the_same_support_widget():
    landing = (ROOT / 'app/mesflow/web/templates/welcome.html').read_text(encoding='utf-8')
    assert "{% include 'support_widget.html' %}" in landing
    assert '/static/support-widget.js' in landing
    assert '/static/support-widget.css' in landing

