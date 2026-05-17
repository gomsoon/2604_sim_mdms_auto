from __future__ import annotations

from sqlalchemy import select

from app.models import AdapterInstance, AuthSessionAudit, UserActionAudit
from app.services.auth import create_user_account
from app.services.seeds import seed_demo_environment


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
