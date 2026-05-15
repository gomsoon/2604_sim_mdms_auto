from __future__ import annotations

from sqlalchemy import inspect

from app.models import (
    EstimationAudit,
    FinalMeasurement,
    InitialMeasurement,
    PipelineRun,
    RawIntervalWindowState,
    ServicePoint,
    UserAccount,
    VeeException,
)


def test_estimation_audit_columns_exist():
    mapper = inspect(EstimationAudit)

    assert "pipeline_run_id" in mapper.columns
    assert "service_point_id" in mapper.columns
    assert "measuring_component_id" in mapper.columns
    assert "device_id" in mapper.columns
    assert "target_initial_measurement_id" in mapper.columns
    assert "anchor_vee_exception_id" in mapper.columns
    assert "raw_interval_window_state_id" in mapper.columns
    assert "target_measured_at" in mapper.columns
    assert "estimation_mode" in mapper.columns
    assert "estimated_by" in mapper.columns
    assert "estimated_by_user_account_id" in mapper.columns
    assert "strategy_code" in mapper.columns
    assert "estimation_status" in mapper.columns
    assert "estimated_value" in mapper.columns
    assert "unit_of_measure" in mapper.columns
    assert "source_previous_final_measurement_id" in mapper.columns
    assert "source_next_final_measurement_id" in mapper.columns
    assert "superseded_final_measurement_id" in mapper.columns
    assert "result_final_measurement_id" in mapper.columns
    assert "operator_memo" in mapper.columns
    assert "details" in mapper.columns


def test_estimation_audit_relationships_exist():
    service_point_mapper = inspect(ServicePoint)
    initial_mapper = inspect(InitialMeasurement)
    final_mapper = inspect(FinalMeasurement)
    pipeline_run_mapper = inspect(PipelineRun)
    vee_exception_mapper = inspect(VeeException)
    raw_interval_window_state_mapper = inspect(RawIntervalWindowState)
    user_account_mapper = inspect(UserAccount)

    assert "estimation_audits" in service_point_mapper.relationships
    assert "estimation_audits" in initial_mapper.relationships
    assert "estimation_audits" in vee_exception_mapper.relationships
    assert "estimation_audits" in raw_interval_window_state_mapper.relationships
    assert "previous_source_estimation_audits" in final_mapper.relationships
    assert "result_estimation_audits" in final_mapper.relationships
    assert "estimation_audits" in pipeline_run_mapper.relationships
    assert "estimated_estimation_audits" in user_account_mapper.relationships
