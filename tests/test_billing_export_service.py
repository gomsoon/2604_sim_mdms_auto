from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    BillCharge,
    BillDeterminant,
    BillingExportItem,
    BillingExportRequest,
    Device,
    MeasuringComponent,
    OperationalEvent,
    PipelineRun,
    ServicePoint,
)
from app.services.billing_export_processor import process_queued_billing_export_requests
from app.services.billing_export_requests import (
    BillingExportRequestError,
    cancel_billing_export_request,
    create_billing_export_request,
    recreate_billing_export_request,
    rerun_billing_export_request,
)
from app.services.auth import create_user_account
from app.services.seeds import seed_master_data


def _prepare_export_environment(session) -> tuple[int, int, int]:
    seed_master_data(session)
    session.commit()
    service_point_id = session.scalar(select(ServicePoint.id).limit(1))
    device_id = session.scalar(select(Device.id).limit(1))
    measuring_component_id = session.scalar(select(MeasuringComponent.id).limit(1))
    assert service_point_id is not None
    assert device_id is not None
    assert measuring_component_id is not None
    return service_point_id, device_id, measuring_component_id


def _create_current_bill_charge(
    session,
    *,
    service_point_id: int,
    device_id: int,
    measuring_component_id: int,
    period_start_at: datetime,
    period_end_at: datetime,
    calculation_status: str,
    quality_summary: str,
    quantity_value: Decimal,
    unit_rate_value: Decimal | None,
    charge_amount: Decimal | None,
    currency_code: str = "KRW",
    tariff_plan_code: str = "KR_BASIC",
) -> BillCharge:
    now = datetime.now(timezone.utc)
    determinant_run = PipelineRun(
        pipeline_name="bill_determinant",
        trigger_type="manual",
        status="completed",
        started_at=now,
        completed_at=now,
        result_code="bill_determinant_completed",
        details={"trigger_source": "test"},
    )
    charge_run = PipelineRun(
        pipeline_name="bill_charge",
        trigger_type="manual",
        status="completed",
        started_at=now,
        completed_at=now,
        result_code="bill_charge_completed",
        details={"trigger_source": "test"},
    )
    session.add_all([determinant_run, charge_run])
    session.flush()

    determinant = BillDeterminant(
        pipeline_run_id=determinant_run.id,
        service_point_id=service_point_id,
        measuring_component_id=measuring_component_id,
        device_id=device_id,
        determinant_type="billing_cycle_consumption_total",
        billing_period_start_at=period_start_at,
        billing_period_end_at=period_end_at,
        window_timezone_name="Asia/Seoul",
        tariff_plan_code=tariff_plan_code,
        tou_bucket_code=None,
        demand_window_code=None,
        unit_of_measure="kWh",
        determinant_value=quantity_value,
        source_usage_count=1,
        quality_summary=quality_summary,
        calculation_status=calculation_status,
        revision_number=1,
        revision_reason_code=None,
        is_current=True,
        supersedes_bill_determinant_id=None,
        calculated_at=now,
        details={"trigger_source": "test"},
    )
    session.add(determinant)
    session.flush()

    charge = BillCharge(
        pipeline_run_id=charge_run.id,
        service_point_id=service_point_id,
        measuring_component_id=measuring_component_id,
        device_id=device_id,
        bill_determinant_id=determinant.id,
        charge_type="flat_energy_charge",
        billing_period_start_at=period_start_at,
        billing_period_end_at=period_end_at,
        currency_code=currency_code,
        tariff_plan_code=tariff_plan_code,
        tariff_version_code="v1",
        quantity_value=quantity_value,
        unit_rate_value=unit_rate_value,
        charge_amount=charge_amount,
        calculation_status=calculation_status,
        quality_summary=quality_summary,
        revision_number=1,
        revision_reason_code=None,
        is_current=True,
        supersedes_bill_charge_id=None,
        calculated_at=now,
        details={"trigger_source": "test"},
    )
    session.add(charge)
    session.commit()
    return charge


