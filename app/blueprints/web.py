from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, abort, flash, redirect, render_template, request, session as browser_session, url_for
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.config import get_app_timezone_name
from app.db import get_session
from app.i18n import (
    translate_adapter_error,
    translate_billing_export_request_error,
    get_locale,
    translate_hes_system_error,
    translate,
    translate_estimation_error,
    translate_manual_edit_error,
    translate_operational_alert_error,
    translate_vee_exception_error,
    translate_vee_replay_request_error,
    translate_finalization_result,
    translate_master_data_error,
    translate_reprocess_error,
    translate_reprocess_result,
    translate_visibility_error,
)
from app.models import (
    AdapterInstance,
    Device,
    EstimationAudit,
    HesEventRaw,
    HesReadRaw,
    HesSystem,
    InstallationHistory,
    MeasuringComponent,
    ServicePoint,
    ServicePointBillingContext,
    ServicePointTariffAssignment,
)
from app.services.adapters import (
    AdapterValidationError,
    create_adapter_instance,
    get_adapter_instance_detail,
    list_adapter_instances,
    list_active_adapter_definitions,
    queue_adapter_run_once,
    update_adapter_admin_state,
)
from app.services.auth import (
    AuthenticationResult,
    admin_required,
    get_current_user,
    login_user_account,
    logout_current_user,
    authenticate_user,
    record_failed_login,
)
from app.services.billing_contexts import create_billing_context, update_billing_context
from app.services.billing_export_requests import (
    BillingExportRequestError,
    cancel_billing_export_request,
)
from app.services.correction_policy import (
    CORRECTION_POLICY_BLOCKED,
    SUPPORTED_CORRECTION_POLICY_EVENT_CONTEXT_TYPES,
    SUPPORTED_CORRECTION_POLICY_REASON_CODES,
    build_correction_policy_decision,
)
from app.services.dashboard import build_dashboard_snapshot
from app.services.estimation import (
    ESTIMATION_ALLOWED_EXCEPTION_CODES,
    SUPPORTED_ESTIMATION_STRATEGIES,
    EstimationActionError,
    apply_estimation_from_vee_exception,
    apply_synthetic_missing_interval_estimation_from_vee_exception,
    get_synthetic_missing_interval_estimation_precheck,
)
from app.services.manual_edits import (
    MANUAL_EDIT_ALLOWED_EXCEPTION_CODES,
    SUPPORTED_MANUAL_EDIT_REASON_CODES,
    ManualEditActionError,
    apply_manual_edit_from_vee_exception,
)
from app.services.exception_queue import (
    ExceptionReprocessError,
    build_exception_filters,
    get_exception_batch_id,
    get_exception_meter_id,
    get_exception_detail_context,
    list_exception_queue,
    reprocess_exception,
)
from app.services.finalization import FinalizationSummary, finalize_canonical_measurements
from app.services.installations import (
    InstallationValidationError,
    create_installation_history,
    update_installation_history,
)
from app.services.hes_systems import (
    HesSystemValidationError,
    create_hes_system,
    get_hes_system_detail,
    list_hes_meter_reference_comparisons,
    list_hes_systems,
    sync_hes_meter_reference_alerts,
    update_hes_system,
)
from app.services.hes_meter_references import list_prefill_hes_meter_references
from app.services.master_data import (
    MasterDataValidationError,
    create_device,
    create_measuring_component,
    create_service_point,
    update_device,
    update_measuring_component,
    update_service_point,
)
from app.services.tariff_assignments import (
    create_tariff_assignment,
    update_tariff_assignment,
)
from app.services.operational_events import (
    OperationalAlertError,
    acknowledge_operational_alert,
    close_operational_alert,
)
from app.services.processing_replay import reevaluate_vee_exception_and_replay
from app.services.vee import (
    VeeExceptionActionError,
    acknowledge_vee_exception,
    resolve_vee_exception,
)
from app.services.vee_replay_requests import (
    VeeReplayRequestError,
    cancel_vee_replay_request,
    create_vee_replay_request,
)
from app.services.visibility import (
    build_bill_charge_filters,
    build_billing_export_request_filters,
    build_estimation_audit_filters,
    build_manual_edit_audit_filters,
    VisibilityFilterError,
    build_bill_determinant_filters,
    build_canonical_filters,
    build_final_filters,
    build_ingest_batch_filters,
    build_operational_event_filters,
    build_usage_transaction_filters,
    build_vee_exception_filters,
    build_vee_replay_request_filters,
    get_bill_charge_detail_context,
    get_billing_export_request_detail_context,
    get_estimation_audit_detail_context,
    get_manual_edit_audit_detail_context,
    get_bill_determinant_detail_context,
    get_usage_transaction_detail_context,
    get_vee_exception_detail_context,
    get_vee_replay_request_detail_context,
    get_operational_event_detail_context,
    list_bill_charges,
    list_billing_export_requests,
    list_estimation_audits,
    list_manual_edit_audits,
    list_bill_determinants,
    list_canonical_measurements,
    list_final_measurements,
    list_ingest_batches,
    list_operational_events,
    list_usage_transactions,
    list_vee_exceptions,
    list_vee_replay_requests,
)


