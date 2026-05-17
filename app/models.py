from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Any

from sqlalchemy import (
    and_,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class UserAccount(TimestampMixin, Base):
    __tablename__ = "user_account"
    __table_args__ = (
        CheckConstraint(
            "role_code in ('admin', 'operator')",
            name="ck_user_account_role_code",
        ),
        Index("ix_user_account_role_code", "role_code"),
        Index("ix_user_account_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role_code: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    auth_session_audits: Mapped[list["AuthSessionAudit"]] = relationship(
        back_populates="user_account"
    )
    user_action_audits: Mapped[list["UserActionAudit"]] = relationship(
        back_populates="user_account"
    )
    acknowledged_vee_exceptions: Mapped[list["VeeException"]] = relationship(
        back_populates="acknowledged_by_user_account",
        foreign_keys="VeeException.acknowledged_by_user_account_id",
    )
    resolved_vee_exceptions: Mapped[list["VeeException"]] = relationship(
        back_populates="resolved_by_user_account",
        foreign_keys="VeeException.resolved_by_user_account_id",
    )
    estimated_estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="estimated_by_user_account",
        foreign_keys="EstimationAudit.estimated_by_user_account_id",
    )
    edited_manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="edited_by_user_account",
        foreign_keys="ManualEditAudit.edited_by_user_account_id",
    )
    requested_vee_replay_requests: Mapped[list["VeeReplayRequest"]] = relationship(
        back_populates="requested_by_user_account",
        foreign_keys="VeeReplayRequest.requested_by_user_account_id",
    )
    cancelled_vee_replay_requests: Mapped[list["VeeReplayRequest"]] = relationship(
        back_populates="cancelled_by_user_account",
        foreign_keys="VeeReplayRequest.cancelled_by_user_account_id",
    )
    requested_billing_export_requests: Mapped[list["BillingExportRequest"]] = relationship(
        back_populates="requested_by_user_account",
        foreign_keys="BillingExportRequest.requested_by_user_account_id",
    )
    cancelled_billing_export_requests: Mapped[list["BillingExportRequest"]] = relationship(
        back_populates="cancelled_by_user_account",
        foreign_keys="BillingExportRequest.cancelled_by_user_account_id",
    )
    created_hes_systems: Mapped[list["HesSystem"]] = relationship(
        back_populates="created_by_user_account",
        foreign_keys="HesSystem.created_by_user_account_id",
    )
    updated_hes_systems: Mapped[list["HesSystem"]] = relationship(
        back_populates="updated_by_user_account",
        foreign_keys="HesSystem.updated_by_user_account_id",
    )
    created_adapter_instances: Mapped[list["AdapterInstance"]] = relationship(
        back_populates="created_by_user_account",
        foreign_keys="AdapterInstance.created_by_user_account_id",
    )
    updated_adapter_instances: Mapped[list["AdapterInstance"]] = relationship(
        back_populates="updated_by_user_account",
        foreign_keys="AdapterInstance.updated_by_user_account_id",
    )
    requested_adapter_runs: Mapped[list["AdapterRun"]] = relationship(
        back_populates="requested_by_user_account",
        foreign_keys="AdapterRun.requested_by_user_account_id",
    )
    created_service_points: Mapped[list["ServicePoint"]] = relationship(
        back_populates="created_by_user_account",
        foreign_keys="ServicePoint.created_by_user_account_id",
    )
    updated_service_points: Mapped[list["ServicePoint"]] = relationship(
        back_populates="updated_by_user_account",
        foreign_keys="ServicePoint.updated_by_user_account_id",
    )
    created_billing_context_rows: Mapped[list["ServicePointBillingContext"]] = relationship(
        back_populates="created_by_user_account",
        foreign_keys="ServicePointBillingContext.created_by_user_account_id",
    )
    updated_billing_context_rows: Mapped[list["ServicePointBillingContext"]] = relationship(
        back_populates="updated_by_user_account",
        foreign_keys="ServicePointBillingContext.updated_by_user_account_id",
    )
    created_tariff_assignment_rows: Mapped[list["ServicePointTariffAssignment"]] = relationship(
        back_populates="created_by_user_account",
        foreign_keys="ServicePointTariffAssignment.created_by_user_account_id",
    )
    updated_tariff_assignment_rows: Mapped[list["ServicePointTariffAssignment"]] = relationship(
        back_populates="updated_by_user_account",
        foreign_keys="ServicePointTariffAssignment.updated_by_user_account_id",
    )
    created_devices: Mapped[list["Device"]] = relationship(
        back_populates="created_by_user_account",
        foreign_keys="Device.created_by_user_account_id",
    )
    updated_devices: Mapped[list["Device"]] = relationship(
        back_populates="updated_by_user_account",
        foreign_keys="Device.updated_by_user_account_id",
    )
    created_measuring_components: Mapped[list["MeasuringComponent"]] = relationship(
        back_populates="created_by_user_account",
        foreign_keys="MeasuringComponent.created_by_user_account_id",
    )
    updated_measuring_components: Mapped[list["MeasuringComponent"]] = relationship(
        back_populates="updated_by_user_account",
        foreign_keys="MeasuringComponent.updated_by_user_account_id",
    )
    created_installation_history_rows: Mapped[list["InstallationHistory"]] = relationship(
        back_populates="created_by_user_account",
        foreign_keys="InstallationHistory.created_by_user_account_id",
    )
    updated_installation_history_rows: Mapped[list["InstallationHistory"]] = relationship(
        back_populates="updated_by_user_account",
        foreign_keys="InstallationHistory.updated_by_user_account_id",
    )