def _create_failed_billing_export_request(
    session,
    monkeypatch,
    *,
    service_point_id: int,
    device_id: int,
    measuring_component_id: int,
    period_start_at: datetime,
    period_end_at: datetime,
    quantity_value: Decimal,
    unit_rate_value: Decimal,
    charge_amount: Decimal,
    requested_by: str = "operator_ui",
    requested_by_user_account_id: int | None = None,
) -> int:
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=period_start_at,
        period_end_at=period_end_at,
        calculation_status="complete",
        quality_summary="all_finalized",
        quantity_value=quantity_value,
        unit_rate_value=unit_rate_value,
        charge_amount=charge_amount,
    )
    created = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=service_point_id,
        billing_period_from=period_start_at,
        billing_period_to=period_end_at,
        requested_by=requested_by,
        requested_by_user_account_id=requested_by_user_account_id,
    )
    session.commit()

    from app.services import billing_export_processor as processor_module

    def _boom(*args, **kwargs):
        raise RuntimeError("forced export failure")

    monkeypatch.setattr(processor_module, "_process_pending_item", _boom)
    process_queued_billing_export_requests(session, limit=1, processed_by="worker_fail")
    session.commit()
    return created.request.id


def test_create_billing_export_request_creates_pending_and_skipped_items(session):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    actor = create_user_account(
        session,
        login_id="billing-export-create-actor",
        display_name="Billing Export Create Actor",
        role_code="admin",
        password="test-password",
    )
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        calculation_status="complete",
        quality_summary="all_finalized",
        quantity_value=Decimal("100.0000"),
        unit_rate_value=Decimal("120.00000000"),
        charge_amount=Decimal("12000.0000"),
    )
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        calculation_status="blocked",
        quality_summary="blocked_missing_tariff_assignment",
        quantity_value=Decimal("50.0000"),
        unit_rate_value=None,
        charge_amount=None,
    )

    result = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=service_point_id,
        billing_period_from=datetime(2026, 4, 1, tzinfo=timezone.utc),
        billing_period_to=datetime(2026, 6, 1, tzinfo=timezone.utc),
        requested_by=actor.login_id,
        requested_by_user_account_id=actor.id,
    )
    session.commit()

    request = result.request
    items = session.scalars(
        select(BillingExportItem)
        .where(BillingExportItem.billing_export_request_id == request.id)
        .order_by(BillingExportItem.billing_period_start_at.asc())
    ).all()
    requested_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "billing_export_requested")
        .where(OperationalEvent.entity_id == request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )

    assert result.created_item_count == 2
    assert result.eligible_item_count == 1
    assert result.skipped_item_count == 1
    assert request.status == "queued"
    assert request.requested_by == actor.login_id
    assert request.requested_by_user_account_id == actor.id
    assert request.item_count == 2
    assert request.processed_count == 1
    assert request.skipped_count == 1
    assert request.details["progress_percent"] == 50.0
    assert request.details["eligible_item_count"] == 1
    assert request.details["requested_by"] == actor.login_id
    assert request.details["requested_by_user_account_id"] == actor.id
    assert len(items) == 2
    assert items[0].status == "pending"
    assert items[0].payload_snapshot["invoice_summary_snapshot"]["export_eligible"] is True
    assert items[0].payload_snapshot["source_bill_charge_rows"]
    assert items[1].status == "skipped"
    assert items[1].result_code == "summary_not_exportable"
    assert items[1].payload_snapshot["export_eligibility_snapshot"]["skip_reason"] == (
        "summary_not_exportable"
    )
    assert requested_event is not None
    assert requested_event.details["requested_by"] == actor.login_id
    assert requested_event.details["requested_by_user_account_id"] == actor.id
    assert requested_event.details["skipped_count"] == 1


def test_create_billing_export_request_completes_immediately_when_all_items_skipped(session):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        calculation_status="blocked",
        quality_summary="blocked_missing_tariff_assignment",
        quantity_value=Decimal("70.0000"),
        unit_rate_value=None,
        charge_amount=None,
    )

    result = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=service_point_id,
        billing_period_from=datetime(2026, 7, 1, tzinfo=timezone.utc),
        billing_period_to=datetime(2026, 8, 1, tzinfo=timezone.utc),
        requested_by="operator_ui",
    )
    session.commit()

    request = result.request
    completed_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "billing_export_completed")
        .where(OperationalEvent.entity_id == request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )

    assert request.status == "completed"
    assert request.completed_at is not None
    assert request.item_count == 1
    assert request.processed_count == 1
    assert request.skipped_count == 1
    assert request.details["completion_reason"] == "all_items_skipped"
    assert request.details["progress_percent"] == 100.0
    assert completed_event is not None


