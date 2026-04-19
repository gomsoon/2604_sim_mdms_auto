from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.i18n import normalize_locale
from app.models import IngestBatch


SUPPORTED_CONTRACT_VERSION = "v1"


@dataclass(slots=True)
class IngestContractError(ValueError):
    error_code: str
    fallback_message: str
    status_code: int = 400
    response_locale: str | None = None

    def __str__(self) -> str:
        return self.fallback_message


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = str(value).strip()
    return stripped or None


def parse_datetime(value: Any, *, require_timezone: bool = False) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)

    if require_timezone and parsed.tzinfo is None:
        raise ValueError("Timezone information is required.")

    return parsed


def coerce_numeric(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid numeric measurements.")
    return float(value)


def detect_response_locale(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    locale = payload.get("locale")
    if locale is None:
        return None

    normalized = normalize_locale(str(locale))
    return normalized


def validate_ingest_envelope(
    session: Session,
    payload: dict[str, Any],
    *,
    record_type: str,
) -> tuple[str, str, datetime | None]:
    response_locale = detect_response_locale(payload)

    contract_version = _normalize_text(payload.get("contract_version"))
    if contract_version != SUPPORTED_CONTRACT_VERSION:
        raise IngestContractError(
            "unsupported_contract_version",
            "Contract version must be v1.",
            response_locale=response_locale,
        )

    source_system = _normalize_text(payload.get("source_system"))
    if source_system is None:
        raise IngestContractError(
            "missing_source_system",
            "Source system is required.",
            response_locale=response_locale,
        )

    locale = payload.get("locale")
    if locale is not None and normalize_locale(str(locale)) is None:
        raise IngestContractError(
            "invalid_locale",
            "Locale must be en or ko.",
            response_locale=response_locale,
        )

    batch_reference = _normalize_text(payload.get("batch_id")) or _normalize_text(
        payload.get("message_id")
    )
    if batch_reference is None:
        raise IngestContractError(
            "missing_envelope_identifier",
            "Either batch_id or message_id is required.",
            response_locale=response_locale,
        )

    try:
        received_at = parse_datetime(payload.get("received_at"), require_timezone=True)
    except ValueError as exc:
        raise IngestContractError(
            "invalid_timestamp",
            "Timestamps must use ISO 8601 format with timezone information.",
            response_locale=response_locale,
        ) from exc

    existing_batch = session.scalar(
        select(IngestBatch)
        .where(
            IngestBatch.source_system == source_system,
            IngestBatch.batch_id == batch_reference,
            IngestBatch.record_type == record_type,
        )
        .limit(1)
    )
    if existing_batch is not None:
        raise IngestContractError(
            "duplicate_ingest_request",
            "A request with the same source system and envelope identifier already exists.",
            status_code=409,
            response_locale=response_locale,
        )

    return source_system, batch_reference, received_at
