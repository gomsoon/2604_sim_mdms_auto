from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IngestBatch(TimestampMixin, Base):
    __tablename__ = "ingest_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(30), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    adapter_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("adapter_instance.id"), index=True
    )
    adapter_run_id: Mapped[int | None] = mapped_column(ForeignKey("adapter_run.id"), index=True)

    hes_read_rows: Mapped[list["HesReadRaw"]] = relationship(back_populates="ingest_batch")
    hes_event_rows: Mapped[list["HesEventRaw"]] = relationship(back_populates="ingest_batch")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="ingest_batch")
    adapter_instance: Mapped["AdapterInstance | None"] = relationship(back_populates="ingest_batches")
    adapter_run: Mapped["AdapterRun | None"] = relationship(back_populates="ingest_batches")


class AdapterDefinition(TimestampMixin, Base):
    __tablename__ = "adapter_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    delivery_mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_family: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    adapter_profile_key: Mapped[str | None] = mapped_column(String(100))
    implementation_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    description: Mapped[str | None] = mapped_column(Text)

    adapter_instances: Mapped[list["AdapterInstance"]] = relationship(
        back_populates="adapter_definition"
    )


class AdapterInstance(TimestampMixin, Base):
    __tablename__ = "adapter_instance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter_definition_id: Mapped[int] = mapped_column(
        ForeignKey("adapter_definition.id"), nullable=False, index=True
    )
    instance_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    admin_state: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(String(200))
    poll_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    batch_size: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    landing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connection_config_masked: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    secret_ref: Mapped[str | None] = mapped_column(String(200))

    adapter_definition: Mapped[AdapterDefinition] = relationship(back_populates="adapter_instances")
    adapter_runs: Mapped[list["AdapterRun"]] = relationship(back_populates="adapter_instance")
    adapter_watermarks: Mapped[list["AdapterWatermark"]] = relationship(
        back_populates="adapter_instance"
    )
    ingest_batches: Mapped[list[IngestBatch]] = relationship(back_populates="adapter_instance")
    landing_lp_em_read_blocks: Mapped[list["LandingLpEmReadBlock"]] = relationship(
        back_populates="adapter_instance"
    )


class AdapterRun(TimestampMixin, Base):
    __tablename__ = "adapter_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter_instance_id: Mapped[int] = mapped_column(
        ForeignKey("adapter_instance.id"), nullable=False, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    run_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_rows_fetched: Mapped[int | None] = mapped_column(Integer)
    ingest_batches_created: Mapped[int | None] = mapped_column(Integer)
    ingest_records_created: Mapped[int | None] = mapped_column(Integer)
    watermark_before: Mapped[str | None] = mapped_column(String(200))
    watermark_after: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_summary: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    adapter_instance: Mapped[AdapterInstance] = relationship(back_populates="adapter_runs")
    ingest_batches: Mapped[list[IngestBatch]] = relationship(back_populates="adapter_run")
    landing_lp_em_read_blocks: Mapped[list["LandingLpEmReadBlock"]] = relationship(
        back_populates="adapter_run"
    )
    raw_interval_window_states: Mapped[list["RawIntervalWindowState"]] = relationship(
        back_populates="last_adapter_run"
    )


