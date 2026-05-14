from __future__ import annotations

from pathlib import Path
from datetime import timedelta

import click
from flask import Flask

from app.blueprints.api import bp as api_bp
from app.blueprints.web import bp as web_bp
from app.config import (
    Config,
    get_database_url,
    get_secret_key,
    get_session_cookie_secure,
    get_session_timeout_hours,
)
from app.db import get_session, init_app as init_db
from app.i18n import register_i18n
from app.migrations import upgrade_db
from app.services.adapter_execution import process_waiting_adapter_runs
from app.services.adapters import enqueue_scheduled_adapter_runs, sync_adapter_health_alerts
from app.services.auth import AuthValidationError, create_user_account, init_auth
from app.services.billing_export_processor import process_queued_billing_export_requests
from app.services.finalization import finalize_canonical_measurements
from app.services.hes_meter_reference_sync import sync_hes_meter_references
from app.services.seeds import seed_demo_environment
from app.services.vee_replay_processor import process_queued_vee_replay_requests


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        APP_TITLE=Config.APP_TITLE,
        SECRET_KEY=get_secret_key(),
        DATABASE_URL=get_database_url(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=get_session_cookie_secure(),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=get_session_timeout_hours()),
    )

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    init_db(app)
    register_i18n(app)
    init_auth(app)
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

    @app.cli.command("create-user")
    @click.option("--login-id", prompt=True)
    @click.option("--display-name", prompt=True)
    @click.option("--role-code", prompt=True, type=click.Choice(["admin", "operator"]))
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_user_command(
        login_id: str,
        display_name: str,
        role_code: str,
        password: str,
    ) -> None:
        session = get_session()
        try:
            user_account = create_user_account(
                session,
                login_id=login_id,
                display_name=display_name,
                role_code=role_code,
                password=password,
            )
            session.commit()
        except AuthValidationError as exc:
            session.rollback()
            raise click.ClickException(exc.fallback_message) from exc
        except Exception:
            session.rollback()
            raise

        click.echo(
            "User created: "
            f"id={user_account.id}, "
            f"login_id={user_account.login_id}, "
            f"role_code={user_account.role_code}"
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
            health_summary = sync_adapter_health_alerts(session)
            session.commit()
        except Exception:
            session.rollback()
            raise

        click.echo(
            "Adapter run processing completed: "
            f"processed={summary.processed}, "
            f"completed={summary.completed}, "
            f"failed={summary.failed}, "
            f"health_checked={health_summary.checked}"
        )

    @app.cli.command("enqueue-scheduled-adapter-runs")
    @click.option("--limit", default=10, type=int)
    def enqueue_scheduled_adapter_runs_command(limit: int) -> None:
        session = get_session()
        try:
            summary = enqueue_scheduled_adapter_runs(session, limit=limit)
            health_summary = sync_adapter_health_alerts(session)
            session.commit()
        except Exception:
            session.rollback()
            raise

        click.echo(
            "Scheduled adapter enqueue completed: "
            f"eligible={summary.eligible}, "
            f"enqueued={summary.enqueued}, "
            f"skipped_due_to_active_run={summary.skipped_due_to_active_run}, "
            f"health_checked={health_summary.checked}"
        )

    @app.cli.command("refresh-adapter-health-alerts")
    def refresh_adapter_health_alerts_command() -> None:
        session = get_session()
        try:
            summary = sync_adapter_health_alerts(session)
            session.commit()
        except Exception:
            session.rollback()
            raise

        click.echo(
            "Adapter health alerts refreshed: "
            f"checked={summary.checked}, "
            f"overdue_opened={summary.overdue_opened}, "
            f"overdue_closed={summary.overdue_closed}, "
            f"stale_opened={summary.stale_opened}, "
            f"stale_closed={summary.stale_closed}"
        )

    @app.cli.command("sync-hes-meter-reference")
    @click.option("--hes-code", required=True)
    def sync_hes_meter_reference_command(hes_code: str) -> None:
        session = get_session()
        try:
            summary = sync_hes_meter_references(session, hes_code=hes_code)
            session.commit()
        except Exception:
            session.rollback()
            raise

        click.echo(
            "HES meter reference sync completed: "
            f"hes_code={summary.hes_code}, "
            f"rows_fetched={summary.rows_fetched}, "
            f"created={summary.created}, "
            f"updated={summary.updated}"
        )

    @app.cli.command("process-vee-replay-requests")
    @click.option("--limit", default=1, type=int)
    @click.option("--request-id", default=None, type=int)
    @click.option("--processed-by", default="vee_replay_worker")
    def process_vee_replay_requests_command(
        limit: int,
        request_id: int | None,
        processed_by: str,
    ) -> None:
        session = get_session()
        try:
            summary = process_queued_vee_replay_requests(
                session,
                limit=limit,
                request_id=request_id,
                processed_by=processed_by,
            )
        except Exception:
            session.rollback()
            raise

        click.echo(
            "VEE replay processing completed: "
            f"claimed_requests={summary.claimed_requests}, "
            f"completed_requests={summary.completed_requests}, "
            f"failed_requests={summary.failed_requests}, "
            f"processed_items={summary.processed_items}, "
            f"succeeded_items={summary.succeeded_items}, "
            f"failed_items={summary.failed_items}"
        )

    @app.cli.command("process-billing-export-requests")
    @click.option("--limit", default=1, type=int)
    @click.option("--request-id", default=None, type=int)
    @click.option("--processed-by", default="billing_export_worker")
    def process_billing_export_requests_command(
        limit: int,
        request_id: int | None,
        processed_by: str,
    ) -> None:
        session = get_session()
        try:
            summary = process_queued_billing_export_requests(
                session,
                limit=limit,
                request_id=request_id,
                processed_by=processed_by,
            )
        except Exception:
            session.rollback()
            raise

        click.echo(
            "Billing export processing completed: "
            f"claimed_requests={summary.claimed_requests}, "
            f"completed_requests={summary.completed_requests}, "
            f"failed_requests={summary.failed_requests}, "
            f"processed_items={summary.processed_items}, "
            f"succeeded_items={summary.succeeded_items}, "
            f"failed_items={summary.failed_items}, "
            f"skipped_items={summary.skipped_items}"
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
