from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    AdapterInstance,
    AuthSessionAudit,
    BillCharge,
    BillDeterminant,
    Device,
    InitialMeasurement,
    MeasuringComponent,
    OperationalEvent,
    PipelineRun,
    ServicePoint,
    UserAccount,
    UserActionAudit,
    VeeException,
    VeeReplayRequest,
)
from app.services.auth import create_user_account
from app.services.billing_export_requests import create_billing_export_request
from app.services.seeds import seed_demo_environment
from app.services.seeds import seed_master_data
from app.services.vee import evaluate_or_get_vee_baseline
from app.services.vee_replay_requests import create_vee_replay_request


def _latest_user_action(session, *, action_type: str, resource_type: str) -> UserActionAudit | None:
    return session.scalar(
        select(UserActionAudit)
        .where(
            UserActionAudit.action_type == action_type,
            UserActionAudit.resource_type == resource_type,
        )
        .order_by(UserActionAudit.id.desc())
        .limit(1)
    )


def _get_open_alert(session) -> OperationalEvent | None:
    return session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.is_alert.is_(True), OperationalEvent.alert_status == "open")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )


def _create_open_vee_exception(session) -> VeeException:
    seed_demo_environment(session)
    session.commit()

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

    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    assert vee_exception is not None
    return vee_exception


def _prepare_replay_request(session, actor: UserAccount) -> VeeReplayRequest:
    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.exception_status == "open")
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    if vee_exception is None:
        vee_exception = _create_open_vee_exception(session)
    hes_system = vee_exception.initial_measurement.canonical_measurement.hes_read_raw.hes_system
    assert hes_system is not None

    result = create_vee_replay_request(
        session,
        request_scope="hes_system",
        hes_system_id=hes_system.id,
        requested_by=actor.login_id,
        requested_by_user_account_id=actor.id,
    )
    session.commit()
    return result.request


def _prepare_billing_export_request(session, actor: UserAccount) -> int:
    existing_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.is_current.is_(True))
        .order_by(BillCharge.billing_period_start_at.asc(), BillCharge.id.asc())
        .limit(1)
    )
    if existing_charge is None:
        seed_master_data(session)
        session.commit()

        service_point_id = session.scalar(select(ServicePoint.id).limit(1))
        device_id = session.scalar(select(Device.id).limit(1))
        measuring_component_id = session.scalar(select(MeasuringComponent.id).limit(1))
        assert service_point_id is not None
        assert device_id is not None
        assert measuring_component_id is not None

        now = datetime.now(timezone.utc)
        determinant_run = PipelineRun(
            pipeline_name="bill_determinant",
            trigger_type="manual",
            status="completed",
            started_at=now,
            completed_at=now,
            result_code="bill_determinant_completed",
            details={"trigger_source": "auth_web_test"},
        )
        charge_run = PipelineRun(
            pipeline_name="bill_charge",
            trigger_type="manual",
            status="completed",
            started_at=now,
            completed_at=now,
            result_code="bill_charge_completed",
            details={"trigger_source": "auth_web_test"},
        )
        session.add_all([determinant_run, charge_run])
        session.flush()

        determinant = BillDeterminant(
            pipeline_run_id=determinant_run.id,
            service_point_id=service_point_id,
            measuring_component_id=measuring_component_id,
            device_id=device_id,
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
            details={"trigger_source": "auth_web_test"},
        )
        session.add(determinant)
        session.flush()

        charge_row = BillCharge(
            pipeline_run_id=charge_run.id,
            service_point_id=service_point_id,
            measuring_component_id=measuring_component_id,
            device_id=device_id,
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
            details={"trigger_source": "auth_web_test"},
        )
        session.add(charge_row)
        session.commit()
    else:
        charge_row = existing_charge

    result = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=charge_row.service_point_id,
        billing_period_from=charge_row.billing_period_start_at,
        billing_period_to=charge_row.billing_period_end_at,
        requested_by=actor.login_id,
        requested_by_user_account_id=actor.id,
    )
    session.commit()
    return result.request.id


