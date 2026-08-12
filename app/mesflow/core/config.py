from dataclasses import dataclass
import os


def _bool(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get("DATABASE_URL") or os.environ.get("WORKSHOP_DATABASE_URL", "")
    secret_key: str = os.environ.get("MESFLOW_SECRET_KEY") or os.environ.get("WORKSHOP_SECRET_KEY", "dev-only")
    admin_username: str = os.environ.get("MESFLOW_ADMIN_USERNAME", "admin")
    admin_password: str = os.environ.get("MESFLOW_ADMIN_PASSWORD", "")
    cookie_secure: bool = _bool("WORKSHOP_COOKIE_SECURE")
    environment: str = os.environ.get("MESFLOW_ENV", "production")
    deployment_id: str = os.environ.get("MESFLOW_DEPLOYMENT_ID", "")
    trusted_proxy_count: int = int(os.environ.get("MESFLOW_TRUSTED_PROXY_COUNT", "1"))
    max_content_length: int = int(os.environ.get("MESFLOW_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))
    timezone_name: str = os.environ.get("MESFLOW_TIMEZONE", "Asia/Ho_Chi_Minh")
    test_auto_login: bool = _bool("MESFLOW_TEST_AUTO_LOGIN", "0")
    test_auto_login_username: str = os.environ.get("MESFLOW_TEST_AUTO_LOGIN_USERNAME", "admin")
    local_auto_login: bool = _bool("MESFLOW_LOCAL_AUTO_LOGIN", "0")
    internal_qa_auto_login: bool = _bool("MESFLOW_INTERNAL_QA_AUTO_LOGIN", "0")
    internal_http_session: bool = _bool("MESFLOW_INTERNAL_HTTP_SESSION", "1")
    action_log_enabled: bool = _bool("MESFLOW_ACTION_LOG_ENABLED", "1")
    action_log_get_requests: bool = _bool("MESFLOW_ACTION_LOG_GET_REQUESTS", "0")
    action_log_slow_ms: int = int(os.environ.get("MESFLOW_ACTION_LOG_SLOW_MS", "1500"))
    action_log_body_limit: int = int(os.environ.get("MESFLOW_ACTION_LOG_BODY_LIMIT", "12000"))
    action_log_scanner_noise: bool = _bool("MESFLOW_ACTION_LOG_SCANNER_NOISE", "0")
    log_retention_enabled: bool = _bool("MESFLOW_LOG_RETENTION_ENABLED", "1")
    log_retention_batch_size: int = int(os.environ.get("MESFLOW_LOG_RETENTION_BATCH_SIZE", "2000"))
    log_retention_success_days: int = int(os.environ.get("MESFLOW_LOG_RETENTION_SUCCESS_DAYS", "30"))
    log_retention_slow_days: int = int(os.environ.get("MESFLOW_LOG_RETENTION_SLOW_DAYS", "90"))
    log_retention_resolved_error_days: int = int(os.environ.get("MESFLOW_LOG_RETENTION_RESOLVED_ERROR_DAYS", "180"))
    log_retention_unresolved_error_days: int = int(os.environ.get("MESFLOW_LOG_RETENTION_UNRESOLVED_ERROR_DAYS", "365"))
    log_retention_security_days: int = int(os.environ.get("MESFLOW_LOG_RETENTION_SECURITY_DAYS", "365"))
    log_retention_error_resolved_days: int = int(os.environ.get("MESFLOW_LOG_RETENTION_ERROR_TRACE_RESOLVED_DAYS", "180"))
    log_retention_error_unresolved_days: int = int(os.environ.get("MESFLOW_LOG_RETENTION_ERROR_TRACE_UNRESOLVED_DAYS", "365"))


settings = Settings()
if not settings.database_url.startswith("postgresql://"):
    raise RuntimeError("DATABASE_URL must be PostgreSQL; SQLite is not supported in MESFlow v65")
if settings.environment == "production" and settings.secret_key in {"", "dev-only", "CHANGE_ME"}:
    raise RuntimeError("MESFLOW_SECRET_KEY must be configured for production")
