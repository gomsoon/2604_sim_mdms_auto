from __future__ import annotations

import re

from playwright.sync_api import Page, expect


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