bp = Blueprint("web", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user() is not None:
        return redirect(url_for("web.dashboard", lang=get_locale()))

    next_url = request.values.get("next") or url_for("web.dashboard", lang=get_locale())

    if request.method == "POST":
        login_id = request.form.get("login_id", "").strip()
        password = request.form.get("password", "")
        session = get_session()
        auth_result: AuthenticationResult = authenticate_user(
            session,
            login_id=login_id,
            password=password,
        )
        if auth_result.user_account is None:
            record_failed_login(login_id, auth_result.error_code or "invalid_credentials")
            flash(translate(f"auth.errors.{auth_result.error_code or 'invalid_credentials'}"), "danger")
            return render_template("login.html", next_url=next_url, login_id=login_id), 401

        if auth_result.error_code is not None:
            record_failed_login(
                login_id,
                auth_result.error_code,
                user_account_id=auth_result.user_account.id,
            )
            flash(translate(f"auth.errors.{auth_result.error_code}"), "danger")
            return render_template("login.html", next_url=next_url, login_id=login_id), 403

        try:
            login_user_account(auth_result.user_account)
            session.commit()
        except Exception:
            session.rollback()
            raise

        flash(translate("auth.flash.login_succeeded"), "success")
        return redirect(_safe_next_url(url_for("web.dashboard", lang=get_locale())))

    return render_template("login.html", next_url=next_url, login_id="")


@bp.post("/logout")
def logout():
    logout_current_user()
    flash(translate("auth.flash.logout_succeeded"), "success")
    return redirect(url_for("web.login", lang=get_locale()))


@bp.get("/")
def dashboard():
    session = get_session()
    snapshot = build_dashboard_snapshot(session)
    return render_template(
        "dashboard.html",
        stats=snapshot.stats,
        stage_cards=snapshot.stage_cards,
        recent_reads=snapshot.recent_reads,
        recent_exceptions=snapshot.recent_exceptions,
        open_alerts=snapshot.open_alerts,
        recent_events=snapshot.recent_events,
        recent_recalculated_usage=snapshot.recent_recalculated_usage,
        recent_bill_determinants=snapshot.recent_bill_determinants,
        recent_vee_replay_requests=snapshot.recent_vee_replay_requests,
        correction_policy_spotlight=snapshot.correction_policy_spotlight,
        recent_correction_audits=snapshot.recent_correction_audits,
    )


@bp.post("/operational-events/<int:event_id>/acknowledge")
def acknowledge_operational_alert_view(event_id: int):
    session = get_session()
    try:
        acknowledge_operational_alert(session, event_id, acknowledged_by="operator_ui")
        session.commit()
        flash(translate("operational_alert.flash.acknowledged"), "success")
    except OperationalAlertError as exc:
        session.rollback()
        flash(translate_operational_alert_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(url_for("web.dashboard", lang=get_locale())))


@bp.post("/operational-events/<int:event_id>/close")
def close_operational_alert_view(event_id: int):
    session = get_session()
    try:
        close_operational_alert(
            session,
            event_id,
            operator_memo=request.form.get("operator_memo"),
        )
        session.commit()
        flash(translate("operational_alert.flash.closed"), "success")
    except OperationalAlertError as exc:
        session.rollback()
        flash(translate_operational_alert_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(url_for("web.dashboard", lang=get_locale())))


@bp.get("/raw-reads")
def raw_reads():
    session = get_session()
    rows = session.scalars(select(HesReadRaw).order_by(HesReadRaw.id.desc()).limit(100)).all()
    return render_template("raw_reads.html", rows=rows)


@bp.get("/raw-events")
def raw_events():
    session = get_session()
    rows = session.scalars(select(HesEventRaw).order_by(HesEventRaw.id.desc()).limit(100)).all()
    return render_template("raw_events.html", rows=rows)


@bp.get("/exceptions")
def exceptions():
    session = get_session()
    filters = build_exception_filters(request.args)
    rows = list_exception_queue(session, filters)
    return render_template(
        "exceptions.html",
        rows=rows,
        filters=filters,
        get_exception_batch_id=get_exception_batch_id,
        get_exception_meter_id=get_exception_meter_id,
    )


def _exception_redirect(exception_id: int) -> str:
    return url_for("web.exception_detail", exception_id=exception_id, lang=get_locale())


def _safe_next_url(default_url: str) -> str:
    next_url = request.form.get("next") or request.args.get("next")
    if next_url and next_url.startswith("/"):
        return next_url
    return default_url


def _canonical_filters_to_query_args(filters) -> dict[str, str]:
    values = {"lang": get_locale()}
    if filters.batch_id:
        values["batch_id"] = filters.batch_id
    if filters.meter_id:
        values["meter_id"] = filters.meter_id
    if filters.date_from:
        values["date_from"] = filters.date_from.date().isoformat()
    if filters.date_to:
        values["date_to"] = filters.date_to.date().isoformat()
    return values


def _finalization_result_code(summary: FinalizationSummary) -> str:
    if summary.skipped_not_well_formed > 0:
        return "finalization_completed_with_skips"
    if summary.finalized > 0:
        return "finalization_completed"
    return "finalization_noop"


@bp.get("/exceptions/<int:exception_id>")
def exception_detail(exception_id: int):
    session = get_session()
    detail = get_exception_detail_context(session, exception_id)
    if detail is None:
        abort(404)

    return render_template("exception_detail.html", detail=detail)


@bp.post("/exceptions/<int:exception_id>/reprocess")
def reprocess_exception_view(exception_id: int):
    session = get_session()
    detail = get_exception_detail_context(session, exception_id)
    if detail is None:
        abort(404)

    try:
        result = reprocess_exception(session, detail.error_log)
        session.commit()
        category = "success" if result.status == "completed" else "danger"
        flash(translate_reprocess_result(result.result_code, result.result_message), category)
    except ExceptionReprocessError as exc:
        session.rollback()
        flash(translate_reprocess_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_exception_redirect(exception_id))


@bp.get("/vee-exceptions")
def vee_exceptions():
    session = get_session()
    try:
        filters = build_vee_exception_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_vee_exception_filters({})

    rows = list_vee_exceptions(session, filters)
    hes_system_options = session.scalars(
        select(HesSystem).order_by(HesSystem.display_name.asc(), HesSystem.id.asc())
    ).all()
    selected_hes_system = (
        next((row for row in hes_system_options if row.id == filters.hes_system_id), None)
        if filters.hes_system_id is not None
        else None
    )
    selected_timezone = (
        selected_hes_system.timezone_name
        if selected_hes_system is not None and selected_hes_system.timezone_name
        else get_app_timezone_name()
    )
    replay_prefill = {
        "request_scope": (
            "date_range"
            if filters.date_from is not None and filters.date_to is not None
            else "hes_system"
        ),
        "hes_system_id": filters.hes_system_id,
        "window_timezone_name": selected_timezone,
        "measured_at_from": _format_datetime_local(filters.date_from, selected_timezone),
        "measured_at_to": _format_datetime_local(filters.date_to, selected_timezone),
    }
    correction_policies = {
        row.id: build_correction_policy_decision(session, row) for row in rows
    }
    return render_template(
        "vee_exceptions.html",
        rows=rows,
        filters=filters,
        hes_system_options=hes_system_options,
        replay_prefill=replay_prefill,
        correction_policies=correction_policies,
        correction_policy_reason_codes=SUPPORTED_CORRECTION_POLICY_REASON_CODES,
        correction_policy_event_context_types=SUPPORTED_CORRECTION_POLICY_EVENT_CONTEXT_TYPES,
    )


def _build_vee_replay_request_form_data(
    values: dict[str, str | None] | None = None,
) -> dict[str, str]:
    source = values or {}
    return {
        "request_scope": (source.get("request_scope") or "hes_system").strip(),
        "requested_by": (source.get("requested_by") or "operator_ui").strip(),
        "operator_memo": (source.get("operator_memo") or "").strip(),
        "hes_system_id": (source.get("hes_system_id") or "").strip(),
        "ingest_batch_id": (source.get("ingest_batch_id") or "").strip(),
        "measured_at_from": (source.get("measured_at_from") or "").strip(),
        "measured_at_to": (source.get("measured_at_to") or "").strip(),
        "window_timezone_name": (source.get("window_timezone_name") or "Asia/Seoul").strip(),
    }


def _parse_optional_int(raw_value: str | None) -> int | None:
    normalized = (raw_value or "").strip()
    if not normalized:
        return None
    return int(normalized)


def _parse_local_datetime(raw_value: str | None, timezone_name: str | None) -> datetime | None:
    normalized = (raw_value or "").strip()
    if not normalized:
        return None
    zone_name = (timezone_name or "UTC").strip() or "UTC"
    naive_value = datetime.fromisoformat(normalized)
    localized = naive_value.replace(tzinfo=ZoneInfo(zone_name))
    return localized.astimezone(ZoneInfo("UTC"))


def _format_datetime_local(value: datetime | None, timezone_name: str | None) -> str:
    if value is None:
        return ""
    zone_name = (timezone_name or get_app_timezone_name()).strip() or get_app_timezone_name()
    return value.astimezone(ZoneInfo(zone_name)).strftime("%Y-%m-%dT%H:%M")


def _build_vee_replay_request_prefill_from_request(replay_request) -> dict[str, str]:
    timezone_name = (
        replay_request.window_timezone_name
        or (replay_request.hes_system.timezone_name if replay_request.hes_system is not None else None)
        or "Asia/Seoul"
    )
    return {
        "request_scope": replay_request.request_scope,
        "requested_by": replay_request.requested_by or "operator_ui",
        "operator_memo": replay_request.operator_memo or "",
        "hes_system_id": str(replay_request.hes_system_id or ""),
        "ingest_batch_id": str(replay_request.ingest_batch_id or ""),
        "measured_at_from": _format_datetime_local(replay_request.measured_at_from, timezone_name),
        "measured_at_to": _format_datetime_local(replay_request.measured_at_to, timezone_name),
        "window_timezone_name": timezone_name,
    }


@bp.get("/vee-replay-requests/new")
def new_vee_replay_request():
    session = get_session()
    form_data = _build_vee_replay_request_form_data(request.args)
    hes_system_options = session.scalars(
        select(HesSystem).order_by(HesSystem.display_name.asc(), HesSystem.id.asc())
    ).all()
    return render_template(
        "vee_replay_request_new.html",
        form_data=form_data,
        hes_system_options=hes_system_options,
    )


@bp.post("/vee-replay-requests")
def create_vee_replay_request_view():
    session = get_session()
    form_data = _build_vee_replay_request_form_data(request.form)
    hes_system_options = session.scalars(
        select(HesSystem).order_by(HesSystem.display_name.asc(), HesSystem.id.asc())
    ).all()

    try:
        result = create_vee_replay_request(
            session,
            request_scope=form_data["request_scope"],
            requested_by=form_data["requested_by"] or "operator_ui",
            operator_memo=form_data["operator_memo"] or None,
            hes_system_id=_parse_optional_int(form_data["hes_system_id"]),
            ingest_batch_id=_parse_optional_int(form_data["ingest_batch_id"]),
            measured_at_from=_parse_local_datetime(
                form_data["measured_at_from"], form_data["window_timezone_name"]
            ),
            measured_at_to=_parse_local_datetime(
                form_data["measured_at_to"], form_data["window_timezone_name"]
            ),
            window_timezone_name=form_data["window_timezone_name"] or None,
        )
        session.commit()
        flash(translate("vee_replay.flash.request_created"), "success")
        return redirect(
            url_for(
                "web.vee_replay_request_detail",
                request_id=result.request.id,
                lang=get_locale(),
            )
        )
    except (VeeReplayRequestError, ValueError, ZoneInfoNotFoundError) as exc:
        session.rollback()
        if isinstance(exc, VeeReplayRequestError):
            message = translate_vee_replay_request_error(exc.error_code, exc.fallback_message)
        else:
            message = translate_vee_replay_request_error(
                "invalid_form_input",
                "Replay request form input is invalid.",
            )
        flash(message, "danger")
        return render_template(
            "vee_replay_request_new.html",
            form_data=form_data,
            hes_system_options=hes_system_options,
        )


@bp.get("/vee-replay-requests")
def vee_replay_requests():
    session = get_session()
    try:
        filters = build_vee_replay_request_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_vee_replay_request_filters({})

    rows = list_vee_replay_requests(session, filters)
    hes_system_options = session.scalars(
        select(HesSystem).order_by(HesSystem.display_name.asc(), HesSystem.id.asc())
    ).all()
    return render_template(
        "vee_replay_requests.html",
        rows=rows,
        filters=filters,
        hes_system_options=hes_system_options,
    )


@bp.get("/vee-replay-requests/<int:request_id>")
def vee_replay_request_detail(request_id: int):
    session = get_session()
    detail = get_vee_replay_request_detail_context(session, request_id)
    if detail is None:
        abort(404)
    repeat_scope_url = url_for(
        "web.new_vee_replay_request",
        lang=get_locale(),
        **_build_vee_replay_request_prefill_from_request(detail.request),
    )
    return render_template(
        "vee_replay_request_detail.html",
        detail=detail,
        repeat_scope_url=repeat_scope_url,
    )


@bp.post("/vee-replay-requests/<int:request_id>/cancel")
def cancel_vee_replay_request_view(request_id: int):
    session = get_session()
    try:
        replay_request = cancel_vee_replay_request(
            session,
            request_id,
            cancelled_by="operator_ui",
            operator_memo=request.form.get("operator_memo") or None,
        )
        session.commit()
        flash(translate("vee_replay.flash.cancelled"), "success")
        return redirect(
            _safe_next_url(
                url_for(
                    "web.vee_replay_request_detail",
                    request_id=replay_request.id,
                    lang=get_locale(),
                )
            )
        )
    except VeeReplayRequestError as exc:
        session.rollback()
        flash(translate_vee_replay_request_error(exc.error_code, exc.fallback_message), "danger")
        return redirect(
            _safe_next_url(
                url_for("web.vee_replay_request_detail", request_id=request_id, lang=get_locale())
            )
        )


def _is_billing_export_request_heartbeat_stale(export_request) -> bool:
    if export_request.status != "processing" or export_request.last_heartbeat_at is None:
        return False
    return (datetime.now(tz=export_request.last_heartbeat_at.tzinfo) - export_request.last_heartbeat_at).total_seconds() > 300


@bp.get("/billing-export-requests")
def billing_export_requests():
    session = get_session()
    try:
        filters = build_billing_export_request_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_billing_export_request_filters({})

    rows = list_billing_export_requests(session, filters)
    stale_request_ids = {
        row.id for row in rows if _is_billing_export_request_heartbeat_stale(row)
    }
    return render_template(
        "billing_export_requests.html",
        rows=rows,
        filters=filters,
        stale_request_ids=stale_request_ids,
    )


@bp.get("/billing-export-requests/<int:request_id>")
def billing_export_request_detail(request_id: int):
    session = get_session()
    detail = get_billing_export_request_detail_context(session, request_id)
    if detail is None:
        abort(404)
    return render_template("billing_export_request_detail.html", detail=detail)


@bp.post("/billing-export-requests/<int:request_id>/cancel")
@admin_required
def cancel_billing_export_request_view(request_id: int):
    session = get_session()
    try:
        export_request = cancel_billing_export_request(
            session,
            request_id,
            cancelled_by="operator_ui",
            operator_memo=request.form.get("operator_memo") or None,
        )
        session.commit()
        flash(translate("billing_export.flash.cancelled"), "success")
        return redirect(
            _safe_next_url(
                url_for(
                    "web.billing_export_request_detail",
                    request_id=export_request.id,
                    lang=get_locale(),
                )
            )
        )
    except BillingExportRequestError as exc:
        session.rollback()
        flash(translate_billing_export_request_error(exc.error_code, exc.fallback_message), "danger")
        return redirect(
            _safe_next_url(
                url_for(
                    "web.billing_export_request_detail",
                    request_id=request_id,
                    lang=get_locale(),
                )
            )
        )


def _vee_exception_redirect(vee_exception_id: int) -> str:
    return url_for("web.vee_exception_detail", vee_exception_id=vee_exception_id, lang=get_locale())


def _store_vee_replay_summary(summary) -> None:
    browser_session["last_vee_replay_summary"] = asdict(summary)


def _pop_vee_replay_summary(vee_exception_id: int) -> dict | None:
    payload = browser_session.pop("last_vee_replay_summary", None)
    if payload is None:
        return None
    if payload.get("target_vee_exception_id") == vee_exception_id:
        return payload
    browser_session["last_vee_replay_summary"] = payload
    return None


def _store_estimation_summary(summary) -> None:
    payload = asdict(summary)
    if payload.get("estimated_value") is not None:
        payload["estimated_value"] = str(payload["estimated_value"])
    browser_session["last_estimation_summary"] = payload


def _pop_estimation_summary(vee_exception_id: int) -> dict | None:
    payload = browser_session.pop("last_estimation_summary", None)
    if payload is None:
        return None
    if payload.get("target_vee_exception_id") == vee_exception_id:
        return payload
    browser_session["last_estimation_summary"] = payload
    return None


def _get_latest_estimation_audit_id_for_vee_exception(
    session,
    *,
    vee_exception_id: int,
    initial_measurement_id: int,
) -> int | None:
    rows = session.scalars(
        select(EstimationAudit)
        .where(EstimationAudit.target_initial_measurement_id == initial_measurement_id)
        .order_by(EstimationAudit.created_at.desc(), EstimationAudit.id.desc())
        .limit(10)
    ).all()
    fallback_id: int | None = None
    for row in rows:
        if fallback_id is None:
            fallback_id = row.id
        details = row.details or {}
        target_snapshot = details.get("target_vee_exception_snapshot") or {}
        anchor_snapshot = details.get("anchor_vee_exception_snapshot") or {}
        if (
            target_snapshot.get("vee_exception_id") == vee_exception_id
            or anchor_snapshot.get("vee_exception_id") == vee_exception_id
        ):
            return row.id
    return fallback_id


def _store_manual_edit_summary(summary) -> None:
    payload = asdict(summary)
    if payload.get("edited_value") is not None:
        payload["edited_value"] = str(payload["edited_value"])
    browser_session["last_manual_edit_summary"] = payload


def _pop_manual_edit_summary(vee_exception_id: int) -> dict | None:
    payload = browser_session.pop("last_manual_edit_summary", None)
    if payload is None:
        return None
    if payload.get("target_vee_exception_id") == vee_exception_id:
        return payload
    browser_session["last_manual_edit_summary"] = payload
    return None


@bp.get("/vee-exceptions/<int:vee_exception_id>")
def vee_exception_detail(vee_exception_id: int):
    session = get_session()
    detail = get_vee_exception_detail_context(session, vee_exception_id)
    if detail is None:
        abort(404)
    correction_policy = build_correction_policy_decision(
        session,
        detail.vee_exception,
        initial_row=detail.initial_measurement,
    )
    estimation_available = (
        detail.vee_exception.exception_code in ESTIMATION_ALLOWED_EXCEPTION_CODES
        and correction_policy.estimation_policy != CORRECTION_POLICY_BLOCKED
    )
    synthetic_estimation_precheck = get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=detail.vee_exception,
        initial_row=detail.initial_measurement,
    )
    manual_edit_available = (
        detail.vee_exception.exception_code in MANUAL_EDIT_ALLOWED_EXCEPTION_CODES
        and correction_policy.manual_edit_policy != CORRECTION_POLICY_BLOCKED
    )
    estimation_summary = _pop_estimation_summary(vee_exception_id)
    latest_estimation_audit_id = _get_latest_estimation_audit_id_for_vee_exception(
        session,
        vee_exception_id=vee_exception_id,
        initial_measurement_id=detail.initial_measurement.id,
    )

    return render_template(
        "vee_exception_detail.html",
        detail=detail,
        replay_summary=_pop_vee_replay_summary(vee_exception_id),
        estimation_summary=estimation_summary,
        latest_estimation_audit_id=latest_estimation_audit_id,
        manual_edit_summary=_pop_manual_edit_summary(vee_exception_id),
        correction_policy=correction_policy,
        estimation_available=estimation_available,
        synthetic_estimation_precheck=synthetic_estimation_precheck,
        manual_edit_available=manual_edit_available,
        estimation_strategies=sorted(SUPPORTED_ESTIMATION_STRATEGIES),
        estimation_supported_exception_codes=ESTIMATION_ALLOWED_EXCEPTION_CODES,
        manual_edit_reason_codes=sorted(SUPPORTED_MANUAL_EDIT_REASON_CODES),
        manual_edit_supported_exception_codes=MANUAL_EDIT_ALLOWED_EXCEPTION_CODES,
    )


