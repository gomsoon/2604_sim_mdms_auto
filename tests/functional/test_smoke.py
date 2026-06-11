from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re

from sqlalchemy import select
from playwright.sync_api import Page, expect

from app.models import (
    BillCharge,
    BillDeterminant,
    BillingExportRequest,
    Device,
    HesSystem,
    InitialMeasurement,
    MeasuringComponent,
    PipelineRun,
    ServicePoint,
    UserAccount,
    VeeException,
    VeeReplayRequest,
)
from app.services.billing_export_requests import create_billing_export_request
from app.services.vee import evaluate_or_get_vee_baseline
from app.services.vee_replay_requests import create_vee_replay_request


def _get_functional_admin(session) -> UserAccount:
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "functional-admin").limit(1))
    assert actor is not None
    return actor


def _prepare_open_vee_exception(session) -> VeeException:
    existing = session.scalar(
        select(VeeException)
        .where(VeeException.exception_status == "open")
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    if existing is not None:
        return existing

    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None

    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
    initial.unit_of_measure = ""
    session.flush()

    evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    created = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    assert created is not None
    return created


def _prepare_replay_request(session) -> int:
    existing = session.scalar(
        select(VeeReplayRequest)
        .order_by(VeeReplayRequest.id.desc())
        .limit(1)
    )
    if existing is not None:
        return existing.id

    actor = _get_functional_admin(session)
    vee_exception = _prepare_open_vee_exception(session)
    hes_system = vee_exception.initial_measurement.canonical_measurement.hes_read_raw.hes_system
    assert hes_system is not None

    created = create_vee_replay_request(
        session,
        request_scope="hes_system",
        hes_system_id=hes_system.id,
        requested_by=actor.login_id,
        requested_by_user_account_id=actor.id,
    )
    session.commit()
    return created.request.id


def _prepare_billing_export_request(session) -> int:
    existing = session.scalar(
        select(BillingExportRequest)
        .order_by(BillingExportRequest.id.desc())
        .limit(1)
    )
    if existing is not None:
        return existing.id

    actor = _get_functional_admin(session)
    existing_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.is_current.is_(True))
        .order_by(BillCharge.billing_period_start_at.asc(), BillCharge.id.asc())
        .limit(1)
    )
    if existing_charge is None:
        service_point = session.scalar(select(ServicePoint).limit(1))
        device = session.scalar(select(Device).limit(1))
        measuring_component = session.scalar(select(MeasuringComponent).limit(1))
        assert service_point is not None
        assert device is not None
        assert measuring_component is not None

        now = datetime.now(timezone.utc)
        determinant_run = PipelineRun(
            pipeline_name="bill_determinant",
            trigger_type="manual",
            status="completed",
            started_at=now,
            completed_at=now,
            result_code="bill_determinant_completed",
            details={"trigger_source": "functional_smoke"},
        )
        charge_run = PipelineRun(
            pipeline_name="bill_charge",
            trigger_type="manual",
            status="completed",
            started_at=now,
            completed_at=now,
            result_code="bill_charge_completed",
            details={"trigger_source": "functional_smoke"},
        )
        session.add_all([determinant_run, charge_run])
        session.flush()

        determinant = BillDeterminant(
            pipeline_run_id=determinant_run.id,
            service_point_id=service_point.id,
            measuring_component_id=measuring_component.id,
            device_id=device.id,
            determinant_type="billing_cycle_consumption_total",
            billing_period_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            billing_period_end_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            window_timezone_name="Asia/Seoul",
            tariff_plan_code="KR_BASIC",
            unit_of_measure="kWh",
            determinant_value=Decimal("100.0000"),
            source_usage_count=1,
            quality_summary="all_finalized",
            calculation_status="complete",
            revision_number=1,
            revision_reason_code=None,
            is_current=True,
            supersedes_bill_determinant_id=None,
            calculated_at=now,
            details={"trigger_source": "functional_smoke"},
        )
        session.add(determinant)
        session.flush()

        existing_charge = BillCharge(
            pipeline_run_id=charge_run.id,
            service_point_id=service_point.id,
            measuring_component_id=measuring_component.id,
            device_id=device.id,
            bill_determinant_id=determinant.id,
            charge_type="flat_energy_charge",
            billing_period_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            billing_period_end_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            currency_code="KRW",
            tariff_plan_code="KR_BASIC",
            tariff_version_code="v1",
            quantity_value=Decimal("100.0000"),
            unit_rate_value=Decimal("120.00000000"),
            charge_amount=Decimal("12000.0000"),
            calculation_status="complete",
            quality_summary="all_finalized",
            revision_number=1,
            revision_reason_code=None,
            is_current=True,
            supersedes_bill_charge_id=None,
            calculated_at=now,
            details={"trigger_source": "functional_smoke"},
        )
        session.add(existing_charge)
        session.commit()

    created = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=existing_charge.service_point_id,
        billing_period_from=existing_charge.billing_period_start_at,
        billing_period_to=existing_charge.billing_period_end_at,
        requested_by=actor.login_id,
        requested_by_user_account_id=actor.id,
    )
    session.commit()
    return created.request.id


