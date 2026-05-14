from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from flask import (
    Flask,
    Response,
    current_app,
    g,
    jsonify,
    redirect,
    request,
    session as browser_session,
    url_for,
)
from sqlalchemy import insert, select, update
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_engine, get_session
from app.i18n import get_locale, translate
from app.models import AuthSessionAudit, UserAccount, UserActionAudit


AUTH_USER_ID_SESSION_KEY = "auth_user_id"
AUTH_ROLE_CODE_SESSION_KEY = "auth_role_code"
AUTH_SESSION_IDENTIFIER_SESSION_KEY = "auth_session_identifier"
AUTH_SESSION_AUDIT_ID_SESSION_KEY = "auth_session_audit_id"

_WEB_EXEMPT_ENDPOINTS = {
    "web.login",
    "web.logout",
}
_API_EXEMPT_ENDPOINTS = {
    "api.health_check",
    "api.ingest_reads_endpoint",
    "api.ingest_events_endpoint",
    "api.receive_reads_endpoint",
    "api.receive_events_endpoint",
}
_GENERIC_AUDIT_EXEMPT_ENDPOINTS = _WEB_EXEMPT_ENDPOINTS | _API_EXEMPT_ENDPOINTS | {"static"}


@dataclass(slots=True)
class AuthenticationResult:
    user_account: UserAccount | None
    error_code: str | None = None


class AuthValidationError(Exception):
    def __init__(self, error_code: str, fallback_message: str):
        super().__init__(fallback_message)
        self.error_code = error_code
        self.fallback_message = fallback_message


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def create_user_account(
    session,
    *,
    login_id: str,
    password: str,
    display_name: str,
    role_code: str,
    is_active: bool = True,
    details: dict | None = None,
) -> UserAccount:
    normalized_login_id = login_id.strip()
    normalized_display_name = display_name.strip()
    normalized_role_code = role_code.strip()

    if normalized_role_code not in {"admin", "operator"}:
        raise AuthValidationError("invalid_role_code", "Unsupported role_code.")
    if not normalized_login_id:
        raise AuthValidationError("missing_login_id", "login_id is required.")
    if not password:
        raise AuthValidationError("missing_password", "password is required.")
    if not normalized_display_name:
        raise AuthValidationError("missing_display_name", "display_name is required.")

    existing = session.scalar(
        select(UserAccount).where(UserAccount.login_id == normalized_login_id)
    )
    if existing is not None:
        raise AuthValidationError("login_id_already_exists", "login_id already exists.")

    user_account = UserAccount(
        login_id=normalized_login_id,
        password_hash=hash_password(password),
        display_name=normalized_display_name,
        role_code=normalized_role_code,
        is_active=is_active,
        password_changed_at=datetime.now(timezone.utc),
        details=details or {},
    )
    session.add(user_account)
    session.flush()
    return user_account


def authenticate_user(session, *, login_id: str, password: str) -> AuthenticationResult:
    normalized_login_id = login_id.strip()
    user_account = session.scalar(
        select(UserAccount).where(UserAccount.login_id == normalized_login_id)
    )
    if user_account is None:
        return AuthenticationResult(None, "invalid_credentials")
    if not user_account.is_active:
        return AuthenticationResult(user_account, "inactive_account")
    if not verify_password(user_account.password_hash, password):
        return AuthenticationResult(None, "invalid_credentials")
    return AuthenticationResult(user_account)


def init_auth(app: Flask) -> None:
    @app.before_request
    def _load_authenticated_user():
        _load_current_user_from_session()

        endpoint = request.endpoint
        if endpoint is None or _is_auth_exempt_endpoint(endpoint):
            return None

        if request.blueprint not in {"web", "api"}:
            return None

        if g.current_user is None:
            if request.blueprint == "api":
                return _api_error_response("authentication_required", 401)

            return redirect(
                url_for(
                    "web.login",
                    next=_next_url_value(),
                    lang=get_locale(),
                )
            )

        return None

    @app.after_request
    def _audit_authenticated_request(response: Response):
        _record_generic_user_action(response)
        return response

    @app.context_processor
    def _auth_template_context():
        return {
            "current_user": getattr(g, "current_user", None),
            "current_user_is_admin": current_user_is_admin(),
        }


def current_user_is_admin() -> bool:
    current_user = get_current_user()
    return current_user is not None and current_user.role_code == "admin"


def get_current_user() -> UserAccount | None:
    return getattr(g, "current_user", None)


def get_current_auth_session_audit_id() -> int | None:
    return getattr(g, "current_auth_session_audit_id", None)