def test_web_routes_require_login(anonymous_client):
    response = anonymous_client.get("/", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_api_routes_require_login(anonymous_client):
    response = anonymous_client.get("/api/v1/raw-reads")

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["error_code"] == "authentication_required"


def test_login_succeeds_and_records_auth_audit(session, anonymous_client):
    create_user_account(
        session,
        login_id="alice",
        display_name="Alice Operator",
        role_code="operator",
        password="secret-password",
    )
    session.commit()

    response = anonymous_client.post(
        "/login",
        data={"login_id": "alice", "password": "secret-password"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/") or "/?lang=" in response.headers["Location"]

    auth_events = session.scalars(
        select(AuthSessionAudit).order_by(AuthSessionAudit.id.asc())
    ).all()
    assert [row.auth_event_type for row in auth_events] == ["login_succeeded"]
    assert auth_events[0].login_id_attempted == "alice"

    user_actions = session.scalars(
        select(UserActionAudit).order_by(UserActionAudit.id.asc())
    ).all()
    assert [row.action_type for row in user_actions] == ["login"]


def test_login_failure_records_failed_auth_audit(session, anonymous_client):
    response = anonymous_client.post(
        "/login",
        data={"login_id": "missing-user", "password": "bad-password"},
    )

    assert response.status_code == 401
    auth_events = session.scalars(
        select(AuthSessionAudit).order_by(AuthSessionAudit.id.asc())
    ).all()
    assert [row.auth_event_type for row in auth_events] == ["login_failed"]
    assert auth_events[0].result_code == "invalid_credentials"


def test_logout_clears_session_and_records_audit(client, session):
    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    follow_up = client.get("/", follow_redirects=False)
    assert follow_up.status_code == 302
    assert "/login" in follow_up.headers["Location"]

    auth_events = session.scalars(
        select(AuthSessionAudit).order_by(AuthSessionAudit.id.asc())
    ).all()
    assert [row.auth_event_type for row in auth_events] == ["login_succeeded", "logout"]

    user_actions = session.scalars(
        select(UserActionAudit).order_by(UserActionAudit.id.asc())
    ).all()
    assert "logout" in [row.action_type for row in user_actions]


def test_authenticated_read_creates_user_action_audit(client, session):
    response = client.get("/")

    assert response.status_code == 200

    user_actions = session.scalars(
        select(UserActionAudit)
        .where(UserActionAudit.action_type == "read")
        .order_by(UserActionAudit.id.asc())
    ).all()
    assert user_actions
    assert user_actions[-1].resource_type == "dashboard"
    assert user_actions[-1].outcome_code == "success"


def test_authenticated_api_read_creates_user_action_audit(client, session):
    response = client.get("/api/v1/raw-reads")

    assert response.status_code == 200

    user_actions = session.scalars(
        select(UserActionAudit)
        .where(
            UserActionAudit.action_type == "read",
            UserActionAudit.resource_type == "list_raw_reads",
        )
        .order_by(UserActionAudit.id.asc())
    ).all()
    assert user_actions
    assert user_actions[-1].request_method == "GET"
    assert user_actions[-1].outcome_code == "success"


def test_critical_detail_reads_create_user_action_audit_evidence(client, session):
    seed_demo_environment(session)
    session.commit()

    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    alert = _get_open_alert(session)
    vee_exception = _create_open_vee_exception(session)
    assert actor is not None
    assert alert is not None

    replay_request = _prepare_replay_request(session, actor)
    export_request_id = _prepare_billing_export_request(session, actor)

    response = client.get(f"/operational-events/{alert.id}")
    assert response.status_code == 200
    response = client.get(f"/vee-exceptions/{vee_exception.id}")
    assert response.status_code == 200
    response = client.get(f"/vee-replay-requests/{replay_request.id}")
    assert response.status_code == 200
    response = client.get(f"/billing-export-requests/{export_request_id}")
    assert response.status_code == 200

    event_read = _latest_user_action(
        session,
        action_type="read",
        resource_type="operational_event_detail",
    )
    assert event_read is not None
    assert event_read.resource_id == str(alert.id)
    assert event_read.request_path == f"/operational-events/{alert.id}"
    assert event_read.outcome_code == "success"
    assert event_read.details["endpoint"] == "web.operational_event_detail"

    vee_read = _latest_user_action(
        session,
        action_type="read",
        resource_type="vee_exception_detail",
    )
    assert vee_read is not None
    assert vee_read.resource_id == str(vee_exception.id)
    assert vee_read.request_path == f"/vee-exceptions/{vee_exception.id}"
    assert vee_read.outcome_code == "success"
    assert vee_read.details["endpoint"] == "web.vee_exception_detail"

    replay_read = _latest_user_action(
        session,
        action_type="read",
        resource_type="vee_replay_request_detail",
    )
    assert replay_read is not None
    assert replay_read.resource_id == str(replay_request.id)
    assert replay_read.request_path == f"/vee-replay-requests/{replay_request.id}"
    assert replay_read.outcome_code == "success"
    assert replay_read.details["endpoint"] == "web.vee_replay_request_detail"

    export_read = _latest_user_action(
        session,
        action_type="read",
        resource_type="billing_export_request_detail",
    )
    assert export_read is not None
    assert export_read.resource_id == str(export_request_id)
    assert export_read.request_path == f"/billing-export-requests/{export_request_id}"
    assert export_read.outcome_code == "success"
    assert export_read.details["endpoint"] == "web.billing_export_request_detail"


def test_admin_execute_action_creates_user_action_audit(client, session):
    seed_demo_environment(session)
    session.commit()

    instance = session.scalar(select(AdapterInstance).limit(1))
    assert instance is not None

    response = client.post(
        f"/adapters/{instance.id}/pause",
        data={"next": f"/adapters/{instance.id}"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    user_actions = session.scalars(
        select(UserActionAudit)
        .where(
            UserActionAudit.action_type == "execute",
            UserActionAudit.resource_type == "pause_adapter_view",
        )
        .order_by(UserActionAudit.id.asc())
    ).all()
    assert user_actions
    assert user_actions[-1].resource_id == str(instance.id)
    assert user_actions[-1].status_code == 302
    assert user_actions[-1].outcome_code == "redirect"


def test_operational_alert_execute_flows_create_user_action_audit_evidence(client, session):
    seed_demo_environment(session)
    session.commit()

    alert = _get_open_alert(session)
    assert alert is not None

    response = client.post(
        f"/operational-events/{alert.id}/acknowledge",
        data={"next": f"/operational-events/{alert.id}"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    response = client.post(
        f"/operational-events/{alert.id}/close",
        data={
            "next": f"/operational-events/{alert.id}",
            "operator_memo": "closed-from-auth-web-test",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    acknowledge_audit = _latest_user_action(
        session,
        action_type="execute",
        resource_type="acknowledge_operational_alert_view",
    )
    assert acknowledge_audit is not None
    assert acknowledge_audit.resource_id == str(alert.id)
    assert acknowledge_audit.request_path == f"/operational-events/{alert.id}/acknowledge"
    assert acknowledge_audit.status_code == 302
    assert acknowledge_audit.outcome_code == "redirect"
    assert acknowledge_audit.details["endpoint"] == "web.acknowledge_operational_alert_view"

    close_audit = _latest_user_action(
        session,
        action_type="execute",
        resource_type="close_operational_alert_view",
    )
    assert close_audit is not None
    assert close_audit.resource_id == str(alert.id)
    assert close_audit.request_path == f"/operational-events/{alert.id}/close"
    assert close_audit.status_code == 302
    assert close_audit.outcome_code == "redirect"
    assert close_audit.details["endpoint"] == "web.close_operational_alert_view"


def test_vee_replay_execute_flows_create_user_action_audit_evidence(client, session):
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    vee_exception = _create_open_vee_exception(session)
    hes_system = vee_exception.initial_measurement.canonical_measurement.hes_read_raw.hes_system
    assert actor is not None
    assert hes_system is not None

    response = client.post(
        "/vee-replay-requests",
        data={
            "request_scope": "hes_system",
            "requested_by": actor.login_id,
            "operator_memo": "auth-web-replay-create",
            "hes_system_id": str(hes_system.id),
            "ingest_batch_id": "",
            "measured_at_from": "",
            "measured_at_to": "",
            "window_timezone_name": "Asia/Seoul",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    replay_request = session.scalar(
        select(VeeReplayRequest).order_by(VeeReplayRequest.id.desc()).limit(1)
    )
    assert replay_request is not None

    response = client.post(
        f"/vee-replay-requests/{replay_request.id}/cancel",
        data={
            "next": f"/vee-replay-requests/{replay_request.id}",
            "operator_memo": "auth-web-replay-cancel",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    create_audit = _latest_user_action(
        session,
        action_type="execute",
        resource_type="create_vee_replay_request_view",
    )
    assert create_audit is not None
    assert create_audit.resource_id is None
    assert create_audit.request_path == "/vee-replay-requests"
    assert create_audit.status_code == 302
    assert create_audit.outcome_code == "redirect"
    assert create_audit.details["endpoint"] == "web.create_vee_replay_request_view"

    cancel_audit = _latest_user_action(
        session,
        action_type="execute",
        resource_type="cancel_vee_replay_request_view",
    )
    assert cancel_audit is not None
    assert cancel_audit.resource_id == str(replay_request.id)
    assert cancel_audit.request_path == f"/vee-replay-requests/{replay_request.id}/cancel"
    assert cancel_audit.status_code == 302
    assert cancel_audit.outcome_code == "redirect"
    assert cancel_audit.details["endpoint"] == "web.cancel_vee_replay_request_view"


def test_billing_export_execute_flows_create_user_action_audit_evidence(client, session):
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None

    request_id = _prepare_billing_export_request(session, actor)

    response = client.get(f"/billing-export-requests/{request_id}")
    assert response.status_code == 200

    response = client.post(
        f"/billing-export-requests/{request_id}/cancel",
        data={
            "next": f"/billing-export-requests/{request_id}",
            "operator_memo": "auth-web-export-cancel",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    detail_read = _latest_user_action(
        session,
        action_type="read",
        resource_type="billing_export_request_detail",
    )
    assert detail_read is not None
    assert detail_read.resource_id == str(request_id)
    assert detail_read.request_path == f"/billing-export-requests/{request_id}"
    assert detail_read.outcome_code == "success"
    assert detail_read.details["endpoint"] == "web.billing_export_request_detail"

    cancel_audit = _latest_user_action(
        session,
        action_type="execute",
        resource_type="cancel_billing_export_request_view",
    )
    assert cancel_audit is not None
    assert cancel_audit.resource_id == str(request_id)
    assert cancel_audit.request_path == f"/billing-export-requests/{request_id}/cancel"
    assert cancel_audit.status_code == 302
    assert cancel_audit.outcome_code == "redirect"
    assert cancel_audit.details["endpoint"] == "web.cancel_billing_export_request_view"


def test_operator_cannot_call_admin_web_action(operator_client):
    response = operator_client.post("/hes-systems", data={})

    assert response.status_code == 403


def test_forbidden_admin_web_action_creates_user_action_audit(operator_client, session):
    response = operator_client.post("/hes-systems", data={})

    assert response.status_code == 403

    user_actions = session.scalars(
        select(UserActionAudit)
        .where(
            UserActionAudit.action_type == "execute",
            UserActionAudit.resource_type == "create_hes_system_view",
        )
        .order_by(UserActionAudit.id.asc())
    ).all()
    assert user_actions
    assert user_actions[-1].status_code == 403
    assert user_actions[-1].outcome_code == "client_error"


def test_operator_cannot_call_admin_api_action(operator_client):
    response = operator_client.post("/api/v1/billing-export-requests/1/cancel", json={})

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["error_code"] == "forbidden"
