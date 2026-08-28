from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADMIN_PASSWORD = "Admin@123456"


def test_non_production_compose_profiles_use_default_admin_password():
    for compose_file in ("compose.sandbox.yml", "compose.projectflow-local.yml"):
        compose = (ROOT / compose_file).read_text(encoding="utf-8")
        assert f"MESFLOW_ADMIN_PASSWORD: {DEFAULT_ADMIN_PASSWORD}" in compose


def test_production_compose_still_requires_an_explicit_admin_password():
    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert "MESFLOW_ADMIN_PASSWORD: ${MESFLOW_ADMIN_PASSWORD:?MESFLOW_ADMIN_PASSWORD is required}" in compose
    assert f"MESFLOW_ADMIN_PASSWORD: {DEFAULT_ADMIN_PASSWORD}" not in compose
