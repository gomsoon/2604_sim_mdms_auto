from __future__ import annotations

from sqlalchemy import inspect

from app.models import (
    FinalMeasurement,
    InitialMeasurement,
    ManualEditAudit,
    PipelineRun,
    ServicePoint,
    UserAccount,
    VeeException,
)


def test_manual_edit_audit_columns_exist():
    mapper = inspect(ManualEditAudit)

    assert "pipeline_run_id" in mapper.columns
    assert "service_point_id" in mapper.columns
    assert "measuring_component_id" in mapper.columns
    assert "device_id" in mapper.columns
    assert "target_initial_measurement_id" in mapper.columns
    assert "related_vee_exception_id" in mapper.columns
    assert "target_measured_at" in mapper.columns
    assert "reason_code" in mapper.columns
    assert "edit_status" in mapper.columns
    assert "edited_value" in mapper.columns
    assert "edited_quality_code" in mapper.columns
    assert "edited_status_code" in mapper.columns
    assert "edited_by" in mapper.columns
    assert "edited_by_user_account_id" in mapper.columns
    assert "operator_memo" in mapper.columns
    assert "superseded_final_measurement_id" in mapper.columns
    assert "result_final_measurement_id" in mapper.columns
    assert "details" in mapper.columns


def test_manual_edit_audit_relationships_exist():
    service_point_mapper = inspect(ServicePoint)
    initial_mapper = inspect(InitialMeasurement)
    vee_exception_mapper = inspect(VeeException)
    final_mapper = inspect(FinalMeasurement)
    pipeline_run_mapper = inspect(PipelineRun)
    user_account_mapper = inspect(UserAccount)

    assert "manual_edit_audits" in service_point_mapper.relationships
    assert "manual_edit_audits" in initial_mapper.relationships
    assert "manual_edit_audits" in vee_exception_mapper.relationships
    assert "superseded_manual_edit_audits" in final_mapper.relationships
    assert "result_manual_edit_audits" in final_mapper.relationships
    assert "manual_edit_audits" in pipeline_run_mapper.relationships
    assert "edited_manual_edit_audits" in user_account_mapper.relationships
