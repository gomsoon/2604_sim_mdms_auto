#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import threading
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, Page, sync_playwright
from sqlalchemy import select
from werkzeug.serving import make_server

from app import create_app
from app.db import get_session
from app.migrations import upgrade_db
from app.models import (
    AdapterInstance,
    BillingExportRequest,
    Device,
    HesSystem,
    InstallationHistory,
    MeasuringComponent,
    PipelineRun,
    ServicePoint,
    ServicePointBillingContext,
    ServicePointTariffAssignment,
    UserAccount,
    VeeReplayRequest,
    VeeReplayRequestItem,
)
from app.services.auth import create_user_account
from app.services.finalization import finalize_canonical_measurements
from app.services.operational_events import record_operational_event
from app.services.seeds import seed_demo_environment
from app.services.tariff_assignments import create_tariff_assignment
from app.services.vee_replay_requests import create_vee_replay_request


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
GENERATED_DIR = DOCS_DIR / "generated"
SCREEN_DIR = GENERATED_DIR / "screens"
MANIFEST_PATH = SCREEN_DIR / "manifest.json"
TESTS_DIR = ROOT / "tests"
FUNCTIONAL_DIR = TESTS_DIR / "functional"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(FUNCTIONAL_DIR) not in sys.path:
    sys.path.insert(0, str(FUNCTIONAL_DIR))

from postgresql_support import (  # noqa: E402
    build_schema_name,
    build_schema_url,
    create_schema,
    drop_schema,
    resolve_test_database_url,
)
from test_vee_exception_web import _create_open_vee_exception  # noqa: E402
from test_vee_replay_web import (  # noqa: E402
    _attach_vee_exception,
    _ingest_initial_measurement,
    _prepare_replay_environment,
)
from test_visibility_web import (  # noqa: E402
    _prepare_billing_export_request_rows,
    _prepare_estimation_audit_rows,
    _prepare_failed_billing_export_request_rows,
    _prepare_manual_edit_audit_rows,
)


VIEWPORT = {"width": 1440, "height": 1400}


@dataclass(slots=True)
class CaptureRecord:
    filename: str
    title: str
    route: str
    scenario: str
    note: str


@dataclass(slots=True)
class CaptureTarget:
    filename: str
    title: str
    route: str
    note: str
    wait_for: str | None = None
    locator: str | None = None
    full_page: bool = False


@dataclass(slots=True)
class FunctionalEnv:
    session: object
    base_url: str
    browser: Browser
    admin_user: UserAccount

    def open_page(self, *, lang: str = "ko", login: bool = True) -> tuple[BrowserContext, Page]:
        context = self.browser.new_context(
            base_url=self.base_url,
            locale="ko-KR",
            viewport=VIEWPORT,
            color_scheme="light",
        )
        page = context.new_page()
        if login:
            page.goto(f"/login?lang={lang}", wait_until="networkidle")
            page.get_by_label("로그인 ID").fill(self.admin_user.login_id)
            page.get_by_label("비밀번호").fill("functional-password")
            page.get_by_role("button", name="로그인").click()
            page.wait_for_url(re.compile(r".*/(?:\?lang=ko)?$"))
        return context, page


def _resolve_chrome_executable() -> str | None:
    configured = os.getenv("PLAYWRIGHT_CHROME_PATH")
    if configured:
        return configured

    for candidate in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        executable = shutil.which(candidate)
        if executable:
            return executable

    return None