class AuthSessionAudit(Base):
    __tablename__ = "auth_session_audit"
    __table_args__ = (
        CheckConstraint(
            "auth_event_type in "
            "('login_succeeded', 'login_failed', 'logout', 'session_expired')",
            name="ck_auth_session_audit_auth_event_type",
        ),
        CheckConstraint(
            "auth_channel in ('web_session', 'api_session', 'api_token')",
            name="ck_auth_session_audit_auth_channel",
        ),
        Index("ix_auth_session_audit_user_account_id", "user_account_id"),
        Index("ix_auth_session_audit_login_id_attempted", "login_id_attempted"),
        Index("ix_auth_session_audit_auth_event_type", "auth_event_type"),
        Index("ix_auth_session_audit_session_identifier", "session_identifier"),
        Index("ix_auth_session_audit_occurred_at", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_account_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    login_id_attempted: Mapped[str | None] = mapped_column(String(120))
    auth_event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    session_identifier: Mapped[str | None] = mapped_column(String(120))
    auth_channel: Mapped[str] = mapped_column(String(30), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    result_code: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="auth_session_audits"
    )
    user_action_audits: Mapped[list["UserActionAudit"]] = relationship(
        back_populates="auth_session_audit"
    )


class UserActionAudit(Base):
    __tablename__ = "user_action_audit"
    __table_args__ = (
        CheckConstraint(
            "action_type in "
            "('read', 'create', 'update', 'delete', 'execute', 'login', 'logout')",
            name="ck_user_action_audit_action_type",
        ),
        Index("ix_user_action_audit_user_account_id", "user_account_id"),
        Index("ix_user_action_audit_auth_session_audit_id", "auth_session_audit_id"),
        Index("ix_user_action_audit_action_type", "action_type"),
        Index("ix_user_action_audit_resource_type", "resource_type"),
        Index("ix_user_action_audit_request_path", "request_path"),
        Index("ix_user_action_audit_outcome_code", "outcome_code"),
        Index("ix_user_action_audit_occurred_at", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_account_id: Mapped[int] = mapped_column(
        ForeignKey("user_account.id"),
        nullable=False,
    )
    auth_session_audit_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_session_audit.id")
    )
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(120))
    request_method: Mapped[str | None] = mapped_column(String(16))
    request_path: Mapped[str | None] = mapped_column(String(255))
    status_code: Mapped[int | None] = mapped_column(Integer)
    outcome_code: Mapped[str] = mapped_column(String(60), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user_account: Mapped["UserAccount"] = relationship(back_populates="user_action_audits")
    auth_session_audit: Mapped["AuthSessionAudit | None"] = relationship(
        back_populates="user_action_audits"
    )


class HesSystem(TimestampMixin, Base):
    __tablename__ = "hes_system"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hes_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    vendor_name: Mapped[str | None] = mapped_column(String(100))
    source_family: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    default_delivery_mode: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    timezone_name: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    connection_config_masked: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    updated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )

    created_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="created_hes_systems",
        foreign_keys=[created_by_user_account_id],
    )
    updated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="updated_hes_systems",
        foreign_keys=[updated_by_user_account_id],
    )
    adapter_instances: Mapped[list["AdapterInstance"]] = relationship(back_populates="hes_system")
    ingest_batches: Mapped[list["IngestBatch"]] = relationship(back_populates="hes_system")
    hes_read_rows: Mapped[list["HesReadRaw"]] = relationship(back_populates="hes_system")
    hes_event_rows: Mapped[list["HesEventRaw"]] = relationship(back_populates="hes_system")
    hes_meter_references: Mapped[list["HesMeterReference"]] = relationship(
        back_populates="hes_system"
    )
    landing_lp_em_read_blocks: Mapped[list["LandingLpEmReadBlock"]] = relationship(
        back_populates="hes_system"
    )
    operational_events: Mapped[list["OperationalEvent"]] = relationship(
        back_populates="hes_system"
    )
    vee_replay_requests: Mapped[list["VeeReplayRequest"]] = relationship(
        back_populates="hes_system"
    )


class IngestBatch(TimestampMixin, Base):
    __tablename__ = "ingest_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hes_system_id: Mapped[int | None] = mapped_column(ForeignKey("hes_system.id"), index=True)
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
    vee_replay_requests: Mapped[list["VeeReplayRequest"]] = relationship(
        back_populates="ingest_batch"
    )
    hes_system: Mapped["HesSystem | None"] = relationship(back_populates="ingest_batches")
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
    hes_system_id: Mapped[int | None] = mapped_column(ForeignKey("hes_system.id"), index=True)
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
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    updated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )

    hes_system: Mapped["HesSystem | None"] = relationship(back_populates="adapter_instances")
    adapter_definition: Mapped[AdapterDefinition] = relationship(back_populates="adapter_instances")
    created_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="created_adapter_instances",
        foreign_keys=[created_by_user_account_id],
    )
    updated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="updated_adapter_instances",
        foreign_keys=[updated_by_user_account_id],
    )
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
    __table_args__ = (
        Index(
            "uq_adapter_run_single_running_per_instance",
            "adapter_instance_id",
            unique=True,
            postgresql_where=text("run_status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter_instance_id: Mapped[int] = mapped_column(
        ForeignKey("adapter_instance.id"), nullable=False, index=True
    )
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    requested_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
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
    requested_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="requested_adapter_runs",
        foreign_keys=[requested_by_user_account_id],
    )
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
    hes_system_id: Mapped[int | None] = mapped_column(ForeignKey("hes_system.id"), index=True)
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

    hes_system: Mapped["HesSystem | None"] = relationship(back_populates="landing_lp_em_read_blocks")
    adapter_instance: Mapped[AdapterInstance] = relationship(
        back_populates="landing_lp_em_read_blocks"
    )
    adapter_run: Mapped[AdapterRun] = relationship(back_populates="landing_lp_em_read_blocks")
    hes_read_rows: Mapped[list["HesReadRaw"]] = relationship(
        back_populates="landing_lp_em_read_block"
    )


class HesMeterReference(TimestampMixin, Base):
    __tablename__ = "hes_meter_reference"
    __table_args__ = (
        UniqueConstraint(
            "hes_system_id",
            "source_meter_id",
            name="uq_hes_meter_reference_source_meter_id",
        ),
        UniqueConstraint(
            "hes_system_id",
            "source_meter_key",
            name="uq_hes_meter_reference_source_meter_key",
        ),
        Index("ix_hes_meter_reference_source_table_name", "source_table_name"),
        Index("ix_hes_meter_reference_meter_status_code", "meter_status_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hes_system_id: Mapped[int] = mapped_column(ForeignKey("hes_system.id"), nullable=False, index=True)
    source_table_name: Mapped[str] = mapped_column(String(150), nullable=False)
    source_meter_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_meter_key: Mapped[str | None] = mapped_column(String(100))
    meter_name: Mapped[str | None] = mapped_column(String(150))
    meter_status_code: Mapped[str | None] = mapped_column(String(60))
    lp_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    meter_type_code: Mapped[str | None] = mapped_column(String(100))
    device_model_code: Mapped[str | None] = mapped_column(String(100))
    modem_source_id: Mapped[str | None] = mapped_column(String(100))
    location_source_id: Mapped[str | None] = mapped_column(String(100))
    supplier_source_id: Mapped[str | None] = mapped_column(String(100))
    last_read_at_text: Mapped[str | None] = mapped_column(String(50))
    source_write_at_text: Mapped[str | None] = mapped_column(String(50))
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    hes_system: Mapped["HesSystem"] = relationship(back_populates="hes_meter_references")


class ServicePoint(TimestampMixin, Base):
    __tablename__ = "service_point"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    service_type: Mapped[str] = mapped_column(String(30), nullable=False, default="electric")
    name: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    updated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )

    created_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="created_service_points",
        foreign_keys=[created_by_user_account_id],
    )
    updated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="updated_service_points",
        foreign_keys=[updated_by_user_account_id],
    )
    devices: Mapped[list["Device"]] = relationship(back_populates="service_point")
    installation_history: Mapped[list["InstallationHistory"]] = relationship(
        back_populates="service_point"
    )
    billing_context_rows: Mapped[list["ServicePointBillingContext"]] = relationship(
        back_populates="service_point"
    )
    tariff_assignment_rows: Mapped[list["ServicePointTariffAssignment"]] = relationship(
        back_populates="service_point"
    )
    measuring_components: Mapped[list["MeasuringComponent"]] = relationship(
        back_populates="service_point"
    )
    initial_measurements: Mapped[list["InitialMeasurement"]] = relationship(
        back_populates="service_point"
    )
    estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="service_point"
    )
    manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="service_point"
    )
    usage_transactions: Mapped[list["UsageTransaction"]] = relationship(
        back_populates="service_point"
    )
    bill_determinants: Mapped[list["BillDeterminant"]] = relationship(
        back_populates="service_point"
    )
    bill_charges: Mapped[list["BillCharge"]] = relationship(back_populates="service_point")
    billing_export_requests: Mapped[list["BillingExportRequest"]] = relationship(
        back_populates="service_point"
    )
    billing_export_items: Mapped[list["BillingExportItem"]] = relationship(
        back_populates="service_point"
    )


