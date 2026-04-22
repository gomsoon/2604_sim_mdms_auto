from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db import get_session
from app.i18n import (
    translate_adapter_error,
    get_locale,
    translate_hes_system_error,
    translate,
    translate_operational_alert_error,
    translate_finalization_result,
    translate_master_data_error,
    translate_reprocess_error,
    translate_reprocess_result,
    translate_visibility_error,
)
from app.models import (
    AdapterInstance,
    Device,
    HesEventRaw,
    HesReadRaw,
    HesSystem,
    MeasuringComponent,
    ServicePoint,
    InstallationHistory,
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
from app.services.dashboard import build_dashboard_snapshot
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
    list_hes_systems,
    update_hes_system,
)
from app.services.master_data import (
    MasterDataValidationError,
    create_device,
    create_measuring_component,
    create_service_point,
    update_device,
    update_measuring_component,
    update_service_point,
)
from app.services.operational_events import (
    OperationalAlertError,
    acknowledge_operational_alert,
    close_operational_alert,
)
from app.services.visibility import (
    VisibilityFilterError,
    build_canonical_filters,
    build_final_filters,
    build_ingest_batch_filters,
    build_operational_event_filters,
    list_canonical_measurements,
    list_final_measurements,
    list_ingest_batches,
    list_operational_events,
)


bp = Blueprint("web", __name__)


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
    next_url = request.form.get("next")
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


@bp.post("/hes-systems/<int:hes_system_id>")
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
    return render_template(
        "master_data.html",
        service_points=service_points,
        devices=devices,
        rows=components,
        installations=installations,
    )


def _master_data_redirect(fragment: str) -> str:
    return f"{url_for('web.master_data', lang=get_locale())}#{fragment}"


def _flash_master_data_success(message_key: str) -> None:
    flash(translate(message_key), "success")


def _flash_master_data_error(exc: MasterDataValidationError) -> None:
    flash(translate_master_data_error(exc.error_code, exc.fallback_message), "danger")


def _flash_installation_error(exc: InstallationValidationError) -> None:
    flash(translate_master_data_error(exc.error_code, exc.fallback_message), "danger")


@bp.post("/master-data/service-points")
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
def create_device_view():
    session = get_session()
    try:
        create_device(
            session,
            source_system=request.form.get("source_system"),
            external_meter_id=request.form.get("external_meter_id"),
            serial_number=request.form.get("serial_number"),
            service_point_id=request.form.get("service_point_id"),
            status=request.form.get("status"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.device_created")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("devices"))


@bp.post("/master-data/devices/<int:device_id>")
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
        session.commit()
        _flash_master_data_success("master_data.flash.device_updated")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("devices"))


@bp.post("/master-data/components")
def create_component_view():
    session = get_session()
    try:
        create_measuring_component(
            session,
            source_system=request.form.get("source_system"),
            external_channel_id=request.form.get("external_channel_id"),
            unit_of_measure=request.form.get("unit_of_measure"),
            multiplier=request.form.get("multiplier"),
            status=request.form.get("status"),
            device_id=request.form.get("device_id"),
            service_point_id=request.form.get("service_point_id"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.component_created")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("components"))


@bp.post("/master-data/components/<int:component_id>")
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
        session.commit()
        _flash_master_data_success("master_data.flash.component_updated")
    except MasterDataValidationError as exc:
        session.rollback()
        _flash_master_data_error(exc)

    return redirect(_master_data_redirect("components"))


@bp.post("/master-data/installations")
def create_installation_view():
    session = get_session()
    try:
        create_installation_history(
            session,
            device_id=request.form.get("device_id"),
            service_point_id=request.form.get("service_point_id"),
            installed_at=request.form.get("installed_at"),
            removed_at=request.form.get("removed_at"),
            status=request.form.get("status"),
        )
        session.commit()
        _flash_master_data_success("master_data.flash.installation_created")
    except InstallationValidationError as exc:
        session.rollback()
        _flash_installation_error(exc)

    return redirect(_master_data_redirect("installations"))


@bp.post("/master-data/installations/<int:installation_id>")
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
        session.commit()
        _flash_master_data_success("master_data.flash.installation_updated")
    except InstallationValidationError as exc:
        session.rollback()
        _flash_installation_error(exc)

    return redirect(_master_data_redirect("installations"))