@bp.post("/vee-exceptions/<int:vee_exception_id>/acknowledge")
def acknowledge_vee_exception_view(vee_exception_id: int):
    session = get_session()
    current_user = get_current_user()
    assert current_user is not None
    try:
        acknowledge_vee_exception(
            session,
            vee_exception_id,
            acknowledged_by=current_user.login_id,
            acknowledged_by_user_account_id=current_user.id,
        )
        session.commit()
        flash(translate("vee_exception.flash.acknowledged"), "success")
    except VeeExceptionActionError as exc:
        session.rollback()
        flash(translate_vee_exception_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_vee_exception_redirect(vee_exception_id)))


@bp.post("/vee-exceptions/<int:vee_exception_id>/resolve")
def resolve_vee_exception_view(vee_exception_id: int):
    session = get_session()
    current_user = get_current_user()
    assert current_user is not None
    try:
        resolve_vee_exception(
            session,
            vee_exception_id,
            resolution_type=request.form.get("resolution_type") or "operator_resolution",
            resolved_by=current_user.login_id,
            resolved_by_user_account_id=current_user.id,
            operator_memo=request.form.get("operator_memo"),
        )
        session.commit()
        flash(translate("vee_exception.flash.resolved"), "success")
    except VeeExceptionActionError as exc:
        session.rollback()
        flash(translate_vee_exception_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_vee_exception_redirect(vee_exception_id)))


