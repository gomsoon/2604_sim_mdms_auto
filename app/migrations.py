from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig


ROOT_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI_PATH = ROOT_DIR / "alembic.ini"
MIGRATIONS_PATH = ROOT_DIR / "migrations"


def build_alembic_config(database_url: str) -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI_PATH))
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_db(database_url: str, revision: str = "head") -> None:
    command.upgrade(build_alembic_config(database_url), revision)

