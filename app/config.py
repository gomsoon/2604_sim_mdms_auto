from __future__ import annotations

import os


DEFAULT_DATABASE_URL = "postgresql+psycopg://mdms_app:change-me@127.0.0.1:5432/mdms_dev"


def get_secret_key() -> str:
    return os.getenv("SECRET_KEY", "dev-secret-key")


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


class Config:
    APP_TITLE = "MDMS Minimal E2E"