def test_dashboard_smoke_flow(page: Page):
    page.goto("/?lang=en", wait_until="networkidle")
    stage_cards = page.locator("section.row.g-3.mb-4").first

    expect(page.get_by_role("heading", name="HES raw ingestion, mapping, canonicalization, and exceptions in one place")).to_be_visible()
    expect(stage_cards.get_by_text("Raw Ingest", exact=True)).to_be_visible()
    expect(stage_cards.get_by_text("Canonical", exact=True)).to_be_visible()
    expect(stage_cards.get_by_text("Errors", exact=True)).to_be_visible()
    expect(stage_cards.get_by_text("Usage", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="Recent Raw Reads")).to_be_visible()
    expect(page.locator("table").get_by_text("MTR-1001").first).to_be_visible()
    expect(page.locator(".list-group").get_by_text("measuring_component_not_found")).to_be_visible()


def test_raw_reads_smoke_flow_in_korean(page: Page):
    page.goto("/raw-reads?lang=ko", wait_until="networkidle")

    expect(page.get_by_role("heading", name="원시 검침")).to_be_visible()
    expect(page.locator("table").get_by_text("MTR-1001").first).to_be_visible()
    expect(page.get_by_role("columnheader", name="중복")).to_be_visible()
    expect(page.locator("table").get_by_text("예", exact=True).first).to_be_visible()


def test_exception_queue_detail_smoke_flow_in_korean(page: Page):
    page.goto(
        "/exceptions?lang=ko&meter_id=MTR-9999&exception_code=measuring_component_not_found",
        wait_until="networkidle",
    )

    expect(page.get_by_role("heading", name="오류 큐")).to_be_visible()
    expect(page.get_by_text("MTR-9999")).to_be_visible()
    expect(page.get_by_role("link", name="상세")).to_be_visible()

    page.get_by_role("link", name="상세").click()

    expect(page).to_have_url(re.compile(r".*/exceptions/\d+(?:\?.*)?$"))
    expect(page.get_by_role("heading", name="오류 상세")).to_be_visible()
    expect(page.get_by_role("button", name="재처리")).to_be_visible()
    expect(page.get_by_text('"meter_id": "MTR-9999"')).to_be_visible()


def test_replay_request_list_and_detail_smoke_flow_in_korean(page: Page, functional_session):
    request_id = _prepare_replay_request(functional_session)

    page.goto("/vee-replay-requests?lang=ko", wait_until="networkidle")

    expect(page.get_by_role("heading", name="VEE 재평가 요청")).to_be_visible()
    expect(page.locator("table").get_by_text("Demo HES").first).to_be_visible()
    expect(page.locator("table").get_by_text("Functional Admin (functional-admin)").first).to_be_visible()
    expect(page.locator("table").get_by_role("link", name="상세").first).to_be_visible()

    page.goto(f"/vee-replay-requests/{request_id}?lang=ko", wait_until="networkidle")

    expect(page).to_have_url(re.compile(r".*/vee-replay-requests/\d+(?:\?.*)?$"))
    expect(page.get_by_role("heading", name="VEE 재평가 요청 상세")).to_be_visible()
    expect(page.get_by_role("link", name="Demo HES")).to_be_visible()
    expect(page.get_by_text("Functional Admin (functional-admin)")).to_be_visible()
    expect(page.get_by_text("아직 이 replay request와 연결된 pipeline run이 없습니다.")).to_be_visible()


def test_billing_export_request_list_and_detail_smoke_flow_in_korean(
    page: Page,
    functional_session,
):
    request_id = _prepare_billing_export_request(functional_session)

    page.goto("/billing-export-requests?lang=ko", wait_until="networkidle")

    expect(page.get_by_role("heading", name="청구 내보내기 요청")).to_be_visible()
    expect(page.locator("table").get_by_text("SP-1001").first).to_be_visible()
    expect(page.locator("table").get_by_text("Functional Admin (functional-admin)").first).to_be_visible()
    expect(page.locator("table").get_by_role("link", name="상세").first).to_be_visible()

    page.goto(f"/billing-export-requests/{request_id}?lang=ko", wait_until="networkidle")

    expect(page).to_have_url(re.compile(r".*/billing-export-requests/\d+(?:\?.*)?$"))
    expect(page.get_by_role("heading", name="청구 내보내기 요청 상세")).to_be_visible()
    expect(page.get_by_text("Functional Admin (functional-admin)")).to_be_visible()
    expect(page.get_by_text("이 export request와 연결된 파이프라인 실행이 아직 없습니다.")).to_be_visible()


def test_hes_detail_smoke_flow_in_korean(page: Page, functional_session):
    hes_system = functional_session.scalar(
        select(HesSystem).where(HesSystem.hes_code == "HES").limit(1)
    )
    assert hes_system is not None

    page.goto(f"/hes-systems/{hes_system.id}?lang=ko", wait_until="networkidle")

    expect(page.get_by_role("heading", name="Demo HES")).to_be_visible()
    expect(page.get_by_role("heading", name="연결된 어댑터")).to_be_visible()
    expect(page.get_by_text("demo_hes_poll_primary")).to_be_visible()
    expect(page.get_by_role("heading", name="계량기 참조")).to_be_visible()


def test_master_data_smoke_flow_in_korean(page: Page):
    page.goto("/master-data?lang=ko", wait_until="networkidle")

    expect(page.get_by_role("heading", name="마스터 데이터")).to_be_visible()
    expect(page.locator("#service-points table").get_by_role("cell", name="SP-1001", exact=True)).to_be_visible()
    expect(page.locator("#devices table").get_by_role("cell", name="MTR-1001", exact=True)).to_be_visible()
    expect(page.locator("#components table").get_by_role("cell", name="CH-01", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="설치 이력", exact=True)).to_be_visible()