class AdapterWatermark(TimestampMixin, Base):
    __tablename__ = "adapter_watermark"
    __table_args__ = (
        UniqueConstraint(
            "adapter_instance_id",
            "record_type",
            name="uq_adapter_watermark_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter_instance_id: Mapped[int] = mapped_column(
        ForeignKey("adapter_instance.id"), nullable=False, index=True
    )
    record_type: Mapped[str] = mapped_column(String(30), nullable=False)
    cursor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    cursor_value: Mapped[str | None] = mapped_column(String(200))
    last_source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    adapter_instance: Mapped[AdapterInstance] = relationship(back_populates="adapter_watermarks")


class LandingLpEmReadBlock(TimestampMixin, Base):
    __tablename__ = "landing_lp_em_read_block"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "source_block_key",
            name="uq_landing_lp_em_read_block_source_block",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter_instance_id: Mapped[int] = mapped_column(
        ForeignKey("adapter_instance.id"), nullable=False, index=True
    )
    adapter_run_id: Mapped[int] = mapped_column(
        ForeignKey("adapter_run.id"), nullable=False, index=True
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_table_name: Mapped[str] = mapped_column(String(150), nullable=False)
    source_block_key: Mapped[str] = mapped_column(String(255), nullable=False)
    meter_source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    device_source_id: Mapped[str | None] = mapped_column(String(100))
    mdev_id: Mapped[str | None] = mapped_column(String(100))
    mdev_type: Mapped[str | None] = mapped_column(String(50))
    channel_code: Mapped[str] = mapped_column(String(30), nullable=False)
    source_business_hour: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    source_hour_component: Mapped[str | None] = mapped_column(String(2))
    source_write_text: Mapped[str | None] = mapped_column(String(14))
    source_write_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    location_source_id: Mapped[str | None] = mapped_column(String(100))
    supplier_source_id: Mapped[str | None] = mapped_column(String(100))
    enddevice_source_id: Mapped[str | None] = mapped_column(String(100))
    value_cnt: Mapped[int | None] = mapped_column(Integer)
    block_value: Mapped[float | None] = mapped_column(Float)
    slot_values: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    slot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsed_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    parse_error_code: Mapped[str | None] = mapped_column(String(100))
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    adapter_instance: Mapped[AdapterInstance] = relationship(
        back_populates="landing_lp_em_read_blocks"
    )
    adapter_run: Mapped[AdapterRun] = relationship(back_populates="landing_lp_em_read_blocks")
    hes_read_rows: Mapped[list["HesReadRaw"]] = relationship(
        back_populates="landing_lp_em_read_block"
    )


class ServicePoint(TimestampMixin, Base):
    __tablename__ = "service_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    service_type: Mapped[str] = mapped_column(String(30), nullable=False, default="electric")
    name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    devices: Mapped[list["Device"]] = relationship(back_populates="service_point")
    installation_history: Mapped[list["InstallationHistory"]] = relationship(
        back_populates="service_point"
    )
    measuring_components: Mapped[list["MeasuringComponent"]] = relationship(
        back_populates="service_point"
    )


class Device(TimestampMixin, Base):
    __tablename__ = "device"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_meter_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    serial_number: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    service_point_id: Mapped[int | None] = mapped_column(ForeignKey("service_point.id"))

    service_point: Mapped[ServicePoint | None] = relationship(back_populates="devices")
    measuring_components: Mapped[list["MeasuringComponent"]] = relationship(back_populates="device")
    installation_history: Mapped[list["InstallationHistory"]] = relationship(
        back_populates="device"
    )


class MeasuringComponent(TimestampMixin, Base):
    __tablename__ = "measuring_component"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_channel_id: Mapped[str] = mapped_column(String(100), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False, default="kWh")
    multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)

    device: Mapped[Device] = relationship(back_populates="measuring_components")
    service_point: Mapped[ServicePoint] = relationship(back_populates="measuring_components")
    canonical_measurements: Mapped[list["CanonicalMeasurement"]] = relationship(
        back_populates="measuring_component"
    )


class InstallationHistory(TimestampMixin, Base):
    __tablename__ = "installation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="installed")

    device: Mapped[Device] = relationship(back_populates="installation_history")
    service_point: Mapped[ServicePoint] = relationship(back_populates="installation_history")


class HesReadRaw(TimestampMixin, Base):
    __tablename__ = "hes_read_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingest_batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batch.id"), nullable=False)
    adapter_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("adapter_instance.id"), index=True
    )
    adapter_run_id: Mapped[int | None] = mapped_column(ForeignKey("adapter_run.id"), index=True)
    landing_lp_em_read_block_id: Mapped[int | None] = mapped_column(
        ForeignKey("landing_lp_em_read_block.id"), index=True
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_table_name: Mapped[str | None] = mapped_column(String(150))
    source_block_key: Mapped[str | None] = mapped_column(String(255))
    source_record_key: Mapped[str | None] = mapped_column(String(255))
    meter_identifier: Mapped[str | None] = mapped_column(String(100), index=True)
    device_identifier: Mapped[str | None] = mapped_column(String(100))
    channel_identifier: Mapped[str | None] = mapped_column(String(100), index=True)
    source_slot_code: Mapped[str | None] = mapped_column(String(10))
    source_slot_index: Mapped[int | None] = mapped_column(Integer)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    interval_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_size_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    reading_value: Mapped[float | None] = mapped_column(Float)
    quality_code: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[str | None] = mapped_column(String(40))
    unit_of_measure: Mapped[str | None] = mapped_column(String(20))
    source_business_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_write_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canonical_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("hes_read_raw.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingest_batch: Mapped[IngestBatch] = relationship(back_populates="hes_read_rows")
    adapter_instance: Mapped["AdapterInstance | None"] = relationship()
    adapter_run: Mapped["AdapterRun | None"] = relationship()
    landing_lp_em_read_block: Mapped["LandingLpEmReadBlock | None"] = relationship(
        back_populates="hes_read_rows"
    )
    canonical_measurement: Mapped["CanonicalMeasurement | None"] = relationship(
        back_populates="hes_read_raw", uselist=False
    )
    duplicate_of: Mapped["HesReadRaw | None"] = relationship(remote_side=[id])
    error_logs: Mapped[list["IngestErrorLog"]] = relationship(back_populates="hes_read_raw")
    reprocess_requests: Mapped[list["ReprocessRequest"]] = relationship(
        back_populates="hes_read_raw"
    )


class HesEventRaw(TimestampMixin, Base):
    __tablename__ = "hes_event_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingest_batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batch.id"), nullable=False)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    meter_identifier: Mapped[str | None] = mapped_column(String(100), index=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    event_code: Mapped[str | None] = mapped_column(String(60))
    severity: Mapped[str | None] = mapped_column(String(30))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingest_batch: Mapped[IngestBatch] = relationship(back_populates="hes_event_rows")
    error_logs: Mapped[list["IngestErrorLog"]] = relationship(back_populates="hes_event_raw")


class CanonicalMeasurement(TimestampMixin, Base):
    __tablename__ = "canonical_measurement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hes_read_raw_id: Mapped[int] = mapped_column(
        ForeignKey("hes_read_raw.id"), nullable=False, unique=True
    )
    measuring_component_id: Mapped[int] = mapped_column(
        ForeignKey("measuring_component.id"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    quality_code: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[str | None] = mapped_column(String(40))
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)

    hes_read_raw: Mapped[HesReadRaw] = relationship(back_populates="canonical_measurement")
    measuring_component: Mapped[MeasuringComponent] = relationship(
        back_populates="canonical_measurements"
    )
    final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        back_populates="canonical_measurement", uselist=False
    )