class ServicePointBillingContext(TimestampMixin, Base):
    __tablename__ = "service_point_billing_context"
    __table_args__ = (
        CheckConstraint(
            "effective_to is null or effective_from < effective_to",
            name="ck_service_point_billing_context_effective_window",
        ),
        CheckConstraint(
            "(billing_cycle_mode = 'calendar_month' and billing_cycle_anchor_day is null) "
            "or "
            "(billing_cycle_mode = 'anchored_month' and billing_cycle_anchor_day between 1 and 28)",
            name="ck_service_point_billing_context_cycle_mode",
        ),
        Index(
            "ix_service_point_billing_context_billing_cycle_mode",
            "billing_cycle_mode",
        ),
        Index(
            "ix_service_point_billing_context_effective_from",
            "effective_from",
        ),
        Index(
            "ix_service_point_billing_context_effective_to",
            "effective_to",
        ),
        Index(
            "ix_service_point_billing_context_is_current",
            "is_current",
        ),
        Index(
            "ix_service_point_billing_context_service_point_effective_from",
            "service_point_id",
            "effective_from",
        ),
        Index(
            "uq_service_point_billing_context_current_service_point",
            "service_point_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_point_id: Mapped[int] = mapped_column(
        ForeignKey("service_point.id"),
        nullable=False,
    )
    timezone_name: Mapped[str] = mapped_column(String(50), nullable=False)
    billing_cycle_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    billing_cycle_anchor_day: Mapped[int | None] = mapped_column(Integer)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_reference: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    updated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )

    service_point: Mapped["ServicePoint"] = relationship(back_populates="billing_context_rows")
    created_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="created_billing_context_rows",
        foreign_keys=[created_by_user_account_id],
    )
    updated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="updated_billing_context_rows",
        foreign_keys=[updated_by_user_account_id],
    )


class ServicePointTariffAssignment(TimestampMixin, Base):
    __tablename__ = "service_point_tariff_assignment"
    __table_args__ = (
        CheckConstraint(
            "effective_to is null or effective_from < effective_to",
            name="ck_service_point_tariff_assignment_effective_window",
        ),
        Index(
            "ix_service_point_tariff_assignment_effective_from",
            "effective_from",
        ),
        Index(
            "ix_service_point_tariff_assignment_effective_to",
            "effective_to",
        ),
        Index(
            "ix_service_point_tariff_assignment_is_current",
            "is_current",
        ),
        Index(
            "ix_service_point_tariff_assignment_service_point_effective_from",
            "service_point_id",
            "effective_from",
        ),
        Index(
            "ix_spta_service_point_tariff_plan_code",
            "service_point_id",
            "tariff_plan_code",
        ),
        Index(
            "uq_service_point_tariff_assignment_current_service_point",
            "service_point_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_point_id: Mapped[int] = mapped_column(
        ForeignKey("service_point.id"),
        nullable=False,
    )
    tariff_plan_code: Mapped[str] = mapped_column(String(60), nullable=False)
    tariff_version_code: Mapped[str | None] = mapped_column(String(60))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_reference: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    updated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )

    service_point: Mapped["ServicePoint"] = relationship(back_populates="tariff_assignment_rows")
    created_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="created_tariff_assignment_rows",
        foreign_keys=[created_by_user_account_id],
    )
    updated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="updated_tariff_assignment_rows",
        foreign_keys=[updated_by_user_account_id],
    )


class Device(TimestampMixin, Base):
    __tablename__ = "device"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_meter_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    serial_number: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    service_point_id: Mapped[int | None] = mapped_column(ForeignKey("service_point.id"))
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    updated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )

    service_point: Mapped[ServicePoint | None] = relationship(back_populates="devices")
    created_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="created_devices",
        foreign_keys=[created_by_user_account_id],
    )
    updated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="updated_devices",
        foreign_keys=[updated_by_user_account_id],
    )
    measuring_components: Mapped[list["MeasuringComponent"]] = relationship(back_populates="device")
    installation_history: Mapped[list["InstallationHistory"]] = relationship(
        back_populates="device"
    )
    initial_measurements: Mapped[list["InitialMeasurement"]] = relationship(
        back_populates="device"
    )
    estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="device"
    )
    manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="device"
    )
    usage_transactions: Mapped[list["UsageTransaction"]] = relationship(
        back_populates="device"
    )
    bill_determinants: Mapped[list["BillDeterminant"]] = relationship(
        back_populates="device"
    )
    bill_charges: Mapped[list["BillCharge"]] = relationship(back_populates="device")


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
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    updated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )

    device: Mapped[Device] = relationship(back_populates="measuring_components")
    service_point: Mapped[ServicePoint] = relationship(back_populates="measuring_components")
    created_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="created_measuring_components",
        foreign_keys=[created_by_user_account_id],
    )
    updated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="updated_measuring_components",
        foreign_keys=[updated_by_user_account_id],
    )
    canonical_measurements: Mapped[list["CanonicalMeasurement"]] = relationship(
        back_populates="measuring_component"
    )
    initial_measurements: Mapped[list["InitialMeasurement"]] = relationship(
        back_populates="measuring_component"
    )
    estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="measuring_component"
    )
    manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="measuring_component"
    )
    usage_transactions: Mapped[list["UsageTransaction"]] = relationship(
        back_populates="measuring_component"
    )
    bill_determinants: Mapped[list["BillDeterminant"]] = relationship(
        back_populates="measuring_component"
    )
    bill_charges: Mapped[list["BillCharge"]] = relationship(
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
    created_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    updated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )

    device: Mapped[Device] = relationship(back_populates="installation_history")
    service_point: Mapped[ServicePoint] = relationship(back_populates="installation_history")
    created_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="created_installation_history_rows",
        foreign_keys=[created_by_user_account_id],
    )
    updated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="updated_installation_history_rows",
        foreign_keys=[updated_by_user_account_id],
    )