@bp.post("/vee-exceptions/<int:vee_exception_id>/re-evaluate")
def reevaluate_vee_exception_view(vee_exception_id: int):
    session = get_session()
    current_user = get_current_user()
    assert current_user is not None
    try:
        summary = reevaluate_vee_exception_and_replay(
            session,
            vee_exception_id,
            reevaluated_by=current_user.login_id,
            reevaluated_by_user_account_id=current_user.id,
            operator_memo=request.form.get("operator_memo"),
        )
        session.commit()
        _store_vee_replay_summary(summary)
        flash(translate("vee_exception.flash.re_evaluated"), "success")
    except VeeExceptionActionError as exc:
        session.rollback()
        flash(translate_vee_exception_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_vee_exception_redirect(vee_exception_id)))


@bp.post("/vee-exceptions/<int:vee_exception_id>/estimate")
def estimate_vee_exception_view(vee_exception_id: int):
    session = get_session()
    current_user = get_current_user()
    assert current_user is not None
    try:
        summary = apply_estimation_from_vee_exception(
            session,
            vee_exception_id,
            strategy_code=request.form.get("strategy_code") or "",
            estimated_by=current_user.login_id,
            estimated_by_user_account_id=current_user.id,
            operator_memo=request.form.get("operator_memo"),
        )
        session.commit()
        _store_estimation_summary(summary)
        if summary.estimation_status == "applied":
            flash(translate("vee_exception.flash.estimated"), "success")
        elif summary.estimation_status == "blocked":
            flash(translate("vee_exception.flash.estimation_blocked"), "warning")
        else:
            flash(translate("vee_exception.flash.estimation_failed"), "danger")
    except EstimationActionError as exc:
        session.rollback()
        flash(translate_estimation_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_vee_exception_redirect(vee_exception_id)))


@bp.post("/vee-exceptions/<int:vee_exception_id>/estimate-synthetic-missing-interval")
def estimate_synthetic_missing_interval_vee_exception_view(vee_exception_id: int):
    session = get_session()
    current_user = get_current_user()
    assert current_user is not None
    try:
        summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
            session,
            vee_exception_id,
            strategy_code=request.form.get("strategy_code") or "",
            estimated_by=current_user.login_id,
            estimated_by_user_account_id=current_user.id,
            operator_memo=request.form.get("operator_memo"),
        )
        session.commit()
        _store_estimation_summary(summary)
        if summary.estimation_status == "applied":
            flash(translate("vee_exception.flash.synthetic_estimated"), "success")
        elif summary.estimation_status == "blocked":
            flash(translate("vee_exception.flash.synthetic_estimation_blocked"), "warning")
        else:
            flash(translate("vee_exception.flash.synthetic_estimation_failed"), "danger")
    except EstimationActionError as exc:
        session.rollback()
        flash(translate_estimation_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_vee_exception_redirect(vee_exception_id)))


