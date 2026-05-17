from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, MeasuringComponent, ServicePoint


VALID_STATUSES = {"active", "inactive"}


@dataclass(slots=True)
class MasterDataValidationError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = str(value).strip()
    return stripped or None


def _require_text(value: str | None, error_code: str, fallback_message: str) -> str:
    normalized = _normalize_text(value)
    if normalized is None:
        raise MasterDataValidationError(error_code, fallback_message)
    return normalized


def _validate_status(value: str | None) -> str:
    status = _require_text(value, "missing_status", "Status is required.").lower()
    if status not in VALID_STATUSES:
        raise MasterDataValidationError("invalid_status", "Status must be active or inactive.")
    return status


def _validate_multiplier(value: str | float | int | None) -> float:
    if value in (None, ""):
        raise MasterDataValidationError("missing_multiplier", "Multiplier is required.")

    try:
        multiplier = float(value)
    except (TypeError, ValueError) as exc:
        raise MasterDataValidationError(
            "invalid_multiplier", "Multiplier must be a valid number."
        ) from exc

    if multiplier <= 0:
        raise MasterDataValidationError(
            "invalid_multiplier", "Multiplier must be greater than zero."
        )

    return multiplier


def _load_service_point(session: Session, service_point_id: int) -> ServicePoint:
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        raise MasterDataValidationError(
            "service_point_not_found", "The selected service point does not exist."
        )
    return service_point


def _load_device(session: Session, device_id: int) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise MasterDataValidationError("device_not_found", "The selected device does not exist.")
    return device


def _ensure_unique_service_point_external_id(
    session: Session, external_id: str, *, exclude_id: int | None = None
) -> None:
    statement = select(ServicePoint).where(ServicePoint.external_id == external_id)
    if exclude_id is not None:
        statement = statement.where(ServicePoint.id != exclude_id)

    duplicate = session.scalar(statement.limit(1))
    if duplicate is not None:
        raise MasterDataValidationError(
            "duplicate_service_point_external_id",
            "A service point with the same external identifier already exists.",
        )


def _ensure_unique_device_external_meter_id(
    session: Session, external_meter_id: str, *, exclude_id: int | None = None
) -> None:
    statement = select(Device).where(Device.external_meter_id == external_meter_id)
    if exclude_id is not None:
        statement = statement.where(Device.id != exclude_id)

    duplicate = session.scalar(statement.limit(1))
    if duplicate is not None:
        raise MasterDataValidationError(
            "duplicate_device_external_meter_id",
            "A device with the same external meter identifier already exists.",
        )


def _ensure_unique_component_channel(
    session: Session,
    *,
    source_system: str,
    external_channel_id: str,
    device_id: int,
    exclude_id: int | None = None,
) -> None:
    statement = (
        select(MeasuringComponent)
        .where(MeasuringComponent.source_system == source_system)
        .where(MeasuringComponent.external_channel_id == external_channel_id)
        .where(MeasuringComponent.device_id == device_id)
    )
    if exclude_id is not None:
        statement = statement.where(MeasuringComponent.id != exclude_id)

    duplicate = session.scalar(statement.limit(1))
    if duplicate is not None:
        raise MasterDataValidationError(
            "duplicate_component_channel",
            "A measuring component with the same source, device, and external channel already exists.",
        )


def create_service_point(
    session: Session,
    *,
    source_system: str | None,
    external_id: str | None,
    service_type: str | None,
    name: str | None,
    status: str | None,
    created_by_user_account_id: int | None = None,
) -> ServicePoint:
    normalized_source_system = _require_text(
        source_system, "missing_source_system", "Source system is required."
    )
    normalized_external_id = _require_text(
        external_id, "missing_external_id", "External identifier is required."
    )
    normalized_service_type = _require_text(
        service_type, "missing_service_type", "Service type is required."
    )
    normalized_status = _validate_status(status)

    _ensure_unique_service_point_external_id(session, normalized_external_id)

    service_point = ServicePoint(
        source_system=normalized_source_system,
        external_id=normalized_external_id,
        service_type=normalized_service_type,
        name=_normalize_text(name),
        status=normalized_status,
        created_by_user_account_id=created_by_user_account_id,
        updated_by_user_account_id=created_by_user_account_id,
    )
    session.add(service_point)
    session.flush()
    return service_point


