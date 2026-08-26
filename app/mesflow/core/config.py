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
    # Human/operator-facing label only (e.g. "DEV", "PRODUCTION_TEST") --
    # distinct from `environment`/MESFLOW_ENV, which code gates key off of.
    # Never infer one from the other: renaming this must never change
    # MESFLOW_ENV-gated behavior (see kiosk_v2.py's _TIMING_ENABLED).
    server_role: str = os.environ.get("SERVER_ROLE", "")
    # Baked into the image at build time (Dockerfile ARG GIT_COMMIT), not a
    # runtime env var -- travels with the image regardless of which target
    # deploys it, so a deploy's health check can confirm the exact commit
    # that's actually running, independent of what the target's own .env
    # claims.
    build_commit: str = os.environ.get("MESFLOW_BUILD_COMMIT", "unknown")
    deployment_id: str = os.environ.get("MESFLOW_DEPLOYMENT_ID", "")
    trusted_proxy_count: int = int(os.environ.get("MESFLOW_TRUSTED_PROXY_COUNT", "1"))
    max_content_length: int = int(os.environ.get("MESFLOW_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))
    timezone_name: str = os.environ.get("MESFLOW_TIMEZONE", "Asia/Ho_Chi_Minh")
    test_auto_login: bool = _bool("MESFLOW_TEST_AUTO_LOGIN", "0")
    test_auto_login_username: str = os.environ.get("MESFLOW_TEST_AUTO_LOGIN_USERNAME", "admin")
    local_auto_login: bool = _bool("MESFLOW_LOCAL_AUTO_LOGIN", "0")
    internal_qa_auto_login: bool = _bool("MESFLOW_INTERNAL_QA_AUTO_LOGIN", "0")
    internal_http_session: bool = _bool("MESFLOW_INTERNAL_HTTP_SESSION", "1")
    # Login sessions previously had no
    # server-side expiry at all (decorators only checked session['user_id'],
    # the client-side cookie itself was the only "expiry" and defaults to
    # browser-close). idle=inactivity window; absolute=hard ceiling from
    # login regardless of activity (a stolen/forgotten-open session still
    # dies eventually). kiosk_* is a SEPARATE, shorter default for shared/
    # walk-up terminals (see core/session_policy.py's own docstring for why
    # a single policy for both is wrong).
    session_idle_minutes: int = int(os.environ.get("MESFLOW_SESSION_IDLE_MINUTES", "60"))
    session_absolute_hours: int = int(os.environ.get("MESFLOW_SESSION_ABSOLUTE_HOURS", "12"))
    kiosk_session_idle_minutes: int = int(os.environ.get("MESFLOW_KIOSK_SESSION_IDLE_MINUTES", "15"))
    # A work_session left OPEN past its shift's end
    # boundary gets auto-closed by ShiftSessionReconciliationService, not by
    # a human opening the UI. grace_minutes is deliberately small (a real
    # operator might scan a finish a few minutes after the nominal shift
    # end) -- see session_past_shift_end_grace_minutes below for the
    # earlier-warning tier vs this actually acting on it. `enabled`/
    # `dry_run` are the first-production-rollout safety switches:
    # a first deploy should run dry-run-only, inspect `audit-sessions` +
    # the dry-run reconcile output, THEN flip enabled=1/dry_run=0 -- never
    # auto-close a fleet's worth of historical stale sessions unreviewed.
    shift_auto_close_grace_minutes: int = int(os.environ.get("MESFLOW_SHIFT_AUTO_CLOSE_GRACE_MINUTES", "15"))
    shift_auto_close_enabled: bool = _bool("MESFLOW_SHIFT_AUTO_CLOSE_ENABLED", "0")
    shift_auto_close_dry_run: bool = _bool("MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN", "1")
    # SESSION_PAST_SHIFT_END exception fires this many minutes after
    # shift end (a much shorter, purely-informational warning) -- separate
    # from the grace window above (which is when auto-close actually acts).
    session_past_shift_end_grace_minutes: int = int(os.environ.get("MESFLOW_SESSION_PAST_SHIFT_END_GRACE_MINUTES", "10"))
    # _legacy_kiosk_identity() (web/execution.py) used to
    # auto-bind ANY unknown device_uuid as ACTIVE with no token check, AND
    # silently flip an admin-DISABLED/PENDING identity back to ACTIVE on its
    # very next heartbeat -- an admin disabling a compromised/decommissioned
    # kiosk did nothing, since the device's own next request undid it.
    # Default OFF (production-safe) -- an environment with a live legacy
    # ESP32 fleet still depending on old auto-bind-on-first-contact behavior
    # must opt in explicitly and understand the tradeoff (see that
    # function's own docstring for the compatibility path when OFF: a
    # never-seen device gets a clear 403 telling an operator to register it
    # via /kiosk-management, not a silent auto-bind).
    allow_legacy_kiosk_autobind: bool = _bool("MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND", "0")
    # Codex audit follow-up: autobind-gating alone left a second
    # hole -- an identity that IS already ACTIVE could still call
    # /api/kiosk/bind|connect with nothing but its own public device_uuid
    # and walk away with a BRAND NEW token (bind_legacy() rotates
    # token_hash unconditionally on conflict), i.e. an attacker who merely
    # knows/guesses a real device_uuid could hijack that kiosk identity
    # without ever proving possession of its current token. Default OFF: an
    # ACTIVE identity now must present its current X-Kiosk-Token (or
    # `kiosk_token` in the body) to rebind/rotate. Set to "1" only as a
    # temporary compatibility bridge for hardware that cannot yet send its
    # token on bind/connect -- logs a warning on every use, same spirit as
    # allow_legacy_kiosk_autobind above.
    allow_legacy_unauthenticated_rebind: bool = _bool("MESFLOW_ALLOW_LEGACY_UNAUTHENTICATED_REBIND", "0")
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
    health_agent_url: str = os.environ.get("MESFLOW_SERVER_AGENT_URL", "").rstrip("/")
    health_qa_url: str = os.environ.get("MESFLOW_QA_CENTER_URL", "").rstrip("/")
    health_external_timeout_seconds: float = float(os.environ.get("MESFLOW_HEALTH_EXTERNAL_TIMEOUT_SECONDS", "2.5"))
    health_cache_seconds: int = int(os.environ.get("MESFLOW_HEALTH_CACHE_SECONDS", "10"))
    health_kiosk_degraded_seconds: int = int(os.environ.get("MESFLOW_HEALTH_KIOSK_DEGRADED_SECONDS", "120"))
    health_kiosk_offline_seconds: int = int(os.environ.get("MESFLOW_HEALTH_KIOSK_OFFLINE_SECONDS", "300"))
    health_db_latency_warning_ms: int = int(os.environ.get("MESFLOW_HEALTH_DB_LATENCY_WARNING_MS", "250"))
    health_qa_stale_hours: int = int(os.environ.get("MESFLOW_HEALTH_QA_STALE_HOURS", "24"))
    health_error_window_minutes: int = int(os.environ.get("MESFLOW_HEALTH_ERROR_WINDOW_MINUTES", "60"))
    # Phase 1 Health Center additions -- Deploy Agent already collects host
    # CPU/RAM/Disk/Docker (agent.py ops_summary()); MESFlow reuses that
    # rather than probing the OS itself (it has no Docker socket access).
    health_deploy_agent_url: str = os.environ.get("MESFLOW_DEPLOY_AGENT_URL", "").rstrip("/")
    # Browser-facing URL for Deploy Agent's Operations Center (section 12:
    # MESFlow links out to it rather than duplicating its storage). Distinct
    # from health_deploy_agent_url above, which is a Docker-network URL used
    # for server-to-server calls, not necessarily reachable from a browser.
    operations_center_url: str = os.environ.get("MESFLOW_OPERATIONS_CENTER_URL", "").rstrip("/")
    # Monitoring ownership cutover (reports/SYSTEM_LOG_AUDIT_SEPARATION.md):
    # Deploy Agent is now authoritative for SYSTEM/INFRASTRUCTURE monitoring.
    # This legacy V69 writer (component_health_state/history,
    # scheduled_job_health, health_alerts, notification_deliveries,
    # health_diagnostics_snapshots, health_metric_samples,
    # predictive_insights, ai_incident_analyses) is OFF by default -- it no
    # longer creates new rows. The tables and their read APIs are kept for
    # legacy/read-only history; nothing is dropped. Existing tests still
    # exercise the underlying write mechanism by turning this back on
    # explicitly (compose.test.yml sets it for mesflow-test-api) --
    # that proves the code isn't rotted for a future rollback, without it
    # running in real deployments.
    legacy_health_writer_enabled: bool = str(os.environ.get("MESFLOW_LEGACY_HEALTH_WRITER_ENABLED", "0")).lower() in {"1", "true", "yes", "on"}
    internal_api_token: str = os.environ.get("MESFLOW_INTERNAL_API_TOKEN", "")
    health_deploy_agent_stale_seconds: int = int(os.environ.get("MESFLOW_HEALTH_DEPLOY_AGENT_STALE_SECONDS", "60"))
    health_cpu_warning_percent: int = int(os.environ.get("MESFLOW_HEALTH_CPU_WARNING_PERCENT", "75"))
    health_cpu_critical_percent: int = int(os.environ.get("MESFLOW_HEALTH_CPU_CRITICAL_PERCENT", "90"))
    health_ram_warning_percent: int = int(os.environ.get("MESFLOW_HEALTH_RAM_WARNING_PERCENT", "80"))
    health_ram_critical_percent: int = int(os.environ.get("MESFLOW_HEALTH_RAM_CRITICAL_PERCENT", "90"))
    health_disk_warning_percent: int = int(os.environ.get("MESFLOW_HEALTH_DISK_WARNING_PERCENT", "80"))
    health_disk_critical_percent: int = int(os.environ.get("MESFLOW_HEALTH_DISK_CRITICAL_PERCENT", "90"))
    # Phase 2 Notification + Diagnosis. Email/Telegram are optional -- an
    # empty host/token means NOT_CONFIGURED, never DOWN (section 25).
    smtp_host: str = os.environ.get("MESFLOW_SMTP_HOST", "")
    smtp_port: int = int(os.environ.get("MESFLOW_SMTP_PORT", "587"))
    smtp_user: str = os.environ.get("MESFLOW_SMTP_USER", "")
    smtp_password: str = os.environ.get("MESFLOW_SMTP_PASSWORD", "")
    smtp_from: str = os.environ.get("MESFLOW_SMTP_FROM", "")
    smtp_to: str = os.environ.get("MESFLOW_SMTP_TO", "")  # comma-separated
    smtp_use_tls: bool = os.environ.get("MESFLOW_SMTP_USE_TLS", "1").strip().lower() in {"1","true","yes","on"}
    telegram_bot_token: str = os.environ.get("MESFLOW_TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.environ.get("MESFLOW_TELEGRAM_CHAT_ID", "")
    # Severity routing (section 29): minimum severity that triggers each
    # external channel. WEB always fires for every opened/resolved alert.
    notify_email_min_severity: str = os.environ.get("MESFLOW_NOTIFY_EMAIL_MIN_SEVERITY", "HIGH")
    notify_telegram_min_severity: str = os.environ.get("MESFLOW_NOTIFY_TELEGRAM_MIN_SEVERITY", "HIGH")
    notification_timeout_seconds: float = float(os.environ.get("MESFLOW_NOTIFICATION_TIMEOUT_SECONDS", "5"))
    notification_retry_attempts: int = int(os.environ.get("MESFLOW_NOTIFICATION_RETRY_ATTEMPTS", "3"))
    # Phase 3 Predictive / AI. Forecasts/anomalies/recurrence are always on
    # (pure deterministic code); AI is opt-in and defaults OFF (no API key).
    predictive_disk_component: str = os.environ.get("MESFLOW_PREDICTIVE_DISK_COMPONENT", "/")
    predictive_forecast_min_samples: int = int(os.environ.get("MESFLOW_PREDICTIVE_FORECAST_MIN_SAMPLES", "6"))
    predictive_forecast_min_span_hours: float = float(os.environ.get("MESFLOW_PREDICTIVE_FORECAST_MIN_SPAN_HOURS", "24"))
    predictive_forecast_window_days: int = int(os.environ.get("MESFLOW_PREDICTIVE_FORECAST_WINDOW_DAYS", "30"))
    # Days-until-critical-threshold -> risk band (section 71), configurable.
    predictive_risk_high_days: float = float(os.environ.get("MESFLOW_PREDICTIVE_RISK_HIGH_DAYS", "7"))
    predictive_risk_medium_days: float = float(os.environ.get("MESFLOW_PREDICTIVE_RISK_MEDIUM_DAYS", "14"))
    predictive_risk_low_days: float = float(os.environ.get("MESFLOW_PREDICTIVE_RISK_LOW_DAYS", "30"))
    predictive_anomaly_min_samples: int = int(os.environ.get("MESFLOW_PREDICTIVE_ANOMALY_MIN_SAMPLES", "20"))
    predictive_anomaly_zscore_threshold: float = float(os.environ.get("MESFLOW_PREDICTIVE_ANOMALY_ZSCORE_THRESHOLD", "3"))
    predictive_recurrence_window_days: int = int(os.environ.get("MESFLOW_PREDICTIVE_RECURRENCE_WINDOW_DAYS", "7"))
    predictive_recurrence_min_count: int = int(os.environ.get("MESFLOW_PREDICTIVE_RECURRENCE_MIN_COUNT", "3"))
    metric_sample_retention_days: int = int(os.environ.get("MESFLOW_METRIC_SAMPLE_RETENTION_DAYS", "14"))
    ai_enabled: bool = os.environ.get("MESFLOW_AI_ENABLED", "0").strip().lower() in {"1","true","yes","on"}
    ai_provider: str = os.environ.get("MESFLOW_AI_PROVIDER", "")  # "" or "anthropic"
    ai_api_key: str = os.environ.get("MESFLOW_AI_API_KEY", "")
    ai_model: str = os.environ.get("MESFLOW_AI_MODEL", "claude-haiku-4-5")
    ai_timeout_seconds: float = float(os.environ.get("MESFLOW_AI_TIMEOUT_SECONDS", "15"))
    ai_max_context_chars: int = int(os.environ.get("MESFLOW_AI_MAX_CONTEXT_CHARS", "8000"))


settings = Settings()
if not settings.database_url.startswith("postgresql://"):
    raise RuntimeError("DATABASE_URL must be PostgreSQL; SQLite is not supported in MESFlow v65")
if settings.environment == "production" and settings.secret_key in {"", "dev-only", "CHANGE_ME"}:
    raise RuntimeError("MESFLOW_SECRET_KEY must be configured for production")
