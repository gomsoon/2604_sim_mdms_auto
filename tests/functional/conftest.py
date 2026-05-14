from __future__ import annotations

import os
import re
import shutil
import sys
import threading
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Error as PlaywrightError, Page, sync_playwright
from werkzeug.serving import make_server

from app import create_app
from app.db import get_session
from app.migrations import upgrade_db
from app.services.auth import create_user_account
from app.services.seeds import seed_demo_environment
TESTS_DIR = Path(__file__).resolve().parent.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from postgresql_support import (  # noqa: E402
    build_schema_name,
    build_schema_url,
    create_schema,
    drop_schema,
    resolve_test_database_url,
)


def _resolve_chrome_executable() -> str | None:
    configured = os.getenv("PLAYWRIGHT_CHROME_PATH")
    if configured:
        return configured

    for candidate in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        executable = shutil.which(candidate)
        if executable:
            return executable

    return None


@pytest.fixture(scope="session")
def functional_app():
    test_database_url = resolve_test_database_url()
    schema_name = build_schema_name(prefix="functional")
    schema_url = build_schema_url(test_database_url, schema_name)
    create_schema(test_database_url, schema_name)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("TEST_DATABASE_URL", test_database_url)
    monkeypatch.setenv("DATABASE_URL", schema_url)
    monkeypatch.setenv("SECRET_KEY", "functional-secret")

    app = create_app()
    app.config.update(TESTING=True)
    upgrade_db(schema_url)

    session = get_session()
    try:
        seed_demo_environment(session)
        create_user_account(
            session,
            login_id="functional-admin",
            display_name="Functional Admin",
            role_code="admin",
            password="functional-password",
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    try:
        yield app
    finally:
        session.remove()
        drop_schema(test_database_url, schema_name)
        monkeypatch.undo()


@pytest.fixture(scope="session")
def live_server(functional_app):
    server = make_server("127.0.0.1", 0, functional_app)
    port = server.socket.getsockname()[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture(scope="session")
def browser() -> Browser:
    chrome_executable = _resolve_chrome_executable()
    if chrome_executable is None:
        pytest.skip("System Chrome executable is not available for Playwright smoke tests.")

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                executable_path=chrome_executable,
                headless=True,
                args=["--no-sandbox"],
            )
        except PlaywrightError as exc:
            pytest.skip(f"Playwright browser launch is not available in this environment: {exc}")
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(browser: Browser, live_server: str) -> Page:
    context = browser.new_context(base_url=live_server, locale="en-US")
    page = context.new_page()
    page.goto("/login?lang=en", wait_until="networkidle")
    page.get_by_label("Login ID").fill("functional-admin")
    page.get_by_label("Password").fill("functional-password")
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_url(re.compile(r".*/(?:\?lang=en)?$"))
    try:
        yield page
    finally:
        context.close()
