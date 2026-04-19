from __future__ import annotations

import os
import shutil
import threading

import pytest
from playwright.sync_api import Browser, Error as PlaywrightError, Page, sync_playwright
from werkzeug.serving import make_server

from app import create_app
from app.db import get_session
from app.migrations import upgrade_db
from app.services.seeds import seed_demo_environment


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
def functional_app(tmp_path_factory: pytest.TempPathFactory):
    work_dir = tmp_path_factory.mktemp("functional")
    database_path = work_dir / "functional.db"

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("SECRET_KEY", "functional-secret")

    app = create_app()
    app.config.update(TESTING=True)
    upgrade_db(app.config["DATABASE_URL"])

    session = get_session()
    try:
        seed_demo_environment(session)
        session.commit()
    except Exception:
        session.rollback()
        raise

    try:
        yield app
    finally:
        session.remove()
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
    try:
        yield page
    finally:
        context.close()