@contextmanager
def functional_environment(prefix: str) -> Iterator[FunctionalEnv]:
    test_database_url = resolve_test_database_url()
    schema_name = build_schema_name(prefix=prefix)
    schema_url = build_schema_url(test_database_url, schema_name)
    create_schema(test_database_url, schema_name)

    previous_env = {key: os.environ.get(key) for key in ("TEST_DATABASE_URL", "DATABASE_URL", "SECRET_KEY")}
    os.environ["TEST_DATABASE_URL"] = test_database_url
    os.environ["DATABASE_URL"] = schema_url
    os.environ["SECRET_KEY"] = "functional-secret"

    app = create_app()
    app.config.update(TESTING=True)
    upgrade_db(schema_url)

    session = get_session()
    server = None
    thread = None
    browser = None
    admin_user = None

    try:
        admin_user = create_user_account(
            session,
            login_id="functional-admin",
            display_name="Functional Admin",
            role_code="admin",
            password="functional-password",
        )
        session.commit()

        chrome_executable = _resolve_chrome_executable()
        if chrome_executable is None:
            raise SystemExit("System Chrome executable is not available for screenshot capture.")

        server = make_server("127.0.0.1", 0, app)
        port = server.socket.getsockname()[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    executable_path=chrome_executable,
                    headless=True,
                    args=["--no-sandbox"],
                )
            except PlaywrightError as exc:
                raise SystemExit(f"Playwright browser launch is not available in this environment: {exc}") from exc

            yield FunctionalEnv(
                session=session,
                base_url=f"http://127.0.0.1:{port}",
                browser=browser,
                admin_user=admin_user,
            )
    finally:
        if browser is not None:
            with suppress(PlaywrightError):
                browser.close()
        if server is not None:
            server.shutdown()
        if thread is not None:
            thread.join(timeout=5)
        session.remove()
        drop_schema(test_database_url, schema_name)
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _capture_target(page: Page, target: CaptureTarget) -> CaptureRecord:
    page.goto(target.route, wait_until="networkidle")
    if target.wait_for:
        page.wait_for_selector(target.wait_for)
    page.wait_for_timeout(250)

    output_path = SCREEN_DIR / target.filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if target.locator:
        locator = page.locator(target.locator).first
        locator.scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        locator.screenshot(path=str(output_path))
    else:
        page.screenshot(path=str(output_path), full_page=target.full_page)

    return CaptureRecord(
        filename=target.filename,
        title=target.title,
        route=target.route,
        scenario="",
        note=target.note,
    )


def _assign_master_actor_visibility(session, actor: UserAccount) -> None:
    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    if hes_system is not None:
        hes_system.created_by_user_account_id = actor.id
        hes_system.updated_by_user_account_id = actor.id

    service_point = session.scalar(select(ServicePoint).where(ServicePoint.external_id == "SP-1001").limit(1))
    if service_point is None:
        raise RuntimeError("Seeded service point SP-1001 is missing.")

    for row in session.scalars(select(ServicePoint)).all():
        row.created_by_user_account_id = actor.id
        row.updated_by_user_account_id = actor.id
    for row in session.scalars(select(Device)).all():
        row.created_by_user_account_id = actor.id
        row.updated_by_user_account_id = actor.id
    for row in session.scalars(select(MeasuringComponent)).all():
        row.created_by_user_account_id = actor.id
        row.updated_by_user_account_id = actor.id
    for row in session.scalars(select(ServicePointBillingContext)).all():
        row.created_by_user_account_id = actor.id
        row.updated_by_user_account_id = actor.id
    for row in session.scalars(select(InstallationHistory)).all():
        row.created_by_user_account_id = actor.id
        row.updated_by_user_account_id = actor.id

    existing_tariff = session.scalar(select(ServicePointTariffAssignment).limit(1))
    if existing_tariff is None:
        create_tariff_assignment(
            session,
            service_point_id=service_point.id,
            tariff_plan_code="KR-BASIC",
            tariff_version_code="v1",
            effective_from="2026-04-01T00:00:00+09:00",
            effective_to=None,
            source_system="manual",
            source_reference="capture:tariff-assignment",
            created_by_user_account_id=actor.id,
        )
    else:
        existing_tariff.created_by_user_account_id = actor.id
        existing_tariff.updated_by_user_account_id = actor.id

    session.commit()


def _prepare_dashboard_attention_state(session, actor: UserAccount) -> None:
    vee_exception = _create_open_vee_exception(session)
    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert hes_system is not None
    request = VeeReplayRequest(
        request_scope="hes_system",
        status="processing",
        requested_by=actor.login_id,
        requested_by_user_account_id=actor.id,
        hes_system_id=hes_system.id,
        target_initial_count=4,
        processed_count=2,
        failed_count=1,
        details={"progress_percent": 50},
    )
    session.add(request)
    session.flush()
    event = record_operational_event(
        session,
        "vee_exception_opened",
        hes_system=hes_system,
        details={
            "status": "open",
            "result_code": vee_exception.exception_code,
            "acted_by": actor.login_id,
            "acted_by_user_account_id": actor.id,
        },
        entity_type="vee_exception",
        entity_id=vee_exception.id,
        exception_code=vee_exception.exception_code,
        initial_measurement_id=vee_exception.initial_measurement_id,
    )
    session.add(
        VeeReplayRequestItem(
            vee_replay_request_id=request.id,
            initial_measurement_id=vee_exception.initial_measurement_id,
            representative_vee_exception_id=vee_exception.id,
            status="failed",
            result_code="processing_error",
            details={
                "event_id": event.id,
                "error_summary": "capture replay failure",
            },
        )
    )
    session.commit()