def require_role(role_code: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            current_user = get_current_user()
            if current_user is None:
                if request.blueprint == "api":
                    return _api_error_response("authentication_required", 401)
                return redirect(
                    url_for(
                        "web.login",
                        next=_next_url_value(),
                        lang=get_locale(),
                    )
                )

            if current_user.role_code != role_code:
                if request.blueprint == "api":
                    return _api_error_response("forbidden", 403)
                return _web_forbidden_response()

            return view_func(*args, **kwargs)

        return wrapped

    return decorator


admin_required = require_role("admin")


def login_user_account(user_account: UserAccount) -> int:
    session_identifier = uuid4().hex
    auth_session_audit_id = record_auth_session_event(
        user_account_id=user_account.id,
        login_id_attempted=user_account.login_id,
        auth_event_type="login_succeeded",
        session_identifier=session_identifier,
        auth_channel="web_session",
        ip_address=_request_ip_address(),
        user_agent=request.headers.get("User-Agent"),
        result_code="login_succeeded",
        details={"endpoint": request.endpoint},
    )

    scoped_session = get_session()
    scoped_session.execute(
        update(UserAccount)
        .where(UserAccount.id == user_account.id)
        .values(last_login_at=datetime.now(timezone.utc))
    )
    scoped_session.flush()

    browser_session.permanent = True
    browser_session[AUTH_USER_ID_SESSION_KEY] = user_account.id
    browser_session[AUTH_ROLE_CODE_SESSION_KEY] = user_account.role_code
    browser_session[AUTH_SESSION_IDENTIFIER_SESSION_KEY] = session_identifier
    browser_session[AUTH_SESSION_AUDIT_ID_SESSION_KEY] = auth_session_audit_id

    g.current_user = user_account
    g.current_auth_session_audit_id = auth_session_audit_id

    record_user_action_event(
        user_account_id=user_account.id,
        auth_session_audit_id=auth_session_audit_id,
        action_type="login",
        resource_type="auth_session",
        resource_id=session_identifier,
        request_method=request.method,
        request_path=request.path,
        status_code=302,
        outcome_code="success",
        ip_address=_request_ip_address(),
        user_agent=request.headers.get("User-Agent"),
        details={"role_code": user_account.role_code},
    )
    return auth_session_audit_id


def logout_current_user() -> None:
    current_user = get_current_user()
    if current_user is None:
        _clear_browser_auth_session()
        return

    session_identifier = browser_session.get(AUTH_SESSION_IDENTIFIER_SESSION_KEY)
    logout_audit_id = record_auth_session_event(
        user_account_id=current_user.id,
        login_id_attempted=current_user.login_id,
        auth_event_type="logout",
        session_identifier=session_identifier,
        auth_channel="web_session",
        ip_address=_request_ip_address(),
        user_agent=request.headers.get("User-Agent"),
        result_code="logout",
        details={"endpoint": request.endpoint},
    )
    record_user_action_event(
        user_account_id=current_user.id,
        auth_session_audit_id=logout_audit_id,
        action_type="logout",
        resource_type="auth_session",
        resource_id=session_identifier,
        request_method=request.method,
        request_path=request.path,
        status_code=302,
        outcome_code="success",
        ip_address=_request_ip_address(),
        user_agent=request.headers.get("User-Agent"),
        details={"role_code": current_user.role_code},
    )
    _clear_browser_auth_session()


def record_failed_login(login_id: str, error_code: str, *, user_account_id: int | None = None) -> int:
    return record_auth_session_event(
        user_account_id=user_account_id,
        login_id_attempted=login_id.strip() or None,
        auth_event_type="login_failed",
        session_identifier=None,
        auth_channel="web_session",
        ip_address=_request_ip_address(),
        user_agent=request.headers.get("User-Agent"),
        result_code=error_code,
        details={"endpoint": request.endpoint},
    )


def record_auth_session_event(
    *,
    user_account_id: int | None,
    login_id_attempted: str | None,
    auth_event_type: str,
    session_identifier: str | None,
    auth_channel: str,
    ip_address: str | None,
    user_agent: str | None,
    result_code: str | None,
    details: dict | None,
) -> int:
    values = {
        "user_account_id": user_account_id,
        "login_id_attempted": login_id_attempted,
        "auth_event_type": auth_event_type,
        "session_identifier": session_identifier,
        "auth_channel": auth_channel,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "result_code": result_code,
        "details": details or {},
        "occurred_at": datetime.now(timezone.utc),
    }
    with get_engine().begin() as connection:
        result = connection.execute(insert(AuthSessionAudit.__table__).values(**values))
        return int(result.inserted_primary_key[0])


def record_user_action_event(
    *,
    user_account_id: int,
    auth_session_audit_id: int | None,
    action_type: str,
    resource_type: str,
    resource_id: str | None,
    request_method: str | None,
    request_path: str | None,
    status_code: int | None,
    outcome_code: str,
    ip_address: str | None,
    user_agent: str | None,
    details: dict | None,
) -> int:
    values = {
        "user_account_id": user_account_id,
        "auth_session_audit_id": auth_session_audit_id,
        "action_type": action_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "request_method": request_method,
        "request_path": request_path,
        "status_code": status_code,
        "outcome_code": outcome_code,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "details": details or {},
        "occurred_at": datetime.now(timezone.utc),
    }
    with get_engine().begin() as connection:
        result = connection.execute(insert(UserActionAudit.__table__).values(**values))
        return int(result.inserted_primary_key[0])


def _load_current_user_from_session() -> None:
    g.current_user = None
    g.current_auth_session_audit_id = browser_session.get(AUTH_SESSION_AUDIT_ID_SESSION_KEY)

    user_account_id = browser_session.get(AUTH_USER_ID_SESSION_KEY)
    if user_account_id is None:
        return

    scoped_session = get_session()
    user_account = scoped_session.scalar(
        select(UserAccount).where(UserAccount.id == user_account_id)
    )
    if user_account is None or not user_account.is_active:
        _record_session_expired(
            user_account_id=user_account_id if user_account is not None else None,
            login_id_attempted=user_account.login_id if user_account is not None else None,
        )
        _clear_browser_auth_session()
        return

    g.current_user = user_account


def _record_session_expired(
    *,
    user_account_id: int | None,
    login_id_attempted: str | None,
) -> None:
    session_identifier = browser_session.get(AUTH_SESSION_IDENTIFIER_SESSION_KEY)
    if session_identifier is None and user_account_id is None and login_id_attempted is None:
        return

    try:
        record_auth_session_event(
            user_account_id=user_account_id,
            login_id_attempted=login_id_attempted,
            auth_event_type="session_expired",
            session_identifier=session_identifier,
            auth_channel="web_session",
            ip_address=_request_ip_address(),
            user_agent=request.headers.get("User-Agent"),
            result_code="session_expired",
            details={"endpoint": request.endpoint},
        )
    except Exception:
        current_app.logger.exception("Failed to record session_expired auth audit.")


def _clear_browser_auth_session() -> None:
    browser_session.pop(AUTH_USER_ID_SESSION_KEY, None)
    browser_session.pop(AUTH_ROLE_CODE_SESSION_KEY, None)
    browser_session.pop(AUTH_SESSION_IDENTIFIER_SESSION_KEY, None)
    browser_session.pop(AUTH_SESSION_AUDIT_ID_SESSION_KEY, None)
    g.current_user = None
    g.current_auth_session_audit_id = None


def _record_generic_user_action(response: Response) -> None:
    endpoint = request.endpoint
    if endpoint is None or endpoint in _GENERIC_AUDIT_EXEMPT_ENDPOINTS:
        return

    if request.blueprint not in {"web", "api"}:
        return

    current_user = get_current_user()
    if current_user is None:
        return

    try:
        record_user_action_event(
            user_account_id=current_user.id,
            auth_session_audit_id=get_current_auth_session_audit_id(),
            action_type=_generic_action_type(request.method),
            resource_type=_resource_type_from_endpoint(endpoint),
            resource_id=_resource_id_from_view_args(request.view_args),
            request_method=request.method,
            request_path=request.path,
            status_code=response.status_code,
            outcome_code=_outcome_code_from_status(response.status_code),
            ip_address=_request_ip_address(),
            user_agent=request.headers.get("User-Agent"),
            details={
                "endpoint": endpoint,
                "view_args": request.view_args or {},
            },
        )
    except Exception:
        current_app.logger.exception("Failed to record user_action_audit.")


def _generic_action_type(method: str) -> str:
    if method == "DELETE":
        return "delete"
    if method in {"POST", "PUT", "PATCH"}:
        return "execute"
    return "read"


def _outcome_code_from_status(status_code: int) -> str:
    if 200 <= status_code < 300:
        return "success"
    if 300 <= status_code < 400:
        return "redirect"
    if 400 <= status_code < 500:
        return "client_error"
    return "server_error"


def _resource_type_from_endpoint(endpoint: str) -> str:
    if "." in endpoint:
        return endpoint.split(".", 1)[1]
    return endpoint


def _resource_id_from_view_args(view_args: dict | None) -> str | None:
    if not view_args:
        return None

    for key, value in view_args.items():
        if key == "id" or key.endswith("_id"):
            return str(value)
    return None


def _request_ip_address() -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr


def _next_url_value() -> str:
    next_value = request.full_path.rstrip("?")
    return next_value if next_value.startswith("/") else request.path


def _is_auth_exempt_endpoint(endpoint: str) -> bool:
    return endpoint in _WEB_EXEMPT_ENDPOINTS or endpoint in _API_EXEMPT_ENDPOINTS or endpoint == "static"


def _api_error_response(error_code: str, status_code: int):
    payload = {
        "error_code": error_code,
        "message": translate(f"api.errors.{error_code}", locale=get_locale()),
        "locale": get_locale(),
    }
    return jsonify(payload), status_code


def _web_forbidden_response():
    return (
        translate("auth.errors.forbidden", locale=get_locale()),
        403,
    )