class HesReadRaw(TimestampMixin, Base):
    __tablename__ = "hes_read_raw"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "measured_at",
            name="uq_hes_read_raw_id_measured_at",
        ),
        Index(
            "ix_hes_read_raw_source_meter_channel_measured_at",
            "source_system",
            "meter_identifier",
            "channel_identifier",
            "measured_at",
        ),
        Index("ix_hes_read_raw_id", "id"),
        Index(
            "ix_hes_read_raw_source_record_key_scope",
            "source_system",
            "source_record_key",
        ),
        ForeignKeyConstraint(
            ["duplicate_of_id", "duplicate_of_measured_at"],
            ["hes_read_raw.id", "hes_read_raw.measured_at"],
            name="fk_hes_read_raw_duplicate_of",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingest_batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batch.id"), nullable=False)
    hes_system_id: Mapped[int | None] = mapped_column(ForeignKey("hes_system.id"), index=True)
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
    reading_value: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    quality_code: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[str | None] = mapped_column(String(40))
    unit_of_measure: Mapped[str | None] = mapped_column(String(20))
    source_business_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_write_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    canonical_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer)
    duplicate_of_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingest_batch: Mapped[IngestBatch] = relationship(back_populates="hes_read_rows")
    hes_system: Mapped["HesSystem | None"] = relationship(back_populates="hes_read_rows")
    adapter_instance: Mapped["AdapterInstance | None"] = relationship()
    adapter_run: Mapped["AdapterRun | None"] = relationship()
    landing_lp_em_read_block: Mapped["LandingLpEmReadBlock | None"] = relationship(
        back_populates="hes_read_rows"
    )
    canonical_measurement: Mapped["CanonicalMeasurement | None"] = relationship(
        back_populates="hes_read_raw", uselist=False
    )
    duplicate_of: Mapped["HesReadRaw | None"] = relationship(
        remote_side=lambda: [HesReadRaw.id, HesReadRaw.measured_at],
        foreign_keys=lambda: [HesReadRaw.duplicate_of_id, HesReadRaw.duplicate_of_measured_at],
    )
    error_logs: Mapped[list["IngestErrorLog"]] = relationship(
        back_populates="hes_read_raw",
        primaryjoin=lambda: HesReadRaw.id == foreign(IngestErrorLog.hes_read_raw_id),
    )
    reprocess_requests: Mapped[list["ReprocessRequest"]] = relationship(
        back_populates="hes_read_raw",
        primaryjoin=lambda: HesReadRaw.id == foreign(ReprocessRequest.hes_read_raw_id),
    )


class HesEventRaw(TimestampMixin, Base):
    __tablename__ = "hes_event_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingest_batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batch.id"), nullable=False)
    hes_system_id: Mapped[int | None] = mapped_column(ForeignKey("hes_system.id"), index=True)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    meter_identifier: Mapped[str | None] = mapped_column(String(100), index=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    event_code: Mapped[str | None] = mapped_column(String(60))
    severity: Mapped[str | None] = mapped_column(String(30))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingest_batch: Mapped[IngestBatch] = relationship(back_populates="hes_event_rows")
    hes_system: Mapped["HesSystem | None"] = relationship(back_populates="hes_event_rows")
    error_logs: Mapped[list["IngestErrorLog"]] = relationship(back_populates="hes_event_raw")


class CanonicalMeasurement(TimestampMixin, Base):
    __tablename__ = "canonical_measurement"
    __table_args__ = (
        UniqueConstraint("hes_read_raw_id", name="uq_canonical_measurement_hes_read_raw_id"),
        ForeignKeyConstraint(
            ["hes_read_raw_id", "hes_read_raw_measured_at"],
            ["hes_read_raw.id", "hes_read_raw.measured_at"],
            name="fk_canonical_measurement_hes_read_raw_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hes_read_raw_id: Mapped[int] = mapped_column(Integer, nullable=False)
    hes_read_raw_measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    measuring_component_id: Mapped[int] = mapped_column(
        ForeignKey("measuring_component.id"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    quality_code: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[str | None] = mapped_column(String(40))
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)

    hes_read_raw: Mapped[HesReadRaw] = relationship(back_populates="canonical_measurement")
    measuring_component: Mapped[MeasuringComponent] = relationship(
        back_populates="canonical_measurements"
    )
    initial_measurement: Mapped["InitialMeasurement | None"] = relationship(
        back_populates="canonical_measurement", uselist=False
    )
    final_measurements: Mapped[list["FinalMeasurement"]] = relationship(
        back_populates="canonical_measurement",
        overlaps="final_measurement",
    )
    final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        primaryjoin=lambda: and_(
            CanonicalMeasurement.id == foreign(FinalMeasurement.canonical_measurement_id),
            FinalMeasurement.is_current.is_(True),
        ),
        uselist=False,
        viewonly=True,
        overlaps="final_measurements,canonical_measurement",
    )


class InitialMeasurement(TimestampMixin, Base):
    __tablename__ = "initial_measurement"

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
    value: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    quality_code: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[str | None] = mapped_column(String(40))
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)
    initial_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    ready_for_vee_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    canonical_measurement: Mapped[CanonicalMeasurement] = relationship(
        back_populates="initial_measurement"
    )
    measuring_component: Mapped[MeasuringComponent] = relationship(
        back_populates="initial_measurements"
    )
    device: Mapped[Device] = relationship(back_populates="initial_measurements")
    service_point: Mapped[ServicePoint] = relationship(back_populates="initial_measurements")
    final_measurements: Mapped[list["FinalMeasurement"]] = relationship(
        back_populates="initial_measurement",
        overlaps="final_measurement",
    )
    final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        primaryjoin=lambda: and_(
            InitialMeasurement.id == foreign(FinalMeasurement.initial_measurement_id),
            FinalMeasurement.is_current.is_(True),
        ),
        uselist=False,
        viewonly=True,
        overlaps="final_measurements,initial_measurement",
    )
    vee_execution_logs: Mapped[list["VeeExecutionLog"]] = relationship(
        back_populates="initial_measurement"
    )
    vee_exceptions: Mapped[list["VeeException"]] = relationship(back_populates="initial_measurement")
    vee_replay_request_items: Mapped[list["VeeReplayRequestItem"]] = relationship(
        back_populates="initial_measurement"
    )
    estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="target_initial_measurement"
    )
    manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="target_initial_measurement"
    )


class VeeExecutionLog(TimestampMixin, Base):
    __tablename__ = "vee_execution_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    initial_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("initial_measurement.id"), index=True
    )
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_run.id"))
    execution_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    rule_set_code: Mapped[str] = mapped_column(String(60), nullable=False)
    period_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary_code: Mapped[str | None] = mapped_column(String(60))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    initial_measurement: Mapped["InitialMeasurement | None"] = relationship(
        back_populates="vee_execution_logs"
    )
    pipeline_run: Mapped["PipelineRun | None"] = relationship(back_populates="vee_execution_logs")
    vee_exceptions: Mapped[list["VeeException"]] = relationship(back_populates="vee_execution_log")


class VeeException(TimestampMixin, Base):
    __tablename__ = "vee_exception"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    initial_measurement_id: Mapped[int] = mapped_column(
        ForeignKey("initial_measurement.id"), nullable=False, index=True
    )
    vee_execution_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("vee_execution_log.id"), index=True
    )
    exception_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    exception_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    blocking_finalization: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(120))
    acknowledged_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    resolved_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id"),
        index=True,
    )
    resolution_type: Mapped[str | None] = mapped_column(String(40))
    operator_memo: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    initial_measurement: Mapped["InitialMeasurement"] = relationship(back_populates="vee_exceptions")
    vee_execution_log: Mapped["VeeExecutionLog | None"] = relationship(
        back_populates="vee_exceptions"
    )
    acknowledged_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="acknowledged_vee_exceptions",
        foreign_keys=[acknowledged_by_user_account_id],
    )
    resolved_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="resolved_vee_exceptions",
        foreign_keys=[resolved_by_user_account_id],
    )
    representative_replay_items: Mapped[list["VeeReplayRequestItem"]] = relationship(
        back_populates="representative_vee_exception"
    )
    estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="anchor_vee_exception"
    )
    manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="related_vee_exception"
    )