@bp.post("/vee-exceptions/<int:vee_exception_id>/manual-edit")
def manual_edit_vee_exception_view(vee_exception_id: int):
    session = get_session()
    try:
        summary = apply_manual_edit_from_vee_exception(
            session,
            vee_exception_id,
            edited_value=request.form.get("edited_value"),
            edited_quality_code=request.form.get("edited_quality_code"),
            edited_status_code=request.form.get("edited_status_code"),
            reason_code=request.form.get("reason_code") or "",
            edited_by="operator_ui",
            operator_memo=request.form.get("operator_memo"),
        )
        session.commit()
        _store_manual_edit_summary(summary)
        if summary.edit_status == "applied":
            flash(translate("vee_exception.flash.manually_edited"), "success")
        elif summary.edit_status == "blocked":
            flash(translate("vee_exception.flash.manual_edit_blocked"), "warning")
        else:
            flash(translate("vee_exception.flash.manual_edit_failed"), "danger")
    except ManualEditActionError as exc:
        session.rollback()
        flash(translate_manual_edit_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_vee_exception_redirect(vee_exception_id)))


@bp.get("/ingest-batches")
def ingest_batches():
    session = get_session()
    try:
        filters = build_ingest_batch_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_ingest_batch_filters({})

    rows = list_ingest_batches(session, filters)
    return render_template("ingest_batches.html", rows=rows, filters=filters)


@bp.get("/canonical-measurements")
def canonical_measurements():
    session = get_session()
    try:
        filters = build_canonical_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_canonical_filters({})

    rows = list_canonical_measurements(session, filters)
    return render_template("canonical_measurements.html", rows=rows, filters=filters)


@bp.post("/canonical-measurements/promote-final")
def promote_canonical_measurements():
    session = get_session()
    try:
        filters = build_canonical_filters(request.form)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        return redirect(url_for("web.canonical_measurements", lang=get_locale()))

    try:
        summary = finalize_canonical_measurements(
            session,
            batch_id=filters.batch_id,
            meter_id=filters.meter_id,
            date_from=filters.date_from,
            date_to=filters.date_to,
            trigger_type="operator",
        )
        session.commit()
    except Exception:
        session.rollback()
        flash(translate("finalization.error.unexpected"), "danger")
        return redirect(url_for("web.canonical_measurements", **_canonical_filters_to_query_args(filters)))

    result_code = _finalization_result_code(summary)
    category = "danger" if result_code == "finalization_completed_with_skips" else "success"
    flash(
        translate_finalization_result(
            result_code,
            candidates=summary.candidates,
            finalized=summary.finalized,
            skipped_existing=summary.skipped_existing,
            skipped_not_well_formed=summary.skipped_not_well_formed,
        ),
        category,
    )
    return redirect(url_for("web.canonical_measurements", **_canonical_filters_to_query_args(filters)))


@bp.get("/final-measurements")
def final_measurements():
    session = get_session()
    try:
        filters = build_final_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_final_filters({})

    rows = list_final_measurements(session, filters)
    return render_template("final_measurements.html", rows=rows, filters=filters)


@bp.get("/usage-transactions")
def usage_transactions():
    session = get_session()
    try:
        filters = build_usage_transaction_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_usage_transaction_filters({})

    rows = list_usage_transactions(session, filters)
    return render_template("usage_transactions.html", rows=rows, filters=filters)


@bp.get("/usage-transactions/<int:usage_transaction_id>")
def usage_transaction_detail(usage_transaction_id: int):
    session = get_session()
    detail = get_usage_transaction_detail_context(session, usage_transaction_id)
    if detail is None:
        abort(404)

    return render_template("usage_transaction_detail.html", detail=detail)


@bp.get("/bill-determinants")
def bill_determinants():
    session = get_session()
    try:
        filters = build_bill_determinant_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_bill_determinant_filters({})

    rows = list_bill_determinants(session, filters)
    return render_template("bill_determinants.html", rows=rows, filters=filters)


@bp.get("/bill-determinants/<int:bill_determinant_id>")
def bill_determinant_detail(bill_determinant_id: int):
    session = get_session()
    detail = get_bill_determinant_detail_context(session, bill_determinant_id)
    if detail is None:
        abort(404)

    return render_template("bill_determinant_detail.html", detail=detail)


@bp.get("/bill-charges")
def bill_charges():
    session = get_session()
    try:
        filters = build_bill_charge_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_bill_charge_filters({})

    rows = list_bill_charges(session, filters)
    return render_template("bill_charges.html", rows=rows, filters=filters)


@bp.get("/bill-charges/<int:bill_charge_id>")
def bill_charge_detail(bill_charge_id: int):
    session = get_session()
    detail = get_bill_charge_detail_context(session, bill_charge_id)
    if detail is None:
        abort(404)

    return render_template("bill_charge_detail.html", detail=detail)


@bp.get("/manual-edit-audits")
def manual_edit_audits():
    session = get_session()
    try:
        filters = build_manual_edit_audit_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_manual_edit_audit_filters({})

    rows = list_manual_edit_audits(session, filters)
    return render_template(
        "manual_edit_audits.html",
        rows=rows,
        filters=filters,
        manual_edit_reason_codes=sorted(SUPPORTED_MANUAL_EDIT_REASON_CODES),
        correction_policy_reason_codes=SUPPORTED_CORRECTION_POLICY_REASON_CODES,
        correction_policy_event_context_types=SUPPORTED_CORRECTION_POLICY_EVENT_CONTEXT_TYPES,
    )


@bp.get("/estimation-audits")
def estimation_audits():
    session = get_session()
    try:
        filters = build_estimation_audit_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_estimation_audit_filters({})

    rows = list_estimation_audits(session, filters)
    return render_template(
        "estimation_audits.html",
        rows=rows,
        filters=filters,
        estimation_strategies=sorted(SUPPORTED_ESTIMATION_STRATEGIES),
        correction_policy_reason_codes=SUPPORTED_CORRECTION_POLICY_REASON_CODES,
        correction_policy_event_context_types=SUPPORTED_CORRECTION_POLICY_EVENT_CONTEXT_TYPES,
    )


@bp.get("/estimation-audits/<int:estimation_audit_id>")
def estimation_audit_detail(estimation_audit_id: int):
    session = get_session()
    detail = get_estimation_audit_detail_context(session, estimation_audit_id)
    if detail is None:
        abort(404)

    return render_template("estimation_audit_detail.html", detail=detail)


@bp.get("/manual-edit-audits/<int:manual_edit_audit_id>")
def manual_edit_audit_detail(manual_edit_audit_id: int):
    session = get_session()
    detail = get_manual_edit_audit_detail_context(session, manual_edit_audit_id)
    if detail is None:
        abort(404)

    return render_template("manual_edit_audit_detail.html", detail=detail)


@bp.get("/operational-events")
def operational_events():
    session = get_session()
    try:
        filters = build_operational_event_filters(request.args)
    except VisibilityFilterError as exc:
        flash(translate_visibility_error(exc.error_code, exc.fallback_message), "danger")
        filters = build_operational_event_filters({})

    rows = list_operational_events(session, filters)
    hes_system_options = session.scalars(
        select(HesSystem).order_by(HesSystem.display_name.asc(), HesSystem.id.asc())
    ).all()
    return render_template(
        "operational_events.html",
        rows=rows,
        filters=filters,
        hes_system_options=hes_system_options,
    )


@bp.get("/operational-events/<int:event_id>")
def operational_event_detail(event_id: int):
    session = get_session()
    detail = get_operational_event_detail_context(session, event_id)
    if detail is None:
        abort(404)

    return render_template("operational_event_detail.html", detail=detail)


