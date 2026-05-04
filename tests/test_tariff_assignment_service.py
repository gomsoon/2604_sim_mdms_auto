from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import ServicePointTariffAssignment
from app.services.master_data import MasterDataValidationError, create_service_point
from app.services.tariff_assignments import (
    create_tariff_assignment,
    find_applicable_tariff_assignment,
    update_tariff_assignment,
)


def test_create_tariff_assignment_auto_closes_previous_current_row(session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-TARIFF-1001",
        service_type="electric",
        name="Tariff Site",
        status="active",
    )

    first = create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="RES-A",
        tariff_version_code="v1",
        effective_from="2026-01-01T00:00:00+09:00",
        effective_to=None,
        source_system="manual",
        source_reference="tariff-1",
    )
    second = create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="RES-B",
        tariff_version_code="v2",
        effective_from="2026-02-01T00:00:00+09:00",
        effective_to=None,
        source_system="manual",
        source_reference="tariff-2",
    )

    session.commit()
    rows = session.scalars(
        select(ServicePointTariffAssignment)
        .where(ServicePointTariffAssignment.service_point_id == service_point.id)
        .order_by(ServicePointTariffAssignment.id.asc())
    ).all()

    assert len(rows) == 2
    assert first.is_current is False
    assert first.effective_to == second.effective_from
    assert second.is_current is True


def test_create_tariff_assignment_rejects_overlap(session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-TARIFF-2001",
        service_type="electric",
        name="Overlap Site",
        status="active",
    )

    create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="RES-A",
        tariff_version_code=None,
        effective_from="2026-02-01T00:00:00+00:00",
        effective_to=None,
        source_system="manual",
        source_reference="tariff-a",
    )

    with pytest.raises(MasterDataValidationError) as exc_info:
        create_tariff_assignment(
            session,
            service_point_id=service_point.id,
            tariff_plan_code="RES-B",
            tariff_version_code=None,
            effective_from="2026-01-15T00:00:00+00:00",
            effective_to=None,
            source_system="manual",
            source_reference="tariff-b",
        )

    assert exc_info.value.error_code == "overlapping_tariff_assignment"


def test_update_tariff_assignment_rejects_overlap(session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-TARIFF-3001",
        service_type="electric",
        name="Update Site",
        status="active",
    )
    first = create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="RES-A",
        tariff_version_code=None,
        effective_from="2026-01-01T00:00:00+00:00",
        effective_to="2026-02-01T00:00:00+00:00",
        source_system="manual",
        source_reference="tariff-a",
    )
    second = create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="RES-B",
        tariff_version_code=None,
        effective_from="2026-02-01T00:00:00+00:00",
        effective_to=None,
        source_system="manual",
        source_reference="tariff-b",
    )
    session.commit()

    with pytest.raises(MasterDataValidationError) as exc_info:
        update_tariff_assignment(
            session,
            second,
            tariff_plan_code="RES-B",
            tariff_version_code=None,
            effective_from="2026-01-15T00:00:00+00:00",
            effective_to=None,
            source_system="manual",
            source_reference="tariff-b",
        )

    assert exc_info.value.error_code == "overlapping_tariff_assignment"
    assert first.is_current is False


def test_find_applicable_tariff_assignment_uses_half_open_window(session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-TARIFF-4001",
        service_type="electric",
        name="Lookup Site",
        status="active",
    )
    first = create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="RES-A",
        tariff_version_code="v1",
        effective_from="2026-01-01T00:00:00+00:00",
        effective_to="2026-02-01T00:00:00+00:00",
        source_system="manual",
        source_reference="tariff-a",
    )
    second = create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="RES-B",
        tariff_version_code="v2",
        effective_from="2026-02-01T00:00:00+00:00",
        effective_to=None,
        source_system="manual",
        source_reference="tariff-b",
    )
    session.commit()

    before_boundary = find_applicable_tariff_assignment(
        session,
        service_point_id=service_point.id,
        target_at=datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc),
    )
    at_boundary = find_applicable_tariff_assignment(
        session,
        service_point_id=service_point.id,
        target_at=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
    )

    assert before_boundary is not None
    assert before_boundary.id == first.id
    assert at_boundary is not None
    assert at_boundary.id == second.id