class VeeReplayRequest(TimestampMixin, Base):
    __tablename__ = "vee_replay_request"
    __table_args__ = (
        Index("ix_vee_replay_request_status", "status"),
        Index("ix_vee_replay_request_request_scope", "request_scope"),
        Index("ix_vee_replay_request_hes_system_id", "hes_system_id"),
        Index("ix_vee_replay_request_ingest_batch_id", "ingest_batch_id"),
        Index("ix_vee_replay_request_requested_by", "requested_by"),
        Index(
            "ix_vee_replay_request_requested_by_user_account_id",
            "requested_by_user_account_id",
        ),
        Index(
            "ix_vee_replay_request_cancelled_by_user_account_id",
            "cancelled_by_user_account_id",
        ),
        Index("ix_vee_replay_request_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by_user_account_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    operator_memo: Mapped[str | None] = mapped_column(Text)
    hes_system_id: Mapped[int | None] = mapped_column(ForeignKey("hes_system.id"))
    ingest_batch_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_batch.id"))
    measured_at_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    measured_at_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_timezone_name: Mapped[str | None] = mapped_column(String(50))
    target_initial_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reopened_exception_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cleared_exception_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_superseded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_recalculated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancelled_by: Mapped[str | None] = mapped_column(String(120))
    cancelled_by_user_account_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    hes_system: Mapped["HesSystem | None"] = relationship(back_populates="vee_replay_requests")
    ingest_batch: Mapped["IngestBatch | None"] = relationship(back_populates="vee_replay_requests")
    requested_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="requested_vee_replay_requests",
        foreign_keys=[requested_by_user_account_id],
    )
    cancelled_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="cancelled_vee_replay_requests",
        foreign_keys=[cancelled_by_user_account_id],
    )
    request_items: Mapped[list["VeeReplayRequestItem"]] = relationship(
        back_populates="vee_replay_request"
    )
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="vee_replay_request")


class VeeReplayRequestItem(TimestampMixin, Base):
    __tablename__ = "vee_replay_request_item"
    __table_args__ = (
        UniqueConstraint(
            "vee_replay_request_id",
            "initial_measurement_id",
            name="uq_vee_replay_request_item_scope",
        ),
        Index("ix_vee_replay_request_item_status", "status"),
        Index("ix_vee_replay_request_item_initial_measurement_id", "initial_measurement_id"),
        Index(
            "ix_vee_replay_request_item_representative_vee_exception_id",
            "representative_vee_exception_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vee_replay_request_id: Mapped[int] = mapped_column(
        ForeignKey("vee_replay_request.id"), nullable=False, index=True
    )
    initial_measurement_id: Mapped[int] = mapped_column(
        ForeignKey("initial_measurement.id"), nullable=False
    )
    representative_vee_exception_id: Mapped[int] = mapped_column(
        ForeignKey("vee_exception.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    result_code: Mapped[str | None] = mapped_column(String(80))
    vee_execution_log_id: Mapped[int | None] = mapped_column(ForeignKey("vee_execution_log.id"))
    previous_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id")
    )
    current_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id")
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    vee_replay_request: Mapped["VeeReplayRequest"] = relationship(back_populates="request_items")
    initial_measurement: Mapped["InitialMeasurement"] = relationship(
        back_populates="vee_replay_request_items"
    )
    representative_vee_exception: Mapped["VeeException"] = relationship(
        back_populates="representative_replay_items"
    )
    vee_execution_log: Mapped["VeeExecutionLog | None"] = relationship()
    previous_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        foreign_keys=[previous_final_measurement_id]
    )
    current_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        foreign_keys=[current_final_measurement_id]
    )


class BillingExportRequest(TimestampMixin, Base):
    __tablename__ = "billing_export_request"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_billing_export_request_status",
        ),
        CheckConstraint(
            "recovery_action_code is null or recovery_action_code in ('rerun', 'recreate')",
            name="ck_billing_export_request_recovery_action_code",
        ),
        Index("ix_billing_export_request_status", "status"),
        Index("ix_billing_export_request_request_scope", "request_scope"),
        Index(
            "ix_billing_export_request_source_billing_export_request_id",
            "source_billing_export_request_id",
        ),
        Index("ix_billing_export_request_recovery_action_code", "recovery_action_code"),
        Index("ix_billing_export_request_service_point_id", "service_point_id"),
        Index("ix_billing_export_request_target_system_code", "target_system_code"),
        Index("ix_billing_export_request_payload_format", "payload_format"),
        Index("ix_billing_export_request_requested_by", "requested_by"),
        Index(
            "ix_billing_export_request_requested_by_user_account_id",
            "requested_by_user_account_id",
        ),
        Index("ix_billing_export_request_cancelled_by_user_account_id", "cancelled_by_user_account_id"),
        Index("ix_billing_export_request_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_scope: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    source_billing_export_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_export_request.id")
    )
    recovery_action_code: Mapped[str | None] = mapped_column(String(30))
    service_point_id: Mapped[int | None] = mapped_column(ForeignKey("service_point.id"))
    billing_period_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing_period_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_system_code: Mapped[str] = mapped_column(String(60), nullable=False)
    payload_format: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_by_user_account_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    operator_memo: Mapped[str | None] = mapped_column(Text)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    cancelled_by: Mapped[str | None] = mapped_column(String(120))
    cancelled_by_user_account_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    service_point: Mapped["ServicePoint | None"] = relationship(
        back_populates="billing_export_requests"
    )
    request_items: Mapped[list["BillingExportItem"]] = relationship(
        back_populates="billing_export_request"
    )
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(
        back_populates="billing_export_request"
    )
    requested_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="requested_billing_export_requests",
        foreign_keys=[requested_by_user_account_id],
    )
    cancelled_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="cancelled_billing_export_requests",
        foreign_keys=[cancelled_by_user_account_id],
    )
    source_billing_export_request: Mapped["BillingExportRequest | None"] = relationship(
        remote_side=[id],
        foreign_keys=[source_billing_export_request_id],
        back_populates="recovery_requests",
    )
    recovery_requests: Mapped[list["BillingExportRequest"]] = relationship(
        back_populates="source_billing_export_request",
        foreign_keys=[source_billing_export_request_id],
    )