def _adapter_redirect(adapter_instance_id: int) -> str:
    return url_for("web.adapter_detail", adapter_instance_id=adapter_instance_id, lang=get_locale())


def _adapter_form_defaults() -> dict[str, str]:
    return {
        "hes_system_id": "",
        "adapter_definition_id": "",
        "instance_code": "",
        "display_name": "",
        "source_system": "",
        "poll_interval_minutes": "",
        "batch_size": "",
        "secret_ref": "",
        "connection_config_masked": "",
        "landing_enabled": "",
    }


def _adapter_form_values() -> dict[str, str]:
    values = _adapter_form_defaults()
    for key in values:
        values[key] = request.form.get(key, "")
    return values


def _resolve_selected_hes_system(session, raw_hes_system_id: str | None) -> HesSystem | None:
    normalized = (raw_hes_system_id or "").strip()
    if not normalized:
        return None
    try:
        hes_system_id = int(normalized)
    except ValueError:
        return None
    return session.get(HesSystem, hes_system_id)


def _hes_system_form_defaults() -> dict[str, str]:
    return {
        "hes_code": "",
        "display_name": "",
        "vendor_name": "",
        "source_family": "hes",
        "default_delivery_mode": "",
        "status": "active",
        "timezone_name": "",
        "description": "",
        "connection_config_masked": "",
    }


def _hes_system_form_values() -> dict[str, str]:
    values = _hes_system_form_defaults()
    for key in values:
        values[key] = request.form.get(key, "")
    return values


def _hes_system_form_from_model(hes_system: HesSystem) -> dict[str, str]:
    import json

    return {
        "hes_code": hes_system.hes_code,
        "display_name": hes_system.display_name,
        "vendor_name": hes_system.vendor_name or "",
        "source_family": hes_system.source_family,
        "default_delivery_mode": hes_system.default_delivery_mode or "",
        "status": hes_system.status,
        "timezone_name": hes_system.timezone_name or "",
        "description": hes_system.description or "",
        "connection_config_masked": (
            json.dumps(hes_system.connection_config_masked, ensure_ascii=False, indent=2)
            if hes_system.connection_config_masked
            else ""
        ),
    }


@bp.get("/adapters")
def adapters():
    session = get_session()
    rows = list_adapter_instances(session)
    return render_template("adapters.html", rows=rows)


@bp.get("/hes-systems")
def hes_systems():
    session = get_session()
    rows = list_hes_systems(session)
    return render_template(
        "hes_systems.html",
        rows=rows,
        form_data=_hes_system_form_defaults(),
    )


@bp.post("/hes-systems")
@admin_required
def create_hes_system_view():
    session = get_session()
    form_data = _hes_system_form_values()
    try:
        hes_system = create_hes_system(
            session,
            hes_code=form_data["hes_code"],
            display_name=form_data["display_name"],
            vendor_name=form_data["vendor_name"],
            source_family=form_data["source_family"],
            default_delivery_mode=form_data["default_delivery_mode"],
            status=form_data["status"],
            timezone_name=form_data["timezone_name"],
            description=form_data["description"],
            connection_config_masked=form_data["connection_config_masked"],
        )
        session.commit()
        flash(translate("hes_system.flash.created"), "success")
        return redirect(url_for("web.hes_system_detail", hes_system_id=hes_system.id, lang=get_locale()))
    except HesSystemValidationError as exc:
        session.rollback()
        flash(translate_hes_system_error(exc.error_code, exc.fallback_message), "danger")
        rows = list_hes_systems(session)
        return render_template(
            "hes_systems.html",
            rows=rows,
            form_data=form_data,
        )


@bp.get("/hes-systems/<int:hes_system_id>")
def hes_system_detail(hes_system_id: int):
    session = get_session()
    detail = get_hes_system_detail(session, hes_system_id)
    if detail is None:
        abort(404)
    return render_template(
        "hes_system_detail.html",
        detail=detail,
        form_data=_hes_system_form_from_model(detail.hes_system),
    )


@bp.get("/hes-systems/<int:hes_system_id>/meter-references")
def hes_meter_references(hes_system_id: int):
    session = get_session()
    comparison_status = (request.args.get("comparison_status") or "").strip() or None
    meter_query = (request.args.get("meter_query") or "").strip() or None
    result = list_hes_meter_reference_comparisons(
        session,
        hes_system_id=hes_system_id,
        comparison_status=comparison_status,
        meter_query=meter_query,
    )
    if result is None:
        abort(404)

    hes_system, rows, summary = result
    return render_template(
        "hes_meter_references.html",
        hes_system=hes_system,
        rows=rows,
        summary=summary,
        form_data={
            "comparison_status": comparison_status or "",
            "meter_query": meter_query or "",
        },
    )


@bp.post("/hes-systems/<int:hes_system_id>")
@admin_required
def update_hes_system_view(hes_system_id: int):
    session = get_session()
    hes_system = session.get(HesSystem, hes_system_id)
    if hes_system is None:
        abort(404)

    form_data = _hes_system_form_values()
    try:
        update_hes_system(
            session,
            hes_system,
            hes_code=form_data["hes_code"],
            display_name=form_data["display_name"],
            vendor_name=form_data["vendor_name"],
            source_family=form_data["source_family"],
            default_delivery_mode=form_data["default_delivery_mode"],
            status=form_data["status"],
            timezone_name=form_data["timezone_name"],
            description=form_data["description"],
            connection_config_masked=form_data["connection_config_masked"],
        )
        session.commit()
        flash(translate("hes_system.flash.updated"), "success")
        return redirect(url_for("web.hes_system_detail", hes_system_id=hes_system.id, lang=get_locale()))
    except HesSystemValidationError as exc:
        session.rollback()
        flash(translate_hes_system_error(exc.error_code, exc.fallback_message), "danger")
        detail = get_hes_system_detail(session, hes_system_id)
        if detail is None:
            abort(404)
        return render_template(
            "hes_system_detail.html",
            detail=detail,
            form_data=form_data,
        )


@bp.get("/adapters/new")
@bp.get("/hes-systems/<int:hes_system_id>/adapters/new")
def new_adapter(hes_system_id: int | None = None):
    session = get_session()
    definitions = list_active_adapter_definitions(session)
    selected_hes_system = None
    if hes_system_id is not None:
        selected_hes_system = session.get(HesSystem, hes_system_id)
        if selected_hes_system is None:
            abort(404)
    elif request.args.get("hes_system_id"):
        selected_hes_system = _resolve_selected_hes_system(session, request.args.get("hes_system_id"))
        if selected_hes_system is None:
            flash(translate_hes_system_error("hes_system_not_found", "The selected HES system does not exist."), "danger")

    form_data = _adapter_form_defaults()
    if selected_hes_system is not None:
        form_data["hes_system_id"] = str(selected_hes_system.id)
        form_data["source_system"] = selected_hes_system.hes_code
    return render_template(
        "adapter_new.html",
        definitions=definitions,
        form_data=form_data,
        selected_hes_system=selected_hes_system,
    )


