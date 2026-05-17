from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, InstallationHistory, ServicePoint


VALID_INSTALLATION_STATUSES = {"installed", "removed"}


@dataclass(slots=True)
class InstallationValidationError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


def _parse_datetime(
    value: str | datetime | None,
    *,
    required_error_code: str,
    required_fallback_message: str,
    invalid_error_code: str,
    invalid_fallback_message: str,
    required: bool,
) -> datetime | None:
    if value in (None, ""):
        if required:
            raise InstallationValidationError(required_error_code, required_fallback_message)
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise InstallationValidationError(
                invalid_error_code, invalid_fallback_message
            ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_device(session: Session, device_id: int) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise InstallationValidationError("device_not_found", "The selected device does not exist.")
    return device


def _load_service_point(session: Session, service_point_id: int) -> ServicePoint:
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        raise InstallationValidationError(
            "service_point_not_found", "The selected service point does not exist."
        )
    return service_point


def _validate_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        raise InstallationValidationError("missing_status", "Status is required.")
    if normalized not in VALID_INSTALLATION_STATUSES:
        raise InstallationValidationError(
            "invalid_installation_status",
            "Installation status must be installed or removed.",
        )
    return normalized


def _validate_no_overlapping_open_installation(
    session: Session, device_id: int, *, exclude_id: int | None = None
) -> None:
    statement = select(InstallationHistory).where(
        InstallationHistory.device_id == device_id,
        InstallationHistory.status == "installed",
        InstallationHistory.removed_at.is_(None),
    )
    if exclude_id is not None:
        statement = statement.where(InstallationHistory.id != exclude_id)

    duplicate = session.scalar(statement.limit(1))
    if duplicate is not None:
        raise InstallationValidationError(
            "overlapping_open_installation",
            "Only one open installation is allowed per device.",
        )


def _validate_installation_window(
    session: Session,
    *,
    installed_at: datetime,
    removed_at: datetime | None,
    status: str,
    device_id: int,
    exclude_id: int | None = None,
) -> None:
    if removed_at is not None and removed_at < installed_at:
        raise InstallationValidationError(
            "removed_at_before_installed_at",
            "Removed time must be equal to or later than installed time.",
        )

    if status == "installed":
        if removed_at is not None:
            raise InstallationValidationError(
                "active_installation_cannot_have_removed_at",
                "An installed record cannot have removed time.",
            )
        _validate_no_overlapping_open_installation(session, device_id, exclude_id=exclude_id)
        return

    if removed_at is None:
        raise InstallationValidationError(
            "missing_removed_at",
            "Removed time is required when status is removed.",
        )


def create_installation_history(
    session: Session,
    *,
    device_id: int | str | None,
    service_point_id: int | str | None,
    installed_at: str | datetime | None,
    removed_at: str | datetime | None,
    status: str | None,
    created_by_user_account_id: int | None = None,
) -> InstallationHistory:
    if device_id in (None, ""):
        raise InstallationValidationError("missing_device_id", "Device selection is required.")
    if service_point_id in (None, ""):
        raise InstallationValidationError(
            "missing_service_point_id", "Service point selection is required."
        )

    device = _load_device(session, int(device_id))
    service_point = _load_service_point(session, int(service_point_id))
    normalized_status = _validate_status(status)
    normalized_installed_at = _parse_datetime(
        installed_at,
        required_error_code="missing_installed_at",
        required_fallback_message="Installed time is required.",
        invalid_error_code="invalid_installed_at",
        invalid_fallback_message="Installed time must be a valid ISO datetime.",
        required=True,
    )
    normalized_removed_at = _parse_datetime(
        removed_at,
        required_error_code="missing_removed_at",
        required_fallback_message="Removed time is required when status is removed.",
        invalid_error_code="invalid_removed_at",
        invalid_fallback_message="Removed time must be a valid ISO datetime.",
        required=False,
    )

    assert normalized_installed_at is not None
    _validate_installation_window(
        session,
        installed_at=normalized_installed_at,
        removed_at=normalized_removed_at,
        status=normalized_status,
        device_id=device.id,
    )

    installation = InstallationHistory(
        device_id=device.id,
        service_point_id=service_point.id,
        installed_at=normalized_installed_at,
        removed_at=normalized_removed_at,
        status=normalized_status,
        created_by_user_account_id=created_by_user_account_id,
        updated_by_user_account_id=created_by_user_account_id,
    )
    session.add(installation)
    session.flush()
    return installation


def update_installation_history(
    session: Session,
    installation: InstallationHistory,
    *,
    device_id: int | str | None,
    service_point_id: int | str | None,
    installed_at: str | datetime | None,
    removed_at: str | datetime | None,
    status: str | None,
    updated_by_user_account_id: int | None = None,
) -> InstallationHistory:
    if device_id in (None, ""):
        raise InstallationValidationError("missing_device_id", "Device selection is required.")
    if service_point_id in (None, ""):
        raise InstallationValidationError(
            "missing_service_point_id", "Service point selection is required."
        )

    device = _load_device(session, int(device_id))
    service_point = _load_service_point(session, int(service_point_id))
    normalized_status = _validate_status(status)
    normalized_installed_at = _parse_datetime(
        installed_at,
        required_error_code="missing_installed_at",
        required_fallback_message="Installed time is required.",
        invalid_error_code="invalid_installed_at",
        invalid_fallback_message="Installed time must be a valid ISO datetime.",
        required=True,
    )
    normalized_removed_at = _parse_datetime(
        removed_at,
        required_error_code="missing_removed_at",
        required_fallback_message="Removed time is required when status is removed.",
        invalid_error_code="invalid_removed_at",
        invalid_fallback_message="Removed time must be a valid ISO datetime.",
        required=False,
    )

    assert normalized_installed_at is not None
    _validate_installation_window(
        session,
        installed_at=normalized_installed_at,
        removed_at=normalized_removed_at,
        status=normalized_status,
        device_id=device.id,
        exclude_id=installation.id,
    )

    installation.device_id = device.id
    installation.service_point_id = service_point.id
    installation.installed_at = normalized_installed_at
    installation.removed_at = normalized_removed_at
    installation.status = normalized_status
    installation.updated_by_user_account_id = updated_by_user_account_id
    session.flush()
    return installation