def test_process_queued_billing_export_requests_completes_request(session):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        calculation_status="complete",
        quality_summary="all_finalized",
        quantity_value=Decimal("88.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("8800.0000"),
    )
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        calculation_status="partial",
        quality_summary="missing_intervals",
        quantity_value=Decimal("90.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("9000.0000"),
    )
    created = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=service_point_id,
        billing_period_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
        billing_period_to=datetime(2026, 10, 1, tzinfo=timezone.utc),
        requested_by="operator_ui",
    )
    session.commit()

    summary = process_queued_billing_export_requests(session, limit=1, processed_by="worker_a")

    request = session.get(BillingExportRequest, created.request.id)
    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.billing_export_request_id == created.request.id)
        .limit(1)
    )
    items = session.scalars(
        select(BillingExportItem)
        .where(BillingExportItem.billing_export_request_id == created.request.id)
        .order_by(BillingExportItem.billing_period_start_at.asc())
    ).all()
    started_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "billing_export_started")
        .where(OperationalEvent.entity_id == created.request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    completed_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "billing_export_completed")
        .where(OperationalEvent.entity_id == created.request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )

    assert summary.claimed_requests == 1
    assert summary.completed_requests == 1
    assert summary.failed_requests == 0
    assert summary.processed_items == 1
    assert summary.succeeded_items == 1
    assert summary.failed_items == 0
    assert summary.skipped_items == 1
    assert request is not None
    assert request.status == "completed"
    assert request.claimed_by == "worker_a"
    assert request.started_at is not None
    assert request.completed_at is not None
    assert request.last_heartbeat_at is not None
    assert request.processed_count == 2
    assert request.succeeded_count == 1
    assert request.failed_count == 0
    assert request.skipped_count == 1
    assert request.details["progress_percent"] == 100.0
    assert request.details["last_processed_result_code"] == "payload_snapshot_staged"
    assert len(items) == 2
    assert items[0].status == "completed"
    assert items[0].exported_at is not None
    assert items[0].result_code == "payload_snapshot_staged"
    assert items[1].status == "skipped"
    assert pipeline_run is not None
    assert pipeline_run.status == "completed"
    assert started_event is not None
    assert completed_event is not None


def test_process_queued_billing_export_requests_marks_request_failed_when_item_errors(
    session,
    monkeypatch,
):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        calculation_status="complete",
        quality_summary="all_finalized",
        quantity_value=Decimal("45.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("4500.0000"),
    )
    created = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=service_point_id,
        billing_period_from=datetime(2026, 10, 1, tzinfo=timezone.utc),
        billing_period_to=datetime(2026, 11, 1, tzinfo=timezone.utc),
        requested_by="operator_ui",
    )
    session.commit()

    from app.services import billing_export_processor as processor_module

    def _boom(*args, **kwargs):
        raise RuntimeError("forced export failure")

    monkeypatch.setattr(processor_module, "_process_pending_item", _boom)

    summary = process_queued_billing_export_requests(session, limit=1, processed_by="worker_b")

    request = session.get(BillingExportRequest, created.request.id)
    item = session.scalar(
        select(BillingExportItem)
        .where(BillingExportItem.billing_export_request_id == created.request.id)
        .limit(1)
    )
    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.billing_export_request_id == created.request.id)
        .limit(1)
    )
    failed_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "billing_export_failed")
        .where(OperationalEvent.entity_id == created.request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )

    assert summary.claimed_requests == 1
    assert summary.completed_requests == 0
    assert summary.failed_requests == 1
    assert summary.processed_items == 1
    assert summary.succeeded_items == 0
    assert summary.failed_items == 1
    assert request is not None
    assert request.status == "failed"
    assert request.failed_count == 1
    assert request.last_error == "forced export failure"
    assert item is not None
    assert item.status == "failed"
    assert item.result_code == "processing_error"
    assert item.last_error == "forced export failure"
    assert pipeline_run is not None
    assert pipeline_run.status == "failed"
    assert failed_event is not None