class BillingExportItem(TimestampMixin, Base):
    __tablename__ = "billing_export_item"
    __table_args__ = (
        CheckConstraint(
            "summary_status in ('complete', 'partial', 'blocked')",
            name="ck_billing_export_item_summary_status",
        ),
        CheckConstraint(
            "status in ('pending', 'processing', 'completed', 'failed', 'skipped')",
            name="ck_billing_export_item_status",
        ),
        Index("ix_billing_export_item_status", "status"),
        Index("ix_billing_export_item_service_point_id", "service_point_id"),
        Index(
            "ix_billing_export_item_source_billing_export_item_id",
            "source_billing_export_item_id",
        ),
        Index(
            "ix_billing_export_item_request_period_start_at",
            "billing_export_request_id",
            "billing_period_start_at",
        ),
        Index(
            "ix_billing_export_item_service_point_period_start_at",
            "service_point_id",
            "billing_period_start_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    billing_export_request_id: Mapped[int] = mapped_column(
        ForeignKey("billing_export_request.id"), nullable=False, index=True
    )
    source_billing_export_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_export_item.id")
    )
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    billing_period_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    billing_period_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    tariff_plan_code: Mapped[str | None] = mapped_column(String(60))
    summary_status: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    result_code: Mapped[str | None] = mapped_column(String(80))
    payload_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    billing_export_request: Mapped["BillingExportRequest"] = relationship(
        back_populates="request_items"
    )
    service_point: Mapped["ServicePoint"] = relationship(back_populates="billing_export_items")
    source_billing_export_item: Mapped["BillingExportItem | None"] = relationship(
        remote_side=[id],
        foreign_keys=[source_billing_export_item_id],
        back_populates="recovery_items",
    )
    recovery_items: Mapped[list["BillingExportItem"]] = relationship(
        back_populates="source_billing_export_item",
        foreign_keys=[source_billing_export_item_id],
    )


class FinalMeasurement(TimestampMixin, Base):
    __tablename__ = "final_measurement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    initial_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("initial_measurement.id"), index=True
    )
    canonical_measurement_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_measurement.id"), nullable=False, index=True
    )
    measuring_component_id: Mapped[int] = mapped_column(
        ForeignKey("measuring_component.id"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    quality_code: Mapped[str | None] = mapped_column(String(40))
    status_code: Mapped[str | None] = mapped_column(String(40))
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)
    final_status: Mapped[str] = mapped_column(String(30), nullable=False, default="finalized")
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision_reason_code: Mapped[str | None] = mapped_column(String(60))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    supersedes_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id"),
        index=True,
    )

    initial_measurement: Mapped["InitialMeasurement | None"] = relationship(
        back_populates="final_measurements",
        overlaps="final_measurement",
    )
    canonical_measurement: Mapped[CanonicalMeasurement] = relationship(
        back_populates="final_measurements",
        overlaps="final_measurement",
    )
    supersedes_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        remote_side=lambda: [FinalMeasurement.id]
    )
    previous_source_estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="source_previous_final_measurement",
        foreign_keys=lambda: [EstimationAudit.source_previous_final_measurement_id],
    )
    next_source_estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="source_next_final_measurement",
        foreign_keys=lambda: [EstimationAudit.source_next_final_measurement_id],
    )
    superseded_estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="superseded_final_measurement",
        foreign_keys=lambda: [EstimationAudit.superseded_final_measurement_id],
    )
    result_estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="result_final_measurement",
        foreign_keys=lambda: [EstimationAudit.result_final_measurement_id],
    )
    superseded_manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="superseded_final_measurement",
        foreign_keys=lambda: [ManualEditAudit.superseded_final_measurement_id],
    )
    result_manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="result_final_measurement",
        foreign_keys=lambda: [ManualEditAudit.result_final_measurement_id],
    )


class EstimationAudit(TimestampMixin, Base):
    __tablename__ = "estimation_audit"
    __table_args__ = (
        CheckConstraint(
            "strategy_code in ('linear_interpolation', 'previous_value_based')",
            name="ck_estimation_audit_strategy_code",
        ),
        CheckConstraint(
            "estimation_status in ('applied', 'blocked', 'failed')",
            name="ck_estimation_audit_estimation_status",
        ),
        CheckConstraint(
            "estimation_mode in ('substitution', 'synthetic_missing_interval')",
            name="ck_estimation_audit_estimation_mode",
        ),
        Index(
            "ix_estimation_audit_target_initial_measurement_id",
            "target_initial_measurement_id",
        ),
        Index(
            "ix_estimation_audit_target_measured_at",
            "target_measured_at",
        ),
        Index(
            "ix_estimation_audit_estimation_status",
            "estimation_status",
        ),
        Index(
            "ix_estimation_audit_strategy_code",
            "strategy_code",
        ),
        Index(
            "ix_estimation_audit_service_point_target_measured_at",
            "service_point_id",
            "target_measured_at",
        ),
        Index(
            "ix_estimation_audit_pipeline_run_id",
            "pipeline_run_id",
        ),
        Index(
            "ix_estimation_audit_anchor_vee_exception_id",
            "anchor_vee_exception_id",
        ),
        Index(
            "ix_estimation_audit_raw_interval_window_state_id",
            "raw_interval_window_state_id",
        ),
        Index(
            "ix_estimation_audit_estimation_mode",
            "estimation_mode",
        ),
        Index(
            "ix_estimation_audit_estimated_by_user_account_id",
            "estimated_by_user_account_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measuring_component_id: Mapped[int] = mapped_column(
        ForeignKey("measuring_component.id"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    target_initial_measurement_id: Mapped[int] = mapped_column(
        ForeignKey("initial_measurement.id"), nullable=False
    )
    anchor_vee_exception_id: Mapped[int | None] = mapped_column(
        ForeignKey("vee_exception.id"),
        index=True,
    )
    raw_interval_window_state_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_interval_window_state.id"),
        index=True,
    )
    target_measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    estimation_mode: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="substitution",
    )
    estimated_by: Mapped[str | None] = mapped_column(String(120))
    estimated_by_user_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_account.id")
    )
    strategy_code: Mapped[str] = mapped_column(String(40), nullable=False)
    estimation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    unit_of_measure: Mapped[str | None] = mapped_column(String(20))
    source_previous_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id")
    )
    source_next_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id")
    )
    superseded_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id")
    )
    result_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id")
    )
    operator_memo: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    pipeline_run: Mapped["PipelineRun | None"] = relationship(back_populates="estimation_audits")
    service_point: Mapped["ServicePoint"] = relationship(back_populates="estimation_audits")
    measuring_component: Mapped["MeasuringComponent"] = relationship(
        back_populates="estimation_audits"
    )
    device: Mapped["Device"] = relationship(back_populates="estimation_audits")
    target_initial_measurement: Mapped["InitialMeasurement"] = relationship(
        back_populates="estimation_audits"
    )
    anchor_vee_exception: Mapped["VeeException | None"] = relationship(
        back_populates="estimation_audits"
    )
    raw_interval_window_state: Mapped["RawIntervalWindowState | None"] = relationship(
        back_populates="estimation_audits"
    )
    estimated_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="estimated_estimation_audits",
        foreign_keys=[estimated_by_user_account_id],
    )
    source_previous_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        back_populates="previous_source_estimation_audits",
        foreign_keys=[source_previous_final_measurement_id],
    )
    source_next_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        back_populates="next_source_estimation_audits",
        foreign_keys=[source_next_final_measurement_id],
    )
    superseded_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        back_populates="superseded_estimation_audits",
        foreign_keys=[superseded_final_measurement_id],
    )
    result_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        back_populates="result_estimation_audits",
        foreign_keys=[result_final_measurement_id],
    )


