from __future__ import annotations

from pathlib import Path

import click
from flask import Flask

from app.blueprints.api import bp as api_bp
from app.blueprints.web import bp as web_bp
from app.config import Config
from app.db import create_all, get_session, init_app as init_db
from app.services.seeds import seed_demo_environment


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    init_db(app)
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    register_commands(app)
    register_filters(app)

    return app


def register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        create_all()
        click.echo("Database tables created.")

    @app.cli.command("seed-demo")
    def seed_demo_command() -> None:
        session = get_session()
        try:
            summary = seed_demo_environment(session)
            session.commit()
        except Exception:
            session.rollback()
            raise

        click.echo(
            "Demo seed completed: "
            f"master_data_created={summary['master_data_created']}, "
            f"raw_reads={summary['read_summary']['raw_reads_received']}, "
            f"raw_events={summary['event_summary']['raw_events_received']}"
        )


def register_filters(app: Flask) -> None:
    @app.template_filter("dt")
    def format_datetime(value) -> str:
        if value is None:
            return "-"

        try:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        except AttributeError:
            return str(value)

