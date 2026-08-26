import pytest

pytestmark = pytest.mark.postgres


def test_health_ready_and_version(api):
    health = api.get('http://mesflow-test-api:8080/api/system/health', timeout=10)
    assert health.status_code == 200, health.text
    body = health.json()
    assert body['ok'] is True
    assert body['database_backend'] == 'postgresql'

    ready = api.get('http://mesflow-test-api:8080/api/system/ready', timeout=10)
    assert ready.status_code == 200, ready.text
    assert ready.json()['migration_head'], ready.json()


def test_system_ready_reports_business_host_and_database_timezone(api):
    """Codex audit Blocker 12: /api/system/ready must explicitly expose the
    business timezone MESFlow's own calendar logic uses (always
    Asia/Ho_Chi_Minh, regardless of what the host or container OS locale
    happens to be), separately from the informational host/database
    timezone fields."""
    ready = api.get('http://mesflow-test-api:8080/api/system/ready', timeout=10)
    assert ready.status_code == 200, ready.text
    tz = ready.json()['timezone']
    assert tz['business_timezone'] == 'Asia/Ho_Chi_Minh'
    assert tz['host_timezone']
    assert tz['database_timezone']


def test_unknown_route_is_real_404_without_internal_error(api):
    response = api.get('http://mesflow-test-api:8080/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php', timeout=10)
    assert response.status_code == 404
    body = response.json()
    assert body['error'] == 'NOT_FOUND'
    assert 'traceback' not in body


def test_dashboard_requires_shift_id(api):
    response = api.get('http://mesflow-test-api:8080/api/dashboard/shift?shift_date=2026-08-06', timeout=10)
    assert response.status_code == 400
