from __future__ import annotations

import os
import re
import uuid

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://mdms_app:change-me@127.0.0.1:5432/mdms_test"
SCHEMA_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

load_dotenv()


def resolve_test_database_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit

    runtime_url = os.getenv("DATABASE_URL")
    if runtime_url:
        url = make_url(runtime_url)
        if url.database:
            return url.set(database="mdms_test").render_as_string(hide_password=False)

    return DEFAULT_TEST_DATABASE_URL


def build_schema_name(prefix: str = "pytest") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def build_schema_url(database_url: str, schema_name: str) -> str:
    validate_schema_name(schema_name)
    url = make_url(database_url).update_query_dict({"options": f"-csearch_path={schema_name}"})
    return url.render_as_string(hide_password=False)


def validate_schema_name(schema_name: str) -> None:
    if not SCHEMA_NAME_PATTERN.fullmatch(schema_name):
        raise ValueError(f"Invalid PostgreSQL schema name: {schema_name}")


def create_schema(database_url: str, schema_name: str) -> None:
    validate_schema_name(schema_name)
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
    finally:
        engine.dispose()


def drop_schema(database_url: str, schema_name: str) -> None:
    validate_schema_name(schema_name)
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
    finally:
        engine.dispose()