def test_cancel_billing_export_request_allows_only_queued_requests(session):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    request_actor = create_user_account(
        session,
        login_id="billing-export-request-actor",
        display_name="Billing Export Request Actor",
        role_code="admin",
        password="test-password",
    )
    cancel_actor = create_user_account(
        session,
        login_id="billing-export-cancel-actor",
        display_name="Billing Export Cancel Actor",
        role_code="admin",
        password="test-password",
    )
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
        calculation_status="complete",
        quality_summary="all_finalized",
        quantity_value=Decimal("64.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("6400.0000"),
    )
    created = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=service_point_id,
        billing_period_from=datetime(2026, 11, 1, tzinfo=timezone.utc),
        billing_period_to=datetime(2026, 12, 1, tzinfo=timezone.utc),
        requested_by=request_actor.login_id,
        requested_by_user_account_id=request_actor.id,
    )

    cancelled = cancel_billing_export_request(
        session,
        created.request.id,
        cancelled_by=cancel_actor.login_id,
        cancelled_by_user_account_id=cancel_actor.id,
        operator_memo="cancel test",
    )
    session.commit()

    cancelled_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "billing_export_cancelled")
        .where(OperationalEvent.entity_id == created.request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )

    assert cancelled.status == "cancelled"
    assert cancelled.completed_at is not None
    assert cancelled.cancelled_by == cancel_actor.login_id
    assert cancelled.cancelled_by_user_account_id == cancel_actor.id
    assert cancelled.cancelled_at is not None
    assert cancelled.details["cancelled_by"] == cancel_actor.login_id
    assert cancelled.details["cancelled_by_user_account_id"] == cancel_actor.id
    assert cancelled_event is not None
    assert cancelled_event.details["cancelled_by"] == cancel_actor.login_id
    assert cancelled_event.details["cancelled_by_user_account_id"] == cancel_actor.id

    with pytest.raises(BillingExportRequestError) as exc_info:
        cancel_billing_export_request(
            session,
            created.request.id,
            cancelled_by=cancel_actor.login_id,
            cancelled_by_user_account_id=cancel_actor.id,
        )

    assert exc_info.value.error_code == "already_cancelled"


def test_rerun_billing_export_request_creates_lineaged_pending_items_from_failed_request(
    session,
    monkeypatch,
):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    source_actor = create_user_account(
        session,
        login_id="billing-export-source-actor",
        display_name="Billing Export Source Actor",
        role_code="admin",
        password="test-password",
    )
    recovery_actor = create_user_account(
        session,
        login_id="billing-export-retry-actor",
        display_name="Billing Export Retry Actor",
        role_code="admin",
        password="test-password",
    )
    source_request_id = _create_failed_billing_export_request(
        session,
        monkeypatch,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2027, 2, 1, tzinfo=timezone.utc),
        quantity_value=Decimal("81.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("8100.0000"),
        requested_by=source_actor.login_id,
        requested_by_user_account_id=source_actor.id,
    )

    result = rerun_billing_export_request(
        session,
        source_request_id,
        requested_by=recovery_actor.login_id,
        requested_by_user_account_id=recovery_actor.id,
        operator_memo="rerun failed export",
    )
    session.commit()

    source_request = session.get(BillingExportRequest, source_request_id)
    recovery_request = result.request
    recovery_items = session.scalars(
        select(BillingExportItem)
        .where(BillingExportItem.billing_export_request_id == recovery_request.id)
        .order_by(BillingExportItem.id.asc())
    ).all()
    source_item = session.scalar(
        select(BillingExportItem)
        .where(BillingExportItem.billing_export_request_id == source_request_id)
        .where(BillingExportItem.status == "failed")
        .limit(1)
    )

    assert source_request is not None
    assert source_request.status == "failed"
    assert source_item is not None
    assert recovery_request.source_billing_export_request_id == source_request_id
    assert recovery_request.recovery_action_code == "rerun"
    assert recovery_request.requested_by == recovery_actor.login_id
    assert recovery_request.requested_by_user_account_id == recovery_actor.id
    assert recovery_request.status == "queued"
    assert recovery_request.processed_count == 0
    assert result.created_item_count == 1
    assert result.eligible_item_count == 1
    assert result.skipped_item_count == 0
    assert len(recovery_items) == 1
    assert recovery_items[0].status == "pending"
    assert recovery_items[0].source_billing_export_item_id == source_item.id
    assert (
        recovery_items[0].payload_snapshot["recovery_lineage_snapshot"][
            "source_billing_export_request_id"
        ]
        == source_request_id
    )
    assert (
        recovery_items[0].payload_snapshot["recovery_lineage_snapshot"][
            "source_billing_export_item_id"
        ]
        == source_item.id
    )
    assert recovery_items[0].payload_snapshot["request_context_snapshot"]["request_id"] == (
        recovery_request.id
    )
    assert recovery_items[0].payload_snapshot["request_context_snapshot"][
        "requested_by_user_account_id"
    ] == recovery_actor.id