class ManualEditAudit(TimestampMixin, Base):
    __tablename__ = "manual_edit_audit"
    __table_args__ = (
        CheckConstraint(
            "edit_status in ('applied', 'blocked', 'failed')",
            name="ck_manual_edit_audit_edit_status",
        ),
        Index(
            "ix_manual_edit_audit_target_initial_measurement_id",
            "target_initial_measurement_id",
        ),
        Index(
            "ix_manual_edit_audit_related_vee_exception_id",
            "related_vee_exception_id",
        ),
        Index(
            "ix_manual_edit_audit_target_measured_at",
            "target_measured_at",
        ),
        Index(
            "ix_manual_edit_audit_edit_status",
            "edit_status",
        ),
        Index(
            "ix_manual_edit_audit_reason_code",
            "reason_code",
        ),
        Index(
            "ix_manual_edit_audit_service_point_target_measured_at",
            "service_point_id",
            "target_measured_at",
        ),
        Index(
            "ix_manual_edit_audit_pipeline_run_id",
            "pipeline_run_id",
        ),
        Index(
            "ix_manual_edit_audit_edited_by_user_account_id",
            "edited_by_user_account_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measuring_component_id: Mapped[int] = mapped_column(
        ForeignKey("measuring_component.id"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    target_initial_measurement_id: Mapped[int] = mapped_column(
        ForeignKey("initial_measurement.id"), nullable=False
    )
    related_vee_exception_id: Mapped[int] = mapped_column(
        ForeignKey("vee_exception.id"), nullable=False
    )
    target_measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(60), nullable=False)
    edit_status: Mapped[str] = mapped_column(String(30), nullable=False)
    edited_value: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    edited_quality_code: Mapped[str | None] = mapped_column(String(40))
    edited_status_code: Mapped[str | None] = mapped_column(String(40))
    edited_by: Mapped[str] = mapped_column(String(120), nullable=False)
    edited_by_user_account_id: Mapped[int | None] = mapped_column(ForeignKey("user_account.id"))
    operator_memo: Mapped[str | None] = mapped_column(Text)
    superseded_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id")
    )
    result_final_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("final_measurement.id")
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    pipeline_run: Mapped["PipelineRun | None"] = relationship(back_populates="manual_edit_audits")
    service_point: Mapped["ServicePoint"] = relationship(back_populates="manual_edit_audits")
    measuring_component: Mapped["MeasuringComponent"] = relationship(
        back_populates="manual_edit_audits"
    )
    device: Mapped["Device"] = relationship(back_populates="manual_edit_audits")
    target_initial_measurement: Mapped["InitialMeasurement"] = relationship(
        back_populates="manual_edit_audits"
    )
    related_vee_exception: Mapped["VeeException"] = relationship(
        back_populates="manual_edit_audits"
    )
    edited_by_user_account: Mapped["UserAccount | None"] = relationship(
        back_populates="edited_manual_edit_audits",
        foreign_keys=[edited_by_user_account_id],
    )
    superseded_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        back_populates="superseded_manual_edit_audits",
        foreign_keys=[superseded_final_measurement_id],
    )
    result_final_measurement: Mapped["FinalMeasurement | None"] = relationship(
        back_populates="result_manual_edit_audits",
        foreign_keys=[result_final_measurement_id],
    )


class UsageTransaction(TimestampMixin, Base):
    __tablename__ = "usage_transaction"
    __table_args__ = (
        UniqueConstraint(
            "service_point_id",
            "measuring_component_id",
            "usage_type",
            "period_start_at",
            "period_end_at",
            name="uq_usage_transaction_scope",
        ),
        Index("ix_usage_transaction_usage_type", "usage_type"),
        Index("ix_usage_transaction_period_start_at", "period_start_at"),
        Index("ix_usage_transaction_calculation_status", "calculation_status"),
        Index(
            "ix_usage_transaction_service_point_period_start_at",
            "service_point_id",
            "period_start_at",
        ),
        Index(
            "ix_usage_transaction_measuring_component_period_start_at",
            "measuring_component_id",
            "period_start_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measuring_component_id: Mapped[int] = mapped_column(
        ForeignKey("measuring_component.id"), nullable=False
    )
    device_id: Mapped[int] = mapped_column(ForeignKey("device.id"), nullable=False)
    usage_type: Mapped[str] = mapped_column(String(40), nullable=False)
    period_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_timezone_name: Mapped[str] = mapped_column(String(50), nullable=False)
    interval_size_minutes: Mapped[int | None] = mapped_column(Integer)
    unit_of_measure: Mapped[str | None] = mapped_column(String(20))
    usage_value: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    source_final_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_interval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_summary: Mapped[str] = mapped_column(String(80), nullable=False)
    calculation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="usage_transactions")
    service_point: Mapped["ServicePoint"] = relationship(back_populates="usage_transactions")
    measuring_component: Mapped["MeasuringComponent"] = relationship(
        back_populates="usage_transactions"
    )
    device: Mapped["Device"] = relationship(back_populates="usage_transactions")


class BillDeterminant(TimestampMixin, Base):
    __tablename__ = "bill_determinant"
    __table_args__ = (
        Index("ix_bill_determinant_determinant_type", "determinant_type"),
        Index("ix_bill_determinant_billing_period_start_at", "billing_period_start_at"),
        Index("ix_bill_determinant_calculation_status", "calculation_status"),
        Index(
            "ix_bill_determinant_service_point_billing_period_start_at",
            "service_point_id",
            "billing_period_start_at",
        ),
        Index(
            "ix_bill_determinant_measuring_component_billing_period_start_at",
            "measuring_component_id",
            "billing_period_start_at",
        ),
        Index("ix_bill_determinant_is_current", "is_current"),
        Index(
            "ix_bill_determinant_supersedes_bill_determinant_id",
            "supersedes_bill_determinant_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measuring_component_id: Mapped[int | None] = mapped_column(
        ForeignKey("measuring_component.id")
    )
    device_id: Mapped[int | None] = mapped_column(ForeignKey("device.id"))
    determinant_type: Mapped[str] = mapped_column(String(60), nullable=False)
    billing_period_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    billing_period_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_timezone_name: Mapped[str] = mapped_column(String(50), nullable=False)
    tariff_plan_code: Mapped[str | None] = mapped_column(String(60))
    tou_bucket_code: Mapped[str | None] = mapped_column(String(60))
    demand_window_code: Mapped[str | None] = mapped_column(String(60))
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)
    determinant_value: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    source_usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_summary: Mapped[str] = mapped_column(String(80), nullable=False)
    calculation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision_reason_code: Mapped[str | None] = mapped_column(String(60))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supersedes_bill_determinant_id: Mapped[int | None] = mapped_column(
        ForeignKey("bill_determinant.id")
    )
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="bill_determinants")
    service_point: Mapped["ServicePoint"] = relationship(back_populates="bill_determinants")
    measuring_component: Mapped["MeasuringComponent | None"] = relationship(
        back_populates="bill_determinants"
    )
    device: Mapped["Device | None"] = relationship(back_populates="bill_determinants")
    bill_charges: Mapped[list["BillCharge"]] = relationship(back_populates="bill_determinant")
    supersedes_bill_determinant: Mapped["BillDeterminant | None"] = relationship(
        remote_side=lambda: [BillDeterminant.id]
    )