@bp.post("/adapters")
@admin_required
def create_adapter_view():
    session = get_session()
    definitions = list_active_adapter_definitions(session)
    form_data = _adapter_form_values()
    selected_hes_system = _resolve_selected_hes_system(session, form_data["hes_system_id"])

    try:
        instance = create_adapter_instance(
            session,
            adapter_definition_id=form_data["adapter_definition_id"],
            hes_system_id=form_data["hes_system_id"],
            instance_code=form_data["instance_code"],
            display_name=form_data["display_name"],
            source_system=form_data["source_system"],
            poll_interval_minutes=form_data["poll_interval_minutes"],
            batch_size=form_data["batch_size"],
            landing_enabled=request.form.get("landing_enabled") == "on",
            secret_ref=form_data["secret_ref"],
            connection_config_masked=form_data["connection_config_masked"],
        )
        session.commit()
        flash(translate("adapter.flash.created"), "success")
        return redirect(_adapter_redirect(instance.id))
    except AdapterValidationError as exc:
        session.rollback()
        flash(translate_adapter_error(exc.error_code, exc.fallback_message), "danger")
        return render_template(
            "adapter_new.html",
            definitions=definitions,
            form_data=form_data,
            selected_hes_system=selected_hes_system,
        )


@bp.get("/adapters/<int:adapter_instance_id>")
def adapter_detail(adapter_instance_id: int):
    session = get_session()
    detail = get_adapter_instance_detail(session, adapter_instance_id)
    if detail is None:
        abort(404)
    return render_template("adapter_detail.html", detail=detail)


@bp.post("/adapters/<int:adapter_instance_id>/enable")
@admin_required
def enable_adapter_view(adapter_instance_id: int):
    session = get_session()
    instance = session.get(AdapterInstance, adapter_instance_id)
    if instance is None:
        abort(404)

    try:
        update_adapter_admin_state(session, instance, "enabled")
        session.commit()
        flash(translate("adapter.flash.enabled"), "success")
    except AdapterValidationError as exc:
        session.rollback()
        flash(translate_adapter_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_adapter_redirect(adapter_instance_id)))


@bp.post("/adapters/<int:adapter_instance_id>/pause")
@admin_required
def pause_adapter_view(adapter_instance_id: int):
    session = get_session()
    instance = session.get(AdapterInstance, adapter_instance_id)
    if instance is None:
        abort(404)

    try:
        update_adapter_admin_state(session, instance, "paused")
        session.commit()
        flash(translate("adapter.flash.paused"), "success")
    except AdapterValidationError as exc:
        session.rollback()
        flash(translate_adapter_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_adapter_redirect(adapter_instance_id)))


@bp.post("/adapters/<int:adapter_instance_id>/run-once")
@admin_required
def run_adapter_once_view(adapter_instance_id: int):
    session = get_session()
    instance = session.get(AdapterInstance, adapter_instance_id)
    if instance is None:
        abort(404)

    try:
        queue_adapter_run_once(session, instance)
        session.commit()
        flash(translate("adapter.flash.run_queued"), "success")
    except AdapterValidationError as exc:
        session.rollback()
        flash(translate_adapter_error(exc.error_code, exc.fallback_message), "danger")

    return redirect(_safe_next_url(_adapter_redirect(adapter_instance_id)))


@bp.get("/master-data")
def master_data():
    session = get_session()
    service_points = session.scalars(
        select(ServicePoint).order_by(ServicePoint.id.desc()).limit(100)
    ).all()
    devices = session.scalars(
        select(Device).options(joinedload(Device.service_point)).order_by(Device.id.desc()).limit(100)
    ).all()
    components = session.scalars(
        select(MeasuringComponent)
        .options(joinedload(MeasuringComponent.device), joinedload(MeasuringComponent.service_point))
        .order_by(MeasuringComponent.id.desc())
        .limit(100)
    ).all()
    installations = session.scalars(
        select(InstallationHistory)
        .options(joinedload(InstallationHistory.device), joinedload(InstallationHistory.service_point))
        .order_by(InstallationHistory.id.desc())
        .limit(100)
    ).all()
    billing_context_rows = session.scalars(
        select(ServicePointBillingContext)
        .options(joinedload(ServicePointBillingContext.service_point))
        .order_by(
            ServicePointBillingContext.is_current.desc(),
            ServicePointBillingContext.effective_from.desc(),
            ServicePointBillingContext.id.desc(),
        )
        .limit(200)
    ).all()
    tariff_assignment_rows = session.scalars(
        select(ServicePointTariffAssignment)
        .options(joinedload(ServicePointTariffAssignment.service_point))
        .order_by(
            ServicePointTariffAssignment.is_current.desc(),
            ServicePointTariffAssignment.effective_from.desc(),
            ServicePointTariffAssignment.id.desc(),
        )
        .limit(200)
    ).all()
    prefill_data = {
        "source_system": (request.args.get("prefill_source_system") or "HES").strip() or "HES",
        "external_meter_id": (request.args.get("prefill_external_meter_id") or "").strip(),
        "external_channel_id": (request.args.get("prefill_external_channel_id") or "").strip(),
        "device_id": (request.args.get("prefill_device_id") or "").strip(),
        "service_point_id": (request.args.get("prefill_service_point_id") or "").strip(),
    }
    prefill_hes_meter_references = list_prefill_hes_meter_references(
        session,
        source_system=prefill_data["source_system"],
        external_meter_id=prefill_data["external_meter_id"],
    )
    return render_template(
        "master_data.html",
        service_points=service_points,
        devices=devices,
        rows=components,
        installations=installations,
        billing_context_rows=billing_context_rows,
        tariff_assignment_rows=tariff_assignment_rows,
        prefill_data=prefill_data,
        prefill_hes_meter_references=prefill_hes_meter_references,
        format_local_datetime=_format_datetime_local,
    )


def _master_data_redirect(fragment: str) -> str:
    return f"{url_for('web.master_data', lang=get_locale())}#{fragment}"


def _flash_master_data_success(message_key: str) -> None:
    flash(translate(message_key), "success")


def _flash_master_data_error(exc: MasterDataValidationError) -> None:
    flash(translate_master_data_error(exc.error_code, exc.fallback_message), "danger")


def _sync_hes_meter_reference_alerts_for_source_system(session, source_system: str | None) -> None:
    normalized = (source_system or "").strip()
    if not normalized:
        return

    hes_system = session.scalar(
        select(HesSystem).where(HesSystem.hes_code == normalized).limit(1)
    )
    if hes_system is None:
        return

    sync_hes_meter_reference_alerts(session, hes_system_id=hes_system.id)


def _flash_installation_error(exc: InstallationValidationError) -> None:
    flash(translate_master_data_error(exc.error_code, exc.fallback_message), "danger")


