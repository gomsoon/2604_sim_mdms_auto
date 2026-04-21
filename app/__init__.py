from __future__ import annotations

from pathlib import Path

import click
from flask import Flask

from app.blueprints.api import bp as api_bp
from app.blueprints.web import bp as web_bp
from app.config import Config, get_database_url, get_secret_key
from app.db import get_session, init_app as init_db
from app.i18n import register_i18n
from app.migrations import upgrade_db
from app.services.adapter_execution import process_waiting_adapter_runs
from app.services.adapters import enqueue_scheduled_adapter_runs
from app.services.finalization import finalize_canonical_measurements
from app.services.seeds import seed_demo_environment


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        APP_TITLE=Config.APP_TITLE,
        SECRET_KEY=get_secret_key(),
        DATABASE_URL=get_database_url(),
    )

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    init_db(app)
    register_i18n(app)
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    register_commands(app)
    register_filters(app)

    return app


def register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        upgrade_db(app.config["DATABASE_URL"])
        click.echo("Database schema upgraded to head.")

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

    @app.cli.command("promote-final")
    @click.option("--batch-id", default=None)
    @click.option("--meter-id", default=None)
    @click.option("--limit", default=100, type=int)
    def promote_final_command(batch_id: str | None, meter_id: str | None, limit: int) -> None:
        session = get_session()
        try:
            summary = finalize_canonical_measurements(
                session,
                batch_id=batch_id,
                meter_id=meter_id,
                limit=limit,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

        click.echo(
            "Finalization completed: "
            f"candidates={summary.candidates}, "
            f"finalized={summary.finalized}, "
            f"skipped_existing={summary.skipped_existing}, "
            f"skipped_not_well_formed={summary.skipped_not_well_formed}"
        )

    @app.cli.command("process-adapter-runs")
    @click.option("--limit", default=1, type=int)
    @click.option("--run-id", default=None, type=int)
    def process_adapter_runs_command(limit: int, run_id: int | None) -> None:
        session = get_session()
        try:
            summary = process_waiting_adapter_runs(session, limit=limit, run_id=run_id)
            session.commit()
        except Exception:
            session.rollback()
            raise

        click.echo(
            "Adapter run processing completed: "
            f"processed={summary.processed}, "
            f"completed={summary.completed}, "
            f"failed={summary.failed}"
        )

    @app.cli.command("enqueue-scheduled-adapter-runs")
    @click.option("--limit", default=10, type=int)
    def enqueue_scheduled_adapter_runs_command(limit: int) -> None:
        session = get_session()
        try:
            summary = enqueue_scheduled_adapter_runs(session, limit=limit)
            session.commit()
        except Exception:
            session.rollback()
            raise

        click.echo(
            "Scheduled adapter enqueue completed: "
            f"eligible={summary.eligible}, "
            f"enqueued={summary.enqueued}, "
            f"skipped_due_to_active_run={summary.skipped_due_to_active_run}"
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
