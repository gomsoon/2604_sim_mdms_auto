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


class IngestionBatch(TimestampMixin, Base):
    __tablename__ = "ingestion_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(30), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    raw_reads: Mapped[list["RawRead"]] = relationship(back_populates="ingestion_batch")
    raw_events: Mapped[list["RawEvent"]] = relationship(back_populates="ingestion_batch")


class ServicePoint(TimestampMixin, Base):
    __tablename__ = "service_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    service_type: Mapped[str] = mapped_column(String(30), nullable=False, default="electric")
    name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")

    devices: Mapped[list["Device"]] = relationship(back_populates="service_point")
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


class RawRead(TimestampMixin, Base):
    __tablename__ = "raw_read"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingestion_batch_id: Mapped[int] = mapped_column(ForeignKey("ingestion_batch.id"), nullable=False)
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
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("raw_read.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingestion_batch: Mapped[IngestionBatch] = relationship(back_populates="raw_reads")
    canonical_measurement: Mapped["CanonicalMeasurement | None"] = relationship(
        back_populates="raw_read", uselist=False
    )
    duplicate_of: Mapped["RawRead | None"] = relationship(remote_side=[id])


class RawEvent(TimestampMixin, Base):
    __tablename__ = "raw_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingestion_batch_id: Mapped[int] = mapped_column(ForeignKey("ingestion_batch.id"), nullable=False)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    meter_identifier: Mapped[str | None] = mapped_column(String(100), index=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    event_code: Mapped[str | None] = mapped_column(String(60))
    severity: Mapped[str | None] = mapped_column(String(30))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingestion_batch: Mapped[IngestionBatch] = relationship(back_populates="raw_events")


class CanonicalMeasurement(TimestampMixin, Base):
    __tablename__ = "canonical_measurement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_read_id: Mapped[int] = mapped_column(ForeignKey("raw_read.id"), nullable=False, unique=True)
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

    raw_read: Mapped[RawRead] = relationship(back_populates="canonical_measurement")
    measuring_component: Mapped[MeasuringComponent] = relationship(
        back_populates="canonical_measurements"
    )


class ProcessingException(TimestampMixin, Base):
    __tablename__ = "processing_exception"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exception_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    exception_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw_read_id: Mapped[int | None] = mapped_column(ForeignKey("raw_read.id"))
    raw_event_id: Mapped[int | None] = mapped_column(ForeignKey("raw_event.id"))