def update_service_point(
    session: Session,
    service_point: ServicePoint,
    *,
    source_system: str | None,
    external_id: str | None,
    service_type: str | None,
    name: str | None,
    status: str | None,
    updated_by_user_account_id: int | None = None,
) -> ServicePoint:
    normalized_source_system = _require_text(
        source_system, "missing_source_system", "Source system is required."
    )
    normalized_external_id = _require_text(
        external_id, "missing_external_id", "External identifier is required."
    )
    normalized_service_type = _require_text(
        service_type, "missing_service_type", "Service type is required."
    )
    normalized_status = _validate_status(status)

    _ensure_unique_service_point_external_id(
        session, normalized_external_id, exclude_id=service_point.id
    )

    service_point.source_system = normalized_source_system
    service_point.external_id = normalized_external_id
    service_point.service_type = normalized_service_type
    service_point.name = _normalize_text(name)
    service_point.status = normalized_status
    service_point.updated_by_user_account_id = updated_by_user_account_id
    session.flush()
    return service_point


def create_device(
    session: Session,
    *,
    source_system: str | None,
    external_meter_id: str | None,
    serial_number: str | None,
    service_point_id: int | str | None,
    status: str | None,
    created_by_user_account_id: int | None = None,
) -> Device:
    normalized_source_system = _require_text(
        source_system, "missing_source_system", "Source system is required."
    )
    normalized_external_meter_id = _require_text(
        external_meter_id, "missing_external_meter_id", "External meter identifier is required."
    )
    normalized_status = _validate_status(status)

    if service_point_id in (None, ""):
        raise MasterDataValidationError(
            "missing_service_point_id", "Service point selection is required."
        )

    service_point = _load_service_point(session, int(service_point_id))
    _ensure_unique_device_external_meter_id(session, normalized_external_meter_id)

    device = Device(
        source_system=normalized_source_system,
        external_meter_id=normalized_external_meter_id,
        serial_number=_normalize_text(serial_number),
        status=normalized_status,
        service_point_id=service_point.id,
        created_by_user_account_id=created_by_user_account_id,
        updated_by_user_account_id=created_by_user_account_id,
    )
    session.add(device)
    session.flush()
    return device


def update_device(
    session: Session,
    device: Device,
    *,
    source_system: str | None,
    external_meter_id: str | None,
    serial_number: str | None,
    service_point_id: int | str | None,
    status: str | None,
    updated_by_user_account_id: int | None = None,
) -> Device:
    normalized_source_system = _require_text(
        source_system, "missing_source_system", "Source system is required."
    )
    normalized_external_meter_id = _require_text(
        external_meter_id, "missing_external_meter_id", "External meter identifier is required."
    )
    normalized_status = _validate_status(status)

    if service_point_id in (None, ""):
        raise MasterDataValidationError(
            "missing_service_point_id", "Service point selection is required."
        )

    service_point = _load_service_point(session, int(service_point_id))
    _ensure_unique_device_external_meter_id(
        session, normalized_external_meter_id, exclude_id=device.id
    )

    if device.measuring_components and any(
        component.service_point_id != service_point.id for component in device.measuring_components
    ):
        raise MasterDataValidationError(
            "device_service_point_component_mismatch",
            "The selected service point conflicts with existing measuring component mappings.",
        )

    device.source_system = normalized_source_system
    device.external_meter_id = normalized_external_meter_id
    device.serial_number = _normalize_text(serial_number)
    device.service_point_id = service_point.id
    device.status = normalized_status
    device.updated_by_user_account_id = updated_by_user_account_id
    session.flush()
    return device


