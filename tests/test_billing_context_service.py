from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import ServicePointBillingContext
from app.services.billing_contexts import create_billing_context, update_billing_context
from app.services.master_data import MasterDataValidationError, create_service_point


def test_create_billing_context_auto_closes_previous_current_row(session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-BCTX-1001",
        service_type="electric",
        name="Billing Site",
        status="active",
    )

    first = create_billing_context(
        session,
        service_point_id=service_point.id,
        timezone_name="Asia/Seoul",
        billing_cycle_mode="calendar_month",
        billing_cycle_anchor_day=None,
        currency_code="KRW",
        effective_from="2026-01-01T00:00",
        effective_to=None,
        source_system="manual",
        source_reference="ctx-1",
    )
    second = create_billing_context(
        session,
        service_point_id=service_point.id,
        timezone_name="Asia/Seoul",
        billing_cycle_mode="calendar_month",
        billing_cycle_anchor_day=None,
        currency_code="KRW",
        effective_from="2026-02-01T00:00",
        effective_to=None,
        source_system="manual",
        source_reference="ctx-2",
    )

    session.commit()
    rows = session.scalars(
        select(ServicePointBillingContext)
        .where(ServicePointBillingContext.service_point_id == service_point.id)
        .order_by(ServicePointBillingContext.id.asc())
    ).all()

    assert len(rows) == 2
    assert first.is_current is False
    assert first.effective_to == second.effective_from
    assert second.is_current is True


def test_create_billing_context_rejects_invalid_anchor_day(session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-BCTX-2001",
        service_type="electric",
        name="Anchor Site",
        status="active",
    )

    with pytest.raises(MasterDataValidationError) as exc_info:
        create_billing_context(
            session,
            service_point_id=service_point.id,
            timezone_name="Asia/Seoul",
            billing_cycle_mode="anchored_month",
            billing_cycle_anchor_day=31,
            currency_code="KRW",
            effective_from="2026-01-01T00:00",
            effective_to=None,
            source_system="manual",
            source_reference="ctx-anchor",
        )

    assert exc_info.value.error_code == "invalid_billing_cycle_anchor_day"


def test_update_billing_context_rejects_overlapping_period(session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-BCTX-3001",
        service_type="electric",
        name="Overlap Site",
        status="active",
    )
    current_row = create_billing_context(
        session,
        service_point_id=service_point.id,
        timezone_name="Asia/Seoul",
        billing_cycle_mode="calendar_month",
        billing_cycle_anchor_day=None,
        currency_code="KRW",
        effective_from="2026-01-01T00:00",
        effective_to=None,
        source_system="manual",
        source_reference="ctx-current",
    )
    history_row = create_billing_context(
        session,
        service_point_id=service_point.id,
        timezone_name="Asia/Seoul",
        billing_cycle_mode="calendar_month",
        billing_cycle_anchor_day=None,
        currency_code="KRW",
        effective_from="2026-02-01T00:00",
        effective_to=None,
        source_system="manual",
        source_reference="ctx-history",
    )
    session.commit()

    with pytest.raises(MasterDataValidationError) as exc_info:
        update_billing_context(
            session,
            history_row,
            timezone_name="Asia/Seoul",
            billing_cycle_mode="calendar_month",
            billing_cycle_anchor_day=None,
            currency_code="KRW",
            effective_from="2026-01-15T00:00",
            effective_to=None,
            source_system="manual",
            source_reference="ctx-history",
        )

    assert exc_info.value.error_code == "overlapping_billing_context"
    assert current_row.is_current is False
