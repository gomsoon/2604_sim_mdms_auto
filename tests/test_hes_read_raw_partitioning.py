from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.models import HesReadRaw, IngestBatch


def _month_floor(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _add_month(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


def _partition_name(value: datetime) -> str:
    return f"hes_read_raw_{value.year:04d}{value.month:02d}"


def _create_batch(session, *, batch_id: str) -> IngestBatch:
    batch = IngestBatch(
        source_system="HES_OVERSEAS",
        batch_id=batch_id,
        record_type="hes_read_raw",
        received_at=datetime.now(timezone.utc),
        payload={"reads": []},
    )
    session.add(batch)
    session.flush()
    return batch


def _table_name_for_raw(session, raw_id: int) -> str:
    return session.execute(
        text("select tableoid::regclass::text from hes_read_raw where id = :raw_id"),
        {"raw_id": raw_id},
    ).scalar_one()


def test_hes_read_raw_routes_cross_month_and_default_partition(session):
    current_month = _month_floor(datetime.now(timezone.utc))
    next_month = _add_month(current_month)
    batch = _create_batch(session, batch_id="partition-routing")

    first = HesReadRaw(
        ingest_batch_id=batch.id,
        source_system="HES_OVERSEAS",
        source_record_key="row-current",
        meter_identifier="32418",
        channel_identifier="0",
        measured_at=current_month,
        interval_size_minutes=60,
        reading_value=14.2,
        received_at=datetime.now(timezone.utc),
        canonical_status="pending",
        is_duplicate=False,
        payload={"value": 14.2},
    )
    second = HesReadRaw(
        ingest_batch_id=batch.id,
        source_system="HES_OVERSEAS",
        source_record_key="row-next",
        meter_identifier="32418",
        channel_identifier="0",
        measured_at=next_month,
        interval_size_minutes=60,
        reading_value=15.0,
        received_at=datetime.now(timezone.utc),
        canonical_status="pending",
        is_duplicate=False,
        payload={"value": 15.0},
    )
    default_row = HesReadRaw(
        ingest_batch_id=batch.id,
        source_system="HES_OVERSEAS",
        source_record_key="row-null",
        meter_identifier="32418",
        channel_identifier="0",
        measured_at=None,
        interval_size_minutes=60,
        reading_value=None,
        received_at=datetime.now(timezone.utc),
        canonical_status="exception",
        is_duplicate=False,
        payload={"value": None},
    )
    session.add_all([first, second, default_row])
    session.commit()

    assert _table_name_for_raw(session, first.id).endswith(_partition_name(current_month))
    assert _table_name_for_raw(session, second.id).endswith(_partition_name(next_month))
    assert _table_name_for_raw(session, default_row.id).endswith("hes_read_raw_default")

    default_row.measured_at = current_month.replace(hour=1)
    default_row.reading_value = 16.0
    default_row.canonical_status = "pending"
    session.commit()

    assert _table_name_for_raw(session, default_row.id).endswith(_partition_name(current_month))
