from pathlib import Path


def test_action_logs_noise_literals_are_escaped_for_psycopg_params():
    src = Path("app/mesflow/web/action_logging.py").read_text(encoding="utf-8")
    list_route = src.split("def list_logs():", 1)[1].split("@bp.get('/action-logs/stats')", 1)[0]
    assert "ILIKE '%%.php%%'" in list_route
    assert "ILIKE '%%/vendor/phpunit/%%'" in list_route
    assert "ILIKE '%.php%'" not in list_route
    assert "LIMIT %s" in list_route
