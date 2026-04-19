from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.ingest_contract import IngestContractError, detect_response_locale


DEFAULT_ADAPTER_KEY = "common_raw_v1"


@dataclass(frozen=True, slots=True)
class AdaptedIngestRecord:
    original_payload: dict[str, Any]
    normalized_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FieldAliasAdapter:
    adapter_key: str
    record_type: str
    collection_key: str
    field_aliases: dict[str, tuple[str, ...]]

    def adapt_records(self, payload: dict[str, Any]) -> list[AdaptedIngestRecord]:
        raw_items = payload.get(self.collection_key) or []
        if not isinstance(raw_items, list):
            raw_items = [raw_items]

        return [
            AdaptedIngestRecord(
                original_payload=_coerce_record_payload(item),
                normalized_payload=_normalize_item(_coerce_record_payload(item), self.field_aliases),
            )
            for item in raw_items
        ]


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = str(value).strip()
    return stripped or None


def _coerce_record_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    return {"_raw_item": item}


def _pick_alias_value(item: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for name in aliases:
        if name in item:
            return item.get(name)
    return None


def _normalize_item(
    item: dict[str, Any], field_aliases: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for common_field, aliases in field_aliases.items():
        normalized[common_field] = _pick_alias_value(item, aliases)
    return normalized


READ_ADAPTERS: dict[str, FieldAliasAdapter] = {
    DEFAULT_ADAPTER_KEY: FieldAliasAdapter(
        adapter_key=DEFAULT_ADAPTER_KEY,
        record_type="hes_read_raw",
        collection_key="reads",
        field_aliases={
            "meter_id": ("meter_id", "meter_identifier", "meter_no"),
            "channel_id": ("channel_id", "channel_identifier", "channel_no"),
            "measurement_ts": ("measurement_ts", "measured_at", "read_at", "read_time"),
            "value": ("value", "reading_value", "read_value"),
            "quality_code": ("quality_code", "quality", "quality_flag"),
            "status_code": ("status_code", "status", "status_flag"),
            "unit_of_measure": ("unit_of_measure", "unit", "uom"),
            "interval_size_minutes": ("interval_size_minutes", "interval_minutes"),
            "source_type": ("source_type", "reading_type"),
        },
    ),
    "legacy_hes_v1": FieldAliasAdapter(
        adapter_key="legacy_hes_v1",
        record_type="hes_read_raw",
        collection_key="reads",
        field_aliases={
            "meter_id": ("mtr_no",),
            "channel_id": ("chn_no",),
            "measurement_ts": ("read_time",),
            "value": ("read_value",),
            "quality_code": ("quality",),
            "status_code": ("status",),
            "unit_of_measure": ("uom",),
            "interval_size_minutes": ("interval_minutes",),
            "source_type": ("reading_type",),
        },
    ),
}

EVENT_ADAPTERS: dict[str, FieldAliasAdapter] = {
    DEFAULT_ADAPTER_KEY: FieldAliasAdapter(
        adapter_key=DEFAULT_ADAPTER_KEY,
        record_type="hes_event_raw",
        collection_key="events",
        field_aliases={
            "meter_id": ("meter_id", "meter_identifier", "meter_no"),
            "event_ts": ("event_ts", "event_time", "occurred_at"),
            "event_code": ("event_code", "code"),
            "severity": ("severity", "event_severity"),
            "event_source": ("event_source", "source"),
        },
    ),
    "legacy_hes_v1": FieldAliasAdapter(
        adapter_key="legacy_hes_v1",
        record_type="hes_event_raw",
        collection_key="events",
        field_aliases={
            "meter_id": ("mtr_no",),
            "event_ts": ("event_time",),
            "event_code": ("event_id",),
            "severity": ("severity",),
            "event_source": ("origin",),
        },
    ),
}


def resolve_adapter_key(payload: dict[str, Any]) -> str:
    return _normalize_text(payload.get("adapter_key")) or DEFAULT_ADAPTER_KEY


def resolve_read_adapter(payload: dict[str, Any]) -> FieldAliasAdapter:
    adapter_key = resolve_adapter_key(payload)
    adapter = READ_ADAPTERS.get(adapter_key)
    if adapter is None:
        raise IngestContractError(
            "unsupported_adapter_key",
            f"Adapter key '{adapter_key}' is not supported for raw reads.",
            response_locale=detect_response_locale(payload),
        )
    return adapter


def resolve_event_adapter(payload: dict[str, Any]) -> FieldAliasAdapter:
    adapter_key = resolve_adapter_key(payload)
    adapter = EVENT_ADAPTERS.get(adapter_key)
    if adapter is None:
        raise IngestContractError(
            "unsupported_adapter_key",
            f"Adapter key '{adapter_key}' is not supported for raw events.",
            response_locale=detect_response_locale(payload),
        )
    return adapter


def adapt_read_records(payload: dict[str, Any]) -> tuple[str, list[AdaptedIngestRecord]]:
    adapter = resolve_read_adapter(payload)
    return adapter.adapter_key, adapter.adapt_records(payload)


def adapt_event_records(payload: dict[str, Any]) -> tuple[str, list[AdaptedIngestRecord]]:
    adapter = resolve_event_adapter(payload)
    return adapter.adapter_key, adapter.adapt_records(payload)
