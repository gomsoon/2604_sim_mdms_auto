from __future__ import annotations

import os


DEFAULT_DATABASE_URL = "postgresql+psycopg://mdms_app:change-me@127.0.0.1:5432/mdms_dev"
DEFAULT_APP_TIMEZONE = "Asia/Seoul"
DEFAULT_SESSION_TIMEOUT_HOURS = 8


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def get_secret_key() -> str:
    return os.getenv("SECRET_KEY", "dev-secret-key")


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_app_timezone_name() -> str:
    return os.getenv("APP_TIMEZONE", DEFAULT_APP_TIMEZONE)


def get_session_cookie_secure() -> bool:
    return _env_bool("SESSION_COOKIE_SECURE", False)


def get_session_timeout_hours() -> int:
    raw_value = os.getenv("SESSION_TIMEOUT_HOURS")
    if raw_value is None:
        return DEFAULT_SESSION_TIMEOUT_HOURS

    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_SESSION_TIMEOUT_HOURS

    return parsed if parsed > 0 else DEFAULT_SESSION_TIMEOUT_HOURS


class Config:
    APP_TITLE = "MDMS Minimal E2E"