class FinalMeasurement(TimestampMixin, Base):
    __tablename__ = "final_measurement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_measurement_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_measurement.id"), nullable=False, unique=True
    )
    measuring_component_id: Mapped[int] = mapped_column(
        ForeignKey("measuring_component.id"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    quality_code: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[str | None] = mapped_column(String(40))
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)
    final_status: Mapped[str] = mapped_column(String(30), nullable=False, default="finalized")
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    canonical_measurement: Mapped[CanonicalMeasurement] = relationship(
        back_populates="final_measurement"
    )


class RawIntervalWindowState(TimestampMixin, Base):
    __tablename__ = "raw_interval_window_state"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "meter_identifier",
            "channel_identifier",
            "window_start_at",
            "window_size_minutes",
            name="uq_raw_interval_window_state_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    meter_identifier: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_identifier: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    window_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_size_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_size_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_slot_count: Mapped[int] = mapped_column(Integer, nullable=False)
    received_slot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_slot_bitmap: Mapped[str | None] = mapped_column(String(256))
    first_source_write_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_source_write_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completion_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    late_update_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_adapter_run_id: Mapped[int | None] = mapped_column(ForeignKey("adapter_run.id"))
    last_ingest_batch_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_batch.id"))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    last_adapter_run: Mapped["AdapterRun | None"] = relationship(
        back_populates="raw_interval_window_states"
    )
    last_ingest_batch: Mapped["IngestBatch | None"] = relationship()


class IngestErrorLog(TimestampMixin, Base):
    __tablename__ = "ingest_error_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exception_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    exception_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    hes_read_raw_id: Mapped[int | None] = mapped_column(ForeignKey("hes_read_raw.id"))
    hes_event_raw_id: Mapped[int | None] = mapped_column(ForeignKey("hes_event_raw.id"))
    hes_read_raw: Mapped[HesReadRaw | None] = relationship(back_populates="error_logs")
    hes_event_raw: Mapped[HesEventRaw | None] = relationship(back_populates="error_logs")
    reprocess_requests: Mapped[list["ReprocessRequest"]] = relationship(
        back_populates="ingest_error_log"
    )


class ReprocessRequest(TimestampMixin, Base):
    __tablename__ = "reprocess_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingest_error_log_id: Mapped[int] = mapped_column(
        ForeignKey("ingest_error_log.id"), nullable=False, index=True
    )
    hes_read_raw_id: Mapped[int] = mapped_column(ForeignKey("hes_read_raw.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="processing")
    result_code: Mapped[str | None] = mapped_column(String(80))
    result_message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ingest_error_log: Mapped[IngestErrorLog] = relationship(back_populates="reprocess_requests")
    hes_read_raw: Mapped[HesReadRaw] = relationship(back_populates="reprocess_requests")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="reprocess_request")


class PipelineRun(TimestampMixin, Base):
    __tablename__ = "pipeline_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="processing")
    ingest_batch_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_batch.id"))
    reprocess_request_id: Mapped[int | None] = mapped_column(ForeignKey("reprocess_request.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_code: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingest_batch: Mapped[IngestBatch | None] = relationship(back_populates="pipeline_runs")
    reprocess_request: Mapped[ReprocessRequest | None] = relationship(back_populates="pipeline_runs")


class ProcessingWatermark(TimestampMixin, Base):
    __tablename__ = "processing_watermark"
    __table_args__ = (
        UniqueConstraint(
            "pipeline_name",
            "source_system",
            "record_type",
            name="uq_processing_watermark_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_system: Mapped[str | None] = mapped_column(String(50), index=True)
    record_type: Mapped[str | None] = mapped_column(String(30), index=True)
    last_processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
