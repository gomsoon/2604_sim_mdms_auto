from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
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

    hes_read_rows: Mapped[list["HesReadRaw"]] = relationship(back_populates="ingest_batch")
    hes_event_rows: Mapped[list["HesEventRaw"]] = relationship(back_populates="ingest_batch")


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
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    meter_identifier: Mapped[str | None] = mapped_column(String(100), index=True)
    channel_identifier: Mapped[str | None] = mapped_column(String(100), index=True)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    reading_value: Mapped[float | None] = mapped_column(Float)
    quality_code: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[str | None] = mapped_column(String(40))
    unit_of_measure: Mapped[str | None] = mapped_column(String(20))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canonical_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("hes_read_raw.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingest_batch: Mapped[IngestBatch] = relationship(back_populates="hes_read_rows")
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
