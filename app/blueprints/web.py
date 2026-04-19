from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db import get_session
from app.i18n import (
    get_locale,
    translate,
    translate_master_data_error,
    translate_reprocess_error,
    translate_reprocess_result,
    translate_visibility_error,
)
from app.models import (
    Device,
    HesEventRaw,
    HesReadRaw,
    MeasuringComponent,
    ServicePoint,
    InstallationHistory,
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
from app.services.installations import (
    InstallationValidationError,
    create_installation_history,
    update_installation_history,
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
from app.services.visibility import (
    VisibilityFilterError,
    build_canonical_filters,
    build_ingest_batch_filters,
    list_canonical_measurements,
    list_ingest_batches,
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
    )


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
