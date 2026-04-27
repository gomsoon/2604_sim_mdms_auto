from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.models import (
    CanonicalMeasurement,
    HesReadRaw,
    IngestBatch,
    IngestErrorLog,
    InitialMeasurement,
    VeeExecutionLog,
)
from app.services.ingestion import ingest_reads
from app.services.seeds import seed_master_data


def test_ingest_reads_accepts_empty_read_list(session):
    summary = ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "boundary-empty-reads",
            "received_at": "2026-04-18T09:00:00+09:00",
            "reads": [],
        },
    )
    session.commit()

    assert summary["batches_created"] == 1
    assert summary["ingest_batch_id"] is not None
    assert summary["raw_reads_received"] == 0
    assert summary["canonical_created"] == 0
    assert summary["duplicates"] == 0
    assert summary["exceptions"] == 0
    assert session.scalar(select(func.count()).select_from(IngestBatch)) == 1
    assert session.scalar(select(func.count()).select_from(HesReadRaw)) == 0
    assert session.scalar(select(func.count()).select_from(IngestErrorLog)) == 0


def test_ingest_reads_marks_missing_required_fields_with_boundary_values(session):
    seed_master_data(session)
    session.commit()

    summary = ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "boundary-missing-fields",
            "received_at": "2026-04-18T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:15:00+09:00",
                    "value": 0.0,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()

    row = session.scalar(select(HesReadRaw).order_by(HesReadRaw.id.desc()).limit(1))
    error = session.scalar(select(IngestErrorLog).order_by(IngestErrorLog.id.desc()).limit(1))

    assert summary["raw_reads_received"] == 1
    assert summary["canonical_created"] == 0
    assert summary["exceptions"] == 1
    assert row is not None
    assert row.canonical_status == "exception"
    assert error is not None
    assert error.exception_code == "missing_required_fields"
    assert error.hes_read_raw_id == row.id


def test_ingest_reads_marks_second_identical_read_as_duplicate(session):
    seed_master_data(session)
    session.commit()

    summary = ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "boundary-duplicate-read",
            "received_at": "2026-04-18T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:15:00+09:00",
                    "value": 0.0,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:15:00+09:00",
                    "value": 0.0,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
            ],
        },
    )
    session.commit()

    rows = session.scalars(select(HesReadRaw).order_by(HesReadRaw.id.asc())).all()
    duplicate_error = session.scalar(
        select(IngestErrorLog)
        .where(IngestErrorLog.exception_code == "duplicate_raw_read")
        .order_by(IngestErrorLog.id.desc())
        .limit(1)
    )

    assert summary["raw_reads_received"] == 2
    assert summary["canonical_created"] == 1
    assert summary["duplicates"] == 1
    assert summary["exceptions"] == 0
    assert len(rows) == 2
    assert rows[0].canonical_status == "mapped"
    assert rows[1].canonical_status == "duplicate"
    assert rows[1].duplicate_of_id == rows[0].id
    assert session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 1
    assert duplicate_error is not None
    assert duplicate_error.hes_read_raw_id == rows[1].id


def test_ingest_reads_supports_legacy_adapter_mapping_and_preserves_original_payload(session):
    seed_master_data(session)
    session.commit()

    summary = ingest_reads(
        session,
        {
            "source_system": "HES",
            "adapter_key": "legacy_hes_v1",
            "batch_id": "boundary-legacy-adapter-read",
            "received_at": "2026-04-18T09:00:00+09:00",
            "reads": [
                {
                    "mtr_no": "MTR-1001",
                    "chn_no": "CH-01",
                    "read_time": "2026-04-18T00:45:00+09:00",
                    "read_value": "3.75",
                    "quality": "OK",
                    "status": "ACTUAL",
                    "uom": "kWh",
                }
            ],
        },
    )
    session.commit()

    row = session.scalar(select(HesReadRaw).order_by(HesReadRaw.id.desc()).limit(1))

    assert summary["raw_reads_received"] == 1
    assert summary["canonical_created"] == 1
    assert summary["exceptions"] == 0
    assert row is not None
    assert row.meter_identifier == "MTR-1001"
    assert row.channel_identifier == "CH-01"
    assert row.reading_value == Decimal("3.75")
    assert row.unit_of_measure == "kWh"
    assert row.payload["mtr_no"] == "MTR-1001"
    assert row.payload["read_value"] == "3.75"
    assert row.canonical_status == "mapped"
    assert session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 1


def test_ingest_reads_creates_initial_measurement_and_pass_through_vee_log(session):
    seed_master_data(session)
    session.commit()

    summary = ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "boundary-processing-core-lineage",
            "received_at": "2026-04-18T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T01:00:00+09:00",
                    "value": 5.25,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()

    canonical = session.scalar(
        select(CanonicalMeasurement).order_by(CanonicalMeasurement.id.desc()).limit(1)
    )
    initial = session.scalar(select(InitialMeasurement).limit(1))
    execution = session.scalar(select(VeeExecutionLog).limit(1))

    assert summary["canonical_created"] == 1
    assert canonical is not None
    assert initial is not None
    assert execution is not None
    assert initial.canonical_measurement_id == canonical.id
    assert initial.initial_status == "accepted"
    assert execution.initial_measurement_id == initial.id
    assert execution.execution_status == "passed"
    assert execution.summary_code == "vee_passed"