def create_measuring_component(
    session: Session,
    *,
    source_system: str | None,
    external_channel_id: str | None,
    unit_of_measure: str | None,
    multiplier: str | float | int | None,
    status: str | None,
    device_id: int | str | None,
    service_point_id: int | str | None,
    created_by_user_account_id: int | None = None,
) -> MeasuringComponent:
    normalized_source_system = _require_text(
        source_system, "missing_source_system", "Source system is required."
    )
    normalized_external_channel_id = _require_text(
        external_channel_id, "missing_external_channel_id", "External channel identifier is required."
    )
    normalized_unit_of_measure = _require_text(
        unit_of_measure, "missing_unit_of_measure", "Unit of measure is required."
    )
    normalized_status = _validate_status(status)
    normalized_multiplier = _validate_multiplier(multiplier)

    if device_id in (None, ""):
        raise MasterDataValidationError("missing_device_id", "Device selection is required.")
    if service_point_id in (None, ""):
        raise MasterDataValidationError(
            "missing_service_point_id", "Service point selection is required."
        )

    device = _load_device(session, int(device_id))
    service_point = _load_service_point(session, int(service_point_id))

    if device.service_point_id != service_point.id:
        raise MasterDataValidationError(
            "component_service_point_device_mismatch",
            "The selected service point does not match the device mapping.",
        )

    _ensure_unique_component_channel(
        session,
        source_system=normalized_source_system,
        external_channel_id=normalized_external_channel_id,
        device_id=device.id,
    )

    component = MeasuringComponent(
        source_system=normalized_source_system,
        external_channel_id=normalized_external_channel_id,
        unit_of_measure=normalized_unit_of_measure,
        multiplier=normalized_multiplier,
        status=normalized_status,
        device_id=device.id,
        service_point_id=service_point.id,
        created_by_user_account_id=created_by_user_account_id,
        updated_by_user_account_id=created_by_user_account_id,
    )
    session.add(component)
    session.flush()
    return component


def update_measuring_component(
    session: Session,
    component: MeasuringComponent,
    *,
    source_system: str | None,
    external_channel_id: str | None,
    unit_of_measure: str | None,
    multiplier: str | float | int | None,
    status: str | None,
    device_id: int | str | None,
    service_point_id: int | str | None,
    updated_by_user_account_id: int | None = None,
) -> MeasuringComponent:
    normalized_source_system = _require_text(
        source_system, "missing_source_system", "Source system is required."
    )
    normalized_external_channel_id = _require_text(
        external_channel_id, "missing_external_channel_id", "External channel identifier is required."
    )
    normalized_unit_of_measure = _require_text(
        unit_of_measure, "missing_unit_of_measure", "Unit of measure is required."
    )
    normalized_status = _validate_status(status)
    normalized_multiplier = _validate_multiplier(multiplier)

    if device_id in (None, ""):
        raise MasterDataValidationError("missing_device_id", "Device selection is required.")
    if service_point_id in (None, ""):
        raise MasterDataValidationError(
            "missing_service_point_id", "Service point selection is required."
        )

    device = _load_device(session, int(device_id))
    service_point = _load_service_point(session, int(service_point_id))

    if device.service_point_id != service_point.id:
        raise MasterDataValidationError(
            "component_service_point_device_mismatch",
            "The selected service point does not match the device mapping.",
        )

    _ensure_unique_component_channel(
        session,
        source_system=normalized_source_system,
        external_channel_id=normalized_external_channel_id,
        device_id=device.id,
        exclude_id=component.id,
    )

    component.source_system = normalized_source_system
    component.external_channel_id = normalized_external_channel_id
    component.unit_of_measure = normalized_unit_of_measure
    component.multiplier = normalized_multiplier
    component.status = normalized_status
    component.device_id = device.id
    component.service_point_id = service_point.id
    component.updated_by_user_account_id = updated_by_user_account_id
    session.flush()
    return component
