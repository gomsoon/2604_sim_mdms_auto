from __future__ import annotations

from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


SessionLocal = scoped_session(sessionmaker(autoflush=False, expire_on_commit=False))
_engine: Engine | None = None


def init_app(app: Flask) -> None:
    global _engine

    _engine = create_engine(app.config["DATABASE_URL"], future=True, pool_pre_ping=True)
    SessionLocal.configure(bind=_engine)

    @app.teardown_appcontext
    def cleanup_session(exception: BaseException | None = None) -> None:
        SessionLocal.remove()


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine is not initialized.")

    return _engine


def get_session():
    return SessionLocal


def check_database_connection() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))

