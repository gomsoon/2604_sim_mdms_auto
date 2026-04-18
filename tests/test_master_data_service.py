from __future__ import annotations

import pytest

from app.services.master_data import (
    MasterDataValidationError,
    create_device,
    create_measuring_component,
    create_service_point,
)


def test_create_service_point_rejects_empty_external_id(session):
    with pytest.raises(MasterDataValidationError) as exc_info:
        create_service_point(
            session,
            source_system="HES",
            external_id="",
            service_type="electric",
            name="Boundary",
            status="active",
        )

    assert exc_info.value.error_code == "missing_external_id"


def test_create_device_rejects_unknown_service_point(session):
    with pytest.raises(MasterDataValidationError) as exc_info:
        create_device(
            session,
            source_system="HES",
            external_meter_id="MTR-4040",
            serial_number="SER-4040",
            service_point_id=999999,
            status="active",
        )

    assert exc_info.value.error_code == "service_point_not_found"


def test_create_measuring_component_rejects_zero_multiplier(session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-2001",
        service_type="electric",
        name="Boundary Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-2001",
        serial_number="SER-2001",
        service_point_id=service_point.id,
        status="active",
    )

    with pytest.raises(MasterDataValidationError) as exc_info:
        create_measuring_component(
            session,
            source_system="HES",
            external_channel_id="CH-01",
            unit_of_measure="kWh",
            multiplier=0,
            status="active",
            device_id=device.id,
            service_point_id=service_point.id,
        )

    assert exc_info.value.error_code == "invalid_multiplier"


def test_create_measuring_component_rejects_device_service_point_mismatch(session):
    service_point_a = create_service_point(
        session,
        source_system="HES",
        external_id="SP-3001",
        service_type="electric",
        name="Site A",
        status="active",
    )
    service_point_b = create_service_point(
        session,
        source_system="HES",
        external_id="SP-3002",
        service_type="electric",
        name="Site B",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-3001",
        serial_number="SER-3001",
        service_point_id=service_point_a.id,
        status="active",
    )

    with pytest.raises(MasterDataValidationError) as exc_info:
        create_measuring_component(
            session,
            source_system="HES",
            external_channel_id="CH-99",
            unit_of_measure="kWh",
            multiplier=1,
            status="active",
            device_id=device.id,
            service_point_id=service_point_b.id,
        )

    assert exc_info.value.error_code == "component_service_point_device_mismatch"