def _prepare_lineage_state(session) -> None:
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()


def _prepare_replay_state(session, actor: UserAccount) -> int:
    hes_system_id = _prepare_replay_environment(session)
    initial_one = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="capture-replay-a",
        measured_at="2026-05-15T00:00:00+09:00",
    )
    initial_two = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="capture-replay-b",
        measured_at="2026-05-16T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial_one)
    _attach_vee_exception(session, initial_two)

    created = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by=actor.login_id,
        requested_by_user_account_id=actor.id,
        hes_system_id=hes_system_id,
    )
    request = created.request
    items = session.scalars(
        select(VeeReplayRequestItem)
        .where(VeeReplayRequestItem.vee_replay_request_id == request.id)
        .order_by(VeeReplayRequestItem.id.asc())
    ).all()
    request.status = "processing"
    request.started_at = datetime.now(timezone.utc)
    request.processed_count = 1
    request.succeeded_count = 0
    request.failed_count = 1
    request.last_error = "capture replay failure"
    request.details = {
        **dict(request.details or {}),
        "progress_percent": 50.0,
        "remaining_count": 1,
        "current_item_id": items[1].id,
        "last_processed_item_id": items[0].id,
    }
    items[0].status = "failed"
    items[0].result_code = "processing_error"
    items[0].details = {
        **dict(items[0].details or {}),
        "error_summary": "capture replay failure",
    }
    items[1].status = "processing"
    pipeline_run = PipelineRun(
        pipeline_name="vee_replay",
        trigger_type="async_replay",
        status="processing",
        vee_replay_request_id=request.id,
        started_at=datetime.now(timezone.utc),
        details={"request_id": request.id},
    )
    session.add(pipeline_run)
    session.commit()
    return request.id


def _prepare_operational_event_state(session, actor: UserAccount) -> int:
    seed_demo_environment(session)
    session.commit()
    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    adapter_instance = session.scalar(
        select(AdapterInstance).where(AdapterInstance.instance_code == "demo_hes_poll_primary").limit(1)
    )
    assert hes_system is not None
    assert adapter_instance is not None
    event = record_operational_event(
        session,
        "adapter_enabled",
        hes_system=hes_system,
        adapter_instance=adapter_instance,
        details={
            "acted_by": actor.login_id,
            "acted_by_user_account_id": actor.id,
            "previous_admin_state": "paused",
            "target_admin_state": "enabled",
        },
        instance_code=adapter_instance.instance_code,
    )
    session.commit()
    return event.id