def test_recreate_billing_export_request_uses_current_invoice_summary_state(
    session,
    monkeypatch,
):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    source_actor = create_user_account(
        session,
        login_id="billing-export-recreate-source",
        display_name="Billing Export Recreate Source",
        role_code="admin",
        password="test-password",
    )
    recovery_actor = create_user_account(
        session,
        login_id="billing-export-recreate-actor",
        display_name="Billing Export Recreate Actor",
        role_code="admin",
        password="test-password",
    )
    source_request_id = _create_failed_billing_export_request(
        session,
        monkeypatch,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2027, 2, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2027, 3, 1, tzinfo=timezone.utc),
        quantity_value=Decimal("82.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("8200.0000"),
        requested_by=source_actor.login_id,
        requested_by_user_account_id=source_actor.id,
    )

    current_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.billing_period_start_at == datetime(2027, 2, 1, tzinfo=timezone.utc))
        .where(BillCharge.is_current.is_(True))
        .limit(1)
    )
    assert current_charge is not None
    current_charge.charge_amount = Decimal("9150.0000")
    current_charge.calculated_at = datetime(2027, 2, 15, tzinfo=timezone.utc)
    session.commit()

    result = recreate_billing_export_request(
        session,
        source_request_id,
        requested_by=recovery_actor.login_id,
        requested_by_user_account_id=recovery_actor.id,
        operator_memo="recreate with current summary",
    )
    session.commit()

    recovery_request = result.request
    recovery_item = session.scalar(
        select(BillingExportItem)
        .where(BillingExportItem.billing_export_request_id == recovery_request.id)
        .limit(1)
    )

    assert recovery_request.source_billing_export_request_id == source_request_id
    assert recovery_request.recovery_action_code == "recreate"
    assert recovery_request.requested_by == recovery_actor.login_id
    assert recovery_request.requested_by_user_account_id == recovery_actor.id
    assert recovery_request.status == "queued"
    assert result.created_item_count == 1
    assert result.eligible_item_count == 1
    assert result.skipped_item_count == 0
    assert recovery_item is not None
    assert recovery_item.status == "pending"
    assert recovery_item.payload_snapshot["invoice_summary_snapshot"]["subtotal_amount"] == "9150.0000"
    assert (
        recovery_item.payload_snapshot["recovery_lineage_snapshot"]["recovery_action_code"]
        == "recreate"
    )
    assert recovery_item.payload_snapshot["request_context_snapshot"][
        "requested_by_user_account_id"
    ] == recovery_actor.id


def test_rerun_billing_export_request_rejects_non_failed_request(session):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    created_charge = _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2027, 3, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2027, 4, 1, tzinfo=timezone.utc),
        calculation_status="complete",
        quality_summary="all_finalized",
        quantity_value=Decimal("70.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("7000.0000"),
    )
    assert created_charge is not None
    created = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=service_point_id,
        billing_period_from=datetime(2027, 3, 1, tzinfo=timezone.utc),
        billing_period_to=datetime(2027, 4, 1, tzinfo=timezone.utc),
        requested_by="operator_ui",
    )
    session.commit()

    with pytest.raises(BillingExportRequestError) as exc_info:
        rerun_billing_export_request(
            session,
            created.request.id,
            requested_by="operator_retry",
        )

    assert exc_info.value.error_code == "request_not_failed"


def test_rerun_billing_export_request_rejects_when_active_recovery_exists(
    session,
    monkeypatch,
):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    source_request_id = _create_failed_billing_export_request(
        session,
        monkeypatch,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2027, 4, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2027, 5, 1, tzinfo=timezone.utc),
        quantity_value=Decimal("77.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("7700.0000"),
    )

    rerun_billing_export_request(
        session,
        source_request_id,
        requested_by="operator_retry",
    )
    session.commit()

    with pytest.raises(BillingExportRequestError) as exc_info:
        rerun_billing_export_request(
            session,
            source_request_id,
            requested_by="operator_retry",
        )

    assert exc_info.value.error_code == "active_recovery_exists"


def test_process_billing_export_requests_cli_processes_queued_request(app, session):
    service_point_id, device_id, measuring_component_id = _prepare_export_environment(session)
    _create_current_bill_charge(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        period_start_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
        period_end_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        calculation_status="complete",
        quality_summary="all_finalized",
        quantity_value=Decimal("75.0000"),
        unit_rate_value=Decimal("100.00000000"),
        charge_amount=Decimal("7500.0000"),
    )
    created = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=service_point_id,
        billing_period_from=datetime(2026, 12, 1, tzinfo=timezone.utc),
        billing_period_to=datetime(2027, 1, 1, tzinfo=timezone.utc),
        requested_by="operator_ui",
    )
    session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["process-billing-export-requests", "--limit", "1"])

    refreshed = session.get(BillingExportRequest, created.request.id)

    assert result.exit_code == 0
    assert "claimed_requests=1" in result.output
    assert "completed_requests=1" in result.output
    assert refreshed is not None
    assert refreshed.status == "completed"
