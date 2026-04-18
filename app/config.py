from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = (BASE_DIR / "instance" / "mdms_dev.db").as_posix()


class Config:
    APP_TITLE = "MDMS Minimal E2E"
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")

