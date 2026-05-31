import os
from dataclasses import dataclass
from functools import lru_cache


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except Exception:
        return default


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _read_str_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


@dataclass(frozen=True)
class Settings:
    app_env: str
    local_mode: bool
    ops_enabled: bool
    ops_admin_emails: str
    cta_token_ttl_days: int
    growth_window_default_days: int
    growth_window_max_days: int
    intervention_window_default_days: int
    intervention_window_max_days: int
    auth_code_ttl_minutes: int
    auth_code_max_attempts: int
    auth_start_max_per_hour: int
    auth_start_max_per_ip_hour: int
    auth_session_ttl_days: int
    auth_debug_codes: bool
    session_cookie_secure: bool
    auth_email_provider: str
    resend_api_key: str
    resend_from_email: str
    storage_backend: str
    database_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    app_env = _read_str_env("ONEFILE_ENV", "development").lower() or "development"
    is_production = app_env in {"prod", "production"}
    local_mode = _read_bool_env("ONEFILE_LOCAL_MODE", not is_production)
    ops_enabled = _read_bool_env("ONEFILE_OPS_ENABLED", local_mode or not is_production)
    ops_admin_emails = _read_str_env("ONEFILE_OPS_ADMIN_EMAILS", "")
    cta_ttl = _clamp(_read_int_env("ONEFILE_CTA_TOKEN_TTL_DAYS", 7), 1, 30)
    growth_default = _clamp(_read_int_env("ONEFILE_GROWTH_WINDOW_DEFAULT_DAYS", 14), 1, 30)
    growth_max = _clamp(_read_int_env("ONEFILE_GROWTH_WINDOW_MAX_DAYS", 60), 7, 120)
    intervention_default = _clamp(_read_int_env("ONEFILE_INTERVENTION_WINDOW_DEFAULT_DAYS", 30), 1, 60)
    intervention_max = _clamp(_read_int_env("ONEFILE_INTERVENTION_WINDOW_MAX_DAYS", 90), 7, 120)
    auth_code_ttl_minutes = _clamp(_read_int_env("ONEFILE_AUTH_CODE_TTL_MINUTES", 10), 3, 30)
    auth_code_max_attempts = _clamp(_read_int_env("ONEFILE_AUTH_CODE_MAX_ATTEMPTS", 5), 1, 10)
    auth_start_max_per_hour = _clamp(_read_int_env("ONEFILE_AUTH_START_MAX_PER_HOUR", 8), 2, 50)
    auth_start_max_per_ip_hour = _clamp(_read_int_env("ONEFILE_AUTH_START_MAX_PER_IP_HOUR", 20), 4, 200)
    auth_session_ttl_days = _clamp(_read_int_env("ONEFILE_AUTH_SESSION_TTL_DAYS", 14), 1, 30)
    auth_debug_codes = _read_bool_env("ONEFILE_AUTH_DEBUG_CODES", not is_production)
    session_cookie_secure = _read_bool_env("ONEFILE_SESSION_COOKIE_SECURE", is_production)
    auth_email_provider = _read_str_env("ONEFILE_AUTH_EMAIL_PROVIDER", "resend").lower() or "resend"
    resend_api_key = _read_str_env("ONEFILE_RESEND_API_KEY", "")
    resend_from_email = _read_str_env("ONEFILE_RESEND_FROM_EMAIL", "")
    storage_backend = _read_str_env("ONEPITCH_STORAGE_BACKEND", "json").lower() or "json"
    if storage_backend not in {"json", "postgres"}:
        storage_backend = "json"
    database_url = _read_str_env("DATABASE_URL", "")
    return Settings(
        app_env=app_env,
        local_mode=local_mode,
        ops_enabled=ops_enabled,
        ops_admin_emails=ops_admin_emails,
        cta_token_ttl_days=cta_ttl,
        growth_window_default_days=min(growth_default, growth_max),
        growth_window_max_days=growth_max,
        intervention_window_default_days=min(intervention_default, intervention_max),
        intervention_window_max_days=intervention_max,
        auth_code_ttl_minutes=auth_code_ttl_minutes,
        auth_code_max_attempts=auth_code_max_attempts,
        auth_start_max_per_hour=auth_start_max_per_hour,
        auth_start_max_per_ip_hour=auth_start_max_per_ip_hour,
        auth_session_ttl_days=auth_session_ttl_days,
        auth_debug_codes=auth_debug_codes,
        session_cookie_secure=session_cookie_secure,
        auth_email_provider=auth_email_provider,
        resend_api_key=resend_api_key,
        resend_from_email=resend_from_email,
        storage_backend=storage_backend,
        database_url=database_url,
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