class BillCharge(TimestampMixin, Base):
    __tablename__ = "bill_charge"
    __table_args__ = (
        Index("ix_bill_charge_charge_type", "charge_type"),
        Index("ix_bill_charge_billing_period_start_at", "billing_period_start_at"),
        Index("ix_bill_charge_calculation_status", "calculation_status"),
        Index("ix_bill_charge_bill_determinant_id", "bill_determinant_id"),
        Index(
            "ix_bill_charge_service_point_billing_period_start_at",
            "service_point_id",
            "billing_period_start_at",
        ),
        Index(
            "ix_bill_charge_measuring_component_billing_period_start_at",
            "measuring_component_id",
            "billing_period_start_at",
        ),
        Index("ix_bill_charge_is_current", "is_current"),
        Index(
            "ix_bill_charge_supersedes_bill_charge_id",
            "supersedes_bill_charge_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_run.id"), nullable=False)
    service_point_id: Mapped[int] = mapped_column(ForeignKey("service_point.id"), nullable=False)
    measuring_component_id: Mapped[int | None] = mapped_column(
        ForeignKey("measuring_component.id")
    )
    device_id: Mapped[int | None] = mapped_column(ForeignKey("device.id"))
    bill_determinant_id: Mapped[int] = mapped_column(
        ForeignKey("bill_determinant.id"), nullable=False
    )
    charge_type: Mapped[str] = mapped_column(String(60), nullable=False)
    billing_period_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    billing_period_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    tariff_plan_code: Mapped[str | None] = mapped_column(String(60))
    tariff_version_code: Mapped[str | None] = mapped_column(String(60))
    quantity_value: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    unit_rate_value: Mapped[Decimal | None] = mapped_column(Numeric(19, 8))
    charge_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    calculation_status: Mapped[str] = mapped_column(String(30), nullable=False)
    quality_summary: Mapped[str] = mapped_column(String(80), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision_reason_code: Mapped[str | None] = mapped_column(String(60))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supersedes_bill_charge_id: Mapped[int | None] = mapped_column(ForeignKey("bill_charge.id"))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="bill_charges")
    service_point: Mapped["ServicePoint"] = relationship(back_populates="bill_charges")
    measuring_component: Mapped["MeasuringComponent | None"] = relationship(
        back_populates="bill_charges"
    )
    device: Mapped["Device | None"] = relationship(back_populates="bill_charges")
    bill_determinant: Mapped["BillDeterminant"] = relationship(back_populates="bill_charges")
    supersedes_bill_charge: Mapped["BillCharge | None"] = relationship(
        remote_side=lambda: [BillCharge.id]
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
    estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="raw_interval_window_state"
    )


class IngestErrorLog(TimestampMixin, Base):
    __tablename__ = "ingest_error_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exception_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    exception_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    hes_read_raw_id: Mapped[int | None] = mapped_column(Integer, index=True)
    hes_read_raw_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hes_event_raw_id: Mapped[int | None] = mapped_column(ForeignKey("hes_event_raw.id"))
    hes_read_raw: Mapped[HesReadRaw | None] = relationship(
        back_populates="error_logs",
        primaryjoin=lambda: foreign(IngestErrorLog.hes_read_raw_id) == HesReadRaw.id,
    )
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
    hes_read_raw_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    hes_read_raw_measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="processing")
    result_code: Mapped[str | None] = mapped_column(String(80))
    result_message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ingest_error_log: Mapped[IngestErrorLog] = relationship(back_populates="reprocess_requests")
    hes_read_raw: Mapped[HesReadRaw] = relationship(
        back_populates="reprocess_requests",
        primaryjoin=lambda: foreign(ReprocessRequest.hes_read_raw_id) == HesReadRaw.id,
    )
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="reprocess_request")


class PipelineRun(TimestampMixin, Base):
    __tablename__ = "pipeline_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="processing")
    ingest_batch_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_batch.id"))
    reprocess_request_id: Mapped[int | None] = mapped_column(ForeignKey("reprocess_request.id"))
    vee_replay_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("vee_replay_request.id"),
        index=True,
    )
    billing_export_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("billing_export_request.id"),
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_code: Mapped[str | None] = mapped_column(String(80))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    ingest_batch: Mapped[IngestBatch | None] = relationship(back_populates="pipeline_runs")
    reprocess_request: Mapped[ReprocessRequest | None] = relationship(back_populates="pipeline_runs")
    vee_replay_request: Mapped["VeeReplayRequest | None"] = relationship(
        back_populates="pipeline_runs"
    )
    billing_export_request: Mapped["BillingExportRequest | None"] = relationship(
        back_populates="pipeline_runs"
    )
    vee_execution_logs: Mapped[list["VeeExecutionLog"]] = relationship(back_populates="pipeline_run")
    estimation_audits: Mapped[list["EstimationAudit"]] = relationship(
        back_populates="pipeline_run"
    )
    manual_edit_audits: Mapped[list["ManualEditAudit"]] = relationship(
        back_populates="pipeline_run"
    )
    usage_transactions: Mapped[list["UsageTransaction"]] = relationship(
        back_populates="pipeline_run"
    )
    bill_determinants: Mapped[list["BillDeterminant"]] = relationship(
        back_populates="pipeline_run"
    )
    bill_charges: Mapped[list["BillCharge"]] = relationship(back_populates="pipeline_run")


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


class OperationalEvent(Base):
    __tablename__ = "operational_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    source_layer: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    event_category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    event_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    alert_status: Mapped[str | None] = mapped_column(String(20), index=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(String(100))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    operator_memo: Mapped[str | None] = mapped_column(Text)
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    title_ko: Mapped[str] = mapped_column(String(200), nullable=False)
    message_en: Mapped[str] = mapped_column(Text, nullable=False)
    message_ko: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    hes_system_id: Mapped[int | None] = mapped_column(ForeignKey("hes_system.id"), index=True)
    adapter_instance_id: Mapped[int | None] = mapped_column(ForeignKey("adapter_instance.id"), index=True)
    adapter_run_id: Mapped[int | None] = mapped_column(ForeignKey("adapter_run.id"), index=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_run.id"), index=True)
    ingest_batch_id: Mapped[int | None] = mapped_column(ForeignKey("ingest_batch.id"), index=True)
    ingest_error_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingest_error_log.id"), index=True
    )
    reprocess_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("reprocess_request.id"), index=True
    )
    meter_identifier: Mapped[str | None] = mapped_column(String(100), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(100), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    hes_system: Mapped["HesSystem | None"] = relationship(back_populates="operational_events")
