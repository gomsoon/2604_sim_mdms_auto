from __future__ import annotations

import os


DEFAULT_DATABASE_URL = "postgresql+psycopg://mdms_app:change-me@127.0.0.1:5432/mdms_dev"
DEFAULT_APP_TIMEZONE = "Asia/Seoul"


def get_secret_key() -> str:
    return os.getenv("SECRET_KEY", "dev-secret-key")


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_app_timezone_name() -> str:
    return os.getenv("APP_TIMEZONE", DEFAULT_APP_TIMEZONE)


class Config:
    APP_TITLE = "MDMS Minimal E2E"