def _run_login_capture(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_login") as env:
        context, page = env.open_page(login=False)
        try:
            record = _capture_target(
                page,
                CaptureTarget(
                    filename="01-login.png",
                    title="로그인 화면",
                    route="/login?lang=ko",
                    note="운영자 진입 화면",
                    wait_for="form",
                ),
            )
            record.scenario = "login"
            records.append(record)
        finally:
            context.close()


def _run_base_visibility_captures(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_base") as env:
        seed_demo_environment(env.session)
        env.session.commit()
        _assign_master_actor_visibility(env.session, env.admin_user)

        hes_system = env.session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
        adapter_instance = env.session.scalar(
            select(AdapterInstance).where(AdapterInstance.instance_code == "demo_hes_poll_primary").limit(1)
        )
        assert hes_system is not None
        assert adapter_instance is not None

        context, page = env.open_page()
        try:
            targets = [
                CaptureTarget(
                    filename="02-dashboard-normal.png",
                    title="대시보드 기본 상태",
                    route="/?lang=ko",
                    note="일일 운영 시작 화면",
                    full_page=True,
                    wait_for="text=최근 원시 검침",
                ),
                CaptureTarget(
                    filename="04-hes-detail.png",
                    title="HES 상세",
                    route=f"/hes-systems/{hes_system.id}?lang=ko",
                    note="HES 중심 운영 화면",
                    wait_for="text=연결된 어댑터",
                ),
                CaptureTarget(
                    filename="05-adapter-detail.png",
                    title="어댑터 상세",
                    route=f"/adapters/{adapter_instance.id}?lang=ko",
                    note="런타임 상태와 운영자 조치",
                    wait_for="text=어댑터 상세",
                ),
                CaptureTarget(
                    filename="06-master-data.png",
                    title="마스터 데이터",
                    route="/master-data?lang=ko",
                    note="최소 마스터 데이터와 actor visibility",
                    wait_for="#service-points",
                    locator="#service-points",
                ),
                CaptureTarget(
                    filename="07-raw-reads.png",
                    title="원시 검침 가시성",
                    route="/raw-reads?lang=ko&meter_id=MTR-1001",
                    note="원본 적재 가시성",
                    wait_for="text=원시 검침",
                ),
            ]
            for target in targets:
                record = _capture_target(page, target)
                record.scenario = "base_visibility"
                records.append(record)
        finally:
            context.close()


def _run_dashboard_attention_capture(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_dashboard_attention") as env:
        _prepare_dashboard_attention_state(env.session, env.admin_user)
        context, page = env.open_page()
        try:
            record = _capture_target(
                page,
                CaptureTarget(
                    filename="03-dashboard-attention.png",
                    title="대시보드 주의 필요 상태",
                    route="/?lang=ko",
                    note="알림, recent event, replay 신호를 함께 보는 상태",
                    wait_for="text=최근 VEE 재평가 요청",
                    full_page=True,
                ),
            )
            record.scenario = "dashboard_attention"
            records.append(record)
        finally:
            context.close()


def _run_lineage_captures(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_lineage") as env:
        _prepare_lineage_state(env.session)
        context, page = env.open_page()
        try:
            targets = [
                CaptureTarget(
                    filename="08-canonical-measurements.png",
                    title="표준 계측",
                    route="/canonical-measurements?lang=ko&batch_id=demo-read-batch&meter_id=MTR-1001",
                    note="정규화 이후 진행 상태",
                    wait_for="text=표준 계측",
                ),
                CaptureTarget(
                    filename="09-final-measurements.png",
                    title="최종 계측",
                    route="/final-measurements?lang=ko&batch_id=demo-read-batch&meter_id=MTR-1001",
                    note="권위 있는 최종 상태",
                    wait_for="text=최종 계측",
                ),
            ]
            for target in targets:
                record = _capture_target(page, target)
                record.scenario = "lineage"
                records.append(record)
        finally:
            context.close()


def _run_vee_captures(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_vee") as env:
        vee_exception = _create_open_vee_exception(env.session)
        context, page = env.open_page()
        try:
            targets = [
                CaptureTarget(
                    filename="10-vee-exception-queue.png",
                    title="VEE 예외 큐",
                    route="/vee-exceptions?lang=ko&exception_status=active&meter_id=MTR-1001",
                    note="차단/비차단 triage 시작점",
                    wait_for="text=VEE 예외",
                ),
                CaptureTarget(
                    filename="11-vee-exception-detail.png",
                    title="VEE 예외 상세",
                    route=f"/vee-exceptions/{vee_exception.id}?lang=ko",
                    note="차단 사유와 다음 조치",
                    wait_for="text=VEE 예외 상세",
                ),
            ]
            for target in targets:
                record = _capture_target(page, target)
                record.scenario = "vee"
                records.append(record)
        finally:
            context.close()


def _run_estimation_capture(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_estimation") as env:
        estimation_audit_id = _prepare_estimation_audit_rows(env.session)
        context, page = env.open_page()
        try:
            record = _capture_target(
                page,
                CaptureTarget(
                    filename="12-estimation-audit-detail.png",
                    title="추정 감사 상세",
                    route=f"/estimation-audits/{estimation_audit_id}?lang=ko",
                    note="추정 보정 accountability",
                    wait_for="text=추정 감사 상세",
                    full_page=True,
                ),
            )
            record.scenario = "estimation"
            records.append(record)
        finally:
            context.close()


def _run_manual_edit_capture(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_manual_edit") as env:
        manual_edit_audit_id = _prepare_manual_edit_audit_rows(env.session)
        context, page = env.open_page()
        try:
            record = _capture_target(
                page,
                CaptureTarget(
                    filename="13-manual-edit-audit-detail.png",
                    title="수동 보정 감사 상세",
                    route=f"/manual-edit-audits/{manual_edit_audit_id}?lang=ko",
                    note="수동 보정 accountability",
                    wait_for="text=수동 보정 감사 상세",
                    full_page=True,
                ),
            )
            record.scenario = "manual_edit"
            records.append(record)
        finally:
            context.close()


def _run_replay_captures(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_replay") as env:
        request_id = _prepare_replay_state(env.session, env.admin_user)
        context, page = env.open_page()
        try:
            targets = [
                CaptureTarget(
                    filename="14-replay-request-list.png",
                    title="VEE 재평가 요청 목록",
                    route="/vee-replay-requests?lang=ko&status=processing",
                    note="queue-style request monitoring",
                    wait_for="text=VEE 재평가 요청",
                ),
                CaptureTarget(
                    filename="15-replay-request-detail.png",
                    title="VEE 재평가 요청 상세",
                    route=f"/vee-replay-requests/{request_id}?lang=ko",
                    note="scope, progress, current item, failed items",
                    wait_for="text=VEE 재평가 요청 상세",
                    full_page=True,
                ),
            ]
            for target in targets:
                record = _capture_target(page, target)
                record.scenario = "replay"
                records.append(record)
        finally:
            context.close()


def _run_billing_export_captures(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_export") as env:
        stale_request_id = _prepare_billing_export_request_rows(env.session, make_stale=True)
        stale_request = env.session.get(BillingExportRequest, stale_request_id)
        assert stale_request is not None
        assert stale_request.service_point is not None
        stale_details = dict(stale_request.details or {})
        stale_claimed_by = stale_request.claimed_by
        stale_last_heartbeat_at = stale_request.last_heartbeat_at

        stale_request.status = "completed"
        stale_request.completed_at = datetime.now(timezone.utc)
        env.session.commit()

        failed_request_id = _prepare_failed_billing_export_request_rows(env.session)

        stale_request = env.session.get(BillingExportRequest, stale_request_id)
        assert stale_request is not None
        stale_request.status = "processing"
        stale_request.completed_at = None
        stale_request.claimed_by = stale_claimed_by
        stale_request.last_heartbeat_at = stale_last_heartbeat_at
        stale_request.details = stale_details
        env.session.commit()

        context, page = env.open_page()
        try:
            targets = [
                CaptureTarget(
                    filename="16-billing-export-request-list.png",
                    title="청구 내보내기 요청 목록",
                    route=(
                        "/billing-export-requests?lang=ko"
                        f"&status=processing&service_point={stale_request.service_point.external_id}"
                        "&target_system_code=generic_json"
                        f"&requested_by={stale_request.requested_by}"
                    ),
                    note="status hint, progress, actor, spotlight",
                    wait_for="text=청구 내보내기 요청",
                ),
                CaptureTarget(
                    filename="17-billing-export-request-detail.png",
                    title="청구 내보내기 요청 상세",
                    route=f"/billing-export-requests/{failed_request_id}?lang=ko",
                    note="request summary, failed items, action context",
                    wait_for="text=청구 내보내기 요청 상세",
                    full_page=True,
                ),
            ]
            for target in targets:
                record = _capture_target(page, target)
                record.scenario = "billing_export"
                records.append(record)
        finally:
            context.close()


def _run_operational_event_capture(records: list[CaptureRecord]) -> None:
    with functional_environment("capture_operational_event") as env:
        event_id = _prepare_operational_event_state(env.session, env.admin_user)
        context, page = env.open_page()
        try:
            record = _capture_target(
                page,
                CaptureTarget(
                    filename="18-operational-event-detail.png",
                    title="운영 이벤트 상세",
                    route=f"/operational-events/{event_id}?lang=ko",
                    note="action snapshot and raw details",
                    wait_for="text=조치 스냅샷",
                    full_page=True,
                ),
            )
            record.scenario = "operational_event"
            records.append(record)
        finally:
            context.close()


SCENARIOS: dict[str, Callable[[list[CaptureRecord]], None]] = {
    "login": _run_login_capture,
    "base_visibility": _run_base_visibility_captures,
    "dashboard_attention": _run_dashboard_attention_capture,
    "lineage": _run_lineage_captures,
    "vee": _run_vee_captures,
    "estimation": _run_estimation_capture,
    "manual_edit": _run_manual_edit_capture,
    "replay": _run_replay_captures,
    "billing_export": _run_billing_export_captures,
    "operational_event": _run_operational_event_capture,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture operator manual screenshots.")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIOS),
        help="Capture only the named scenario. Repeat to capture multiple scenarios.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    records: list[CaptureRecord] = []
    scenario_names = args.scenario or list(SCENARIOS)
    for scenario_name in scenario_names:
        SCENARIOS[scenario_name](records)

    manifest = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "viewport": VIEWPORT,
        "captures": [asdict(record) for record in records],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {len(records)} captures to {SCREEN_DIR}")
    print(f"Wrote manifest {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