@bp.post("/master-data/service-points")
@admin_required
def create_service_point_view():
    session = get_session()
    try:
        create_service_point(
            session,
            source_system=request.form.get("source_system"),
            external_id=request.form.get("external_id"),
            service_type=request.form.get("service_type"),
            name=request.form.get("name"),
            status=request.form.get("status"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.service_point_created")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("service-points"))


@bp.post("/master-data/service-points/<int:service_point_id>")
@admin_required
def update_service_point_view(service_point_id: int):
    session = get_session()
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        flash(
            translate_master_data_error(
                "service_point_not_found", "The selected service point does not exist."
            ),
            "danger",
        )
        return redirect(_master_data_redirect("service-points"))

    try:
        update_service_point(
            session,
            service_point,
            source_system=request.form.get("source_system"),
            external_id=request.form.get("external_id"),
            service_type=request.form.get("service_type"),
            name=request.form.get("name"),
            status=request.form.get("status"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.service_point_updated")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("service-points"))


@bp.post("/master-data/devices")
@admin_required
def create_device_view():
    session = get_session()
    try:
        device = create_device(
            session,
            source_system=request.form.get("source_system"),
            external_meter_id=request.form.get("external_meter_id"),
            serial_number=request.form.get("serial_number"),
            service_point_id=request.form.get("service_point_id"),
            status=request.form.get("status"),
        )
        _sync_hes_meter_reference_alerts_for_source_system(session, device.source_system)
        session.commit()
        _flash_master_data_success("master_data.flash.device_created")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("devices"))


@bp.post("/master-data/devices/<int:device_id>")
@admin_required
def update_device_view(device_id: int):
    session = get_session()
    device = session.get(Device, device_id)
    if device is None:
        flash(
            translate_master_data_error("device_not_found", "The selected device does not exist."),
            "danger",
        )
        return redirect(_master_data_redirect("devices"))

    try:
        update_device(
            session,
            device,
            source_system=request.form.get("source_system"),
            external_meter_id=request.form.get("external_meter_id"),
            serial_number=request.form.get("serial_number"),
            service_point_id=request.form.get("service_point_id"),
            status=request.form.get("status"),
        )
        _sync_hes_meter_reference_alerts_for_source_system(session, device.source_system)
        session.commit()
        _flash_master_data_success("master_data.flash.device_updated")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("devices"))


@bp.post("/master-data/components")
@admin_required
def create_component_view():
    session = get_session()
    try:
        component = create_measuring_component(
            session,
            source_system=request.form.get("source_system"),
            external_channel_id=request.form.get("external_channel_id"),
            unit_of_measure=request.form.get("unit_of_measure"),
            multiplier=request.form.get("multiplier"),
            status=request.form.get("status"),
            device_id=request.form.get("device_id"),
            service_point_id=request.form.get("service_point_id"),
        )
        _sync_hes_meter_reference_alerts_for_source_system(session, component.source_system)
        session.commit()
        _flash_master_data_success("master_data.flash.component_created")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("components"))


@bp.post("/master-data/components/<int:component_id>")
@admin_required
def update_component_view(component_id: int):
    session = get_session()
    component = session.get(MeasuringComponent, component_id)
    if component is None:
        flash(
            translate_master_data_error(
                "component_not_found", "The selected measuring component does not exist."
            ),
            "danger",
        )
        return redirect(_master_data_redirect("components"))

    try:
        update_measuring_component(
            session,
            component,
            source_system=request.form.get("source_system"),
            external_channel_id=request.form.get("external_channel_id"),
            unit_of_measure=request.form.get("unit_of_measure"),
            multiplier=request.form.get("multiplier"),
            status=request.form.get("status"),
            device_id=request.form.get("device_id"),
            service_point_id=request.form.get("service_point_id"),
        )
        _sync_hes_meter_reference_alerts_for_source_system(session, component.source_system)
        session.commit()
        _flash_master_data_success("master_data.flash.component_updated")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("components"))


@bp.post("/master-data/installations")
@admin_required
def create_installation_view():
    session = get_session()
    try:
        installation = create_installation_history(
            session,
            device_id=request.form.get("device_id"),
            service_point_id=request.form.get("service_point_id"),
            installed_at=request.form.get("installed_at"),
            removed_at=request.form.get("removed_at"),
            status=request.form.get("status"),
        )
        _sync_hes_meter_reference_alerts_for_source_system(
            session, installation.device.source_system
        )
        session.commit()
        _flash_master_data_success("master_data.flash.installation_created")
    except InstallationValidationError as exc:
        session.rollback()
        _flash_installation_error(exc)

    return redirect(_master_data_redirect("installations"))


@bp.post("/master-data/installations/<int:installation_id>")
@admin_required
def update_installation_view(installation_id: int):
    session = get_session()
    installation = session.get(InstallationHistory, installation_id)
    if installation is None:
        flash(
            translate_master_data_error(
                "installation_not_found", "The selected installation history does not exist."
            ),
            "danger",
        )
        return redirect(_master_data_redirect("installations"))

    try:
        update_installation_history(
            session,
            installation,
            device_id=request.form.get("device_id"),
            service_point_id=request.form.get("service_point_id"),
            installed_at=request.form.get("installed_at"),
            removed_at=request.form.get("removed_at"),
            status=request.form.get("status"),
        )
        _sync_hes_meter_reference_alerts_for_source_system(
            session, installation.device.source_system
        )
        session.commit()
        _flash_master_data_success("master_data.flash.installation_updated")
    except InstallationValidationError as exc:
        session.rollback()
        _flash_installation_error(exc)

    return redirect(_master_data_redirect("installations"))


@bp.post("/master-data/billing-contexts")
@admin_required
def create_billing_context_view():
    session = get_session()
    try:
        create_billing_context(
            session,
            service_point_id=request.form.get("service_point_id"),
            timezone_name=request.form.get("timezone_name"),
            billing_cycle_mode=request.form.get("billing_cycle_mode"),
            billing_cycle_anchor_day=request.form.get("billing_cycle_anchor_day"),
            currency_code=request.form.get("currency_code"),
            effective_from=request.form.get("effective_from"),
            effective_to=request.form.get("effective_to"),
            source_system=request.form.get("source_system"),
            source_reference=request.form.get("source_reference"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.billing_context_created")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("billing-contexts"))


@bp.post("/master-data/billing-contexts/<int:billing_context_id>")
@admin_required
def update_billing_context_view(billing_context_id: int):
    session = get_session()
    billing_context = session.get(ServicePointBillingContext, billing_context_id)
    if billing_context is None:
        flash(
            translate_master_data_error(
                "billing_context_not_found",
                "The selected billing context does not exist.",
            ),
            "danger",
        )
        return redirect(_master_data_redirect("billing-contexts"))

    try:
        update_billing_context(
            session,
            billing_context,
            timezone_name=request.form.get("timezone_name"),
            billing_cycle_mode=request.form.get("billing_cycle_mode"),
            billing_cycle_anchor_day=request.form.get("billing_cycle_anchor_day"),
            currency_code=request.form.get("currency_code"),
            effective_from=request.form.get("effective_from"),
            effective_to=request.form.get("effective_to"),
            source_system=request.form.get("source_system"),
            source_reference=request.form.get("source_reference"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.billing_context_updated")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("billing-contexts"))


@bp.post("/master-data/tariff-assignments")
@admin_required
def create_tariff_assignment_view():
    session = get_session()
    try:
        create_tariff_assignment(
            session,
            service_point_id=request.form.get("service_point_id"),
            tariff_plan_code=request.form.get("tariff_plan_code"),
            tariff_version_code=request.form.get("tariff_version_code"),
            effective_from=request.form.get("effective_from"),
            effective_to=request.form.get("effective_to"),
            source_system=request.form.get("source_system"),
            source_reference=request.form.get("source_reference"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.tariff_assignment_created")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("tariff-assignments"))


@bp.post("/master-data/tariff-assignments/<int:tariff_assignment_id>")
@admin_required
def update_tariff_assignment_view(tariff_assignment_id: int):
    session = get_session()
    tariff_assignment = session.get(ServicePointTariffAssignment, tariff_assignment_id)
    if tariff_assignment is None:
        flash(
            translate_master_data_error(
                "tariff_assignment_not_found",
                "The selected tariff assignment does not exist.",
            ),
            "danger",
        )
        return redirect(_master_data_redirect("tariff-assignments"))

    try:
        update_tariff_assignment(
            session,
            tariff_assignment,
            tariff_plan_code=request.form.get("tariff_plan_code"),
            tariff_version_code=request.form.get("tariff_version_code"),
            effective_from=request.form.get("effective_from"),
            effective_to=request.form.get("effective_to"),
            source_system=request.form.get("source_system"),
            source_reference=request.form.get("source_reference"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.tariff_assignment_updated")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("tariff-assignments"))
