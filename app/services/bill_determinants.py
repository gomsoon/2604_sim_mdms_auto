from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import BillDeterminant, UsageTransaction
from app.services.pipeline import (
    complete_pipeline_run,
    fail_pipeline_run,
    start_pipeline_run,
    upsert_processing_watermark,
)


BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL = "billing_cycle_consumption_total"
SUPPORTED_BILL_DETERMINANT_TYPES = {
    BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
}

_DETERMINANT_SOURCE_USAGE_TYPE = {
    BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL: "monthly_consumption",
}

_DETERMINANT_WATERMARK_RECORD_TYPE = {
    BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL: "billing_cycle_total",
}


@dataclass(frozen=True, slots=True)
class BillDeterminantCalculationSummary:
    determinant_type: str
    groups: int
    created: int
    superseded: int
    reused: int
    complete: int
    partial: int
    blocked: int


def _load_source_usage_transactions(
    session: Session,
    *,
    determinant_type: str,
    service_point_id: int | None,
    measuring_component_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[UsageTransaction]:
    source_usage_type = _DETERMINANT_SOURCE_USAGE_TYPE[determinant_type]
    statement: Select[tuple[UsageTransaction]] = (
        select(UsageTransaction)
        .where(UsageTransaction.usage_type == source_usage_type)
        .order_by(UsageTransaction.id.asc())
    )
    if service_point_id is not None:
        statement = statement.where(UsageTransaction.service_point_id == service_point_id)
    if measuring_component_id is not None:
        statement = statement.where(
            UsageTransaction.measuring_component_id == measuring_component_id
        )
    if date_from is not None:
        statement = statement.where(UsageTransaction.period_start_at >= date_from)
    if date_to is not None:
        statement = statement.where(UsageTransaction.period_end_at <= date_to)
    return session.execute(statement).scalars().all()


def _build_bill_determinant_payload(
    usage_row: UsageTransaction,
    *,
    trigger_type: str,
    details_context: dict[str, object] | None,
) -> dict[str, object]:
    provenance: dict[str, object] = {
        "trigger_type": trigger_type,
        "trigger_source": "bill_determinant_calculation",
        "source_usage_transaction_ids": [usage_row.id],
    }
    if details_context:
        replay_context = {
            key: value
            for key, value in details_context.items()
            if key != "trigger_source"
        }
        if details_context.get("trigger_source"):
            provenance["trigger_source"] = str(details_context["trigger_source"])
        if replay_context:
            provenance["replay_context"] = replay_context

    return {
        "window_timezone_name": usage_row.window_timezone_name,
        "unit_of_measure": usage_row.unit_of_measure or "UNKNOWN",
        "determinant_value": usage_row.usage_value,
        "source_usage_count": 1,
        "quality_summary": usage_row.quality_summary,
        "calculation_status": usage_row.calculation_status,
        "details": {
            "billing_period_source": "usage_period",
            "source_usage_type": usage_row.usage_type,
            "source_usage_calculation_status": usage_row.calculation_status,
            "source_usage_quality_summary": usage_row.quality_summary,
            "provenance": provenance,
        },
    }


def _find_current_bill_determinant(
    session: Session,
    *,
    usage_row: UsageTransaction,
    determinant_type: str,
) -> BillDeterminant | None:
    return session.scalar(
        select(BillDeterminant)
        .where(BillDeterminant.service_point_id == usage_row.service_point_id)
        .where(BillDeterminant.measuring_component_id == usage_row.measuring_component_id)
        .where(BillDeterminant.determinant_type == determinant_type)
        .where(BillDeterminant.billing_period_start_at == usage_row.period_start_at)
        .where(BillDeterminant.billing_period_end_at == usage_row.period_end_at)
        .where(BillDeterminant.tariff_plan_code.is_(None))
        .where(BillDeterminant.tou_bucket_code.is_(None))
        .where(BillDeterminant.demand_window_code.is_(None))
        .where(BillDeterminant.is_current.is_(True))
        .limit(1)
    )


def _same_snapshot(
    current_row: BillDeterminant,
    *,
    usage_row: UsageTransaction,
    payload: dict[str, object],
) -> bool:
    return (
        current_row.device_id == usage_row.device_id
        and current_row.window_timezone_name == payload["window_timezone_name"]
        and current_row.unit_of_measure == payload["unit_of_measure"]
        and current_row.determinant_value == payload["determinant_value"]
        and current_row.source_usage_count == payload["source_usage_count"]
        and current_row.quality_summary == payload["quality_summary"]
        and current_row.calculation_status == payload["calculation_status"]
    )


def calculate_bill_determinants(
    session: Session,
    *,
    determinant_type: str,
    service_point_id: int | None = None,
    measuring_component_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    trigger_type: str = "manual",
    revision_reason_code: str | None = None,
    details_context: dict[str, object] | None = None,
) -> BillDeterminantCalculationSummary:
    if determinant_type not in SUPPORTED_BILL_DETERMINANT_TYPES:
        raise ValueError(f"Unsupported bill determinant type: {determinant_type}")

    usage_rows = _load_source_usage_transactions(
        session,
        determinant_type=determinant_type,
        service_point_id=service_point_id,
        measuring_component_id=measuring_component_id,
        date_from=date_from,
        date_to=date_to,
    )
    pipeline_run = start_pipeline_run(
        session,
        pipeline_name="bill_determinant",
        trigger_type=trigger_type,
        details={
            "determinant_type": determinant_type,
            "service_point_id": service_point_id,
            "measuring_component_id": measuring_component_id,
            "date_from": date_from.isoformat() if date_from is not None else None,
            "date_to": date_to.isoformat() if date_to is not None else None,
            "trigger_context": details_context or None,
        },
    )

    try:
        created = 0
        superseded = 0
        reused = 0
        complete = 0
        partial = 0
        blocked = 0
        calculated_at = datetime.now(timezone.utc)
        latest_billing_period_end_at: datetime | None = None

        for usage_row in usage_rows:
            payload = _build_bill_determinant_payload(
                usage_row,
                trigger_type=trigger_type,
                details_context=details_context,
            )
            if payload["calculation_status"] == "complete":
                complete += 1
            elif payload["calculation_status"] == "partial":
                partial += 1
            else:
                blocked += 1

            current_row = _find_current_bill_determinant(
                session,
                usage_row=usage_row,
                determinant_type=determinant_type,
            )
            if current_row is None:
                session.add(
                    BillDeterminant(
                        pipeline_run_id=pipeline_run.id,
                        service_point_id=usage_row.service_point_id,
                        measuring_component_id=usage_row.measuring_component_id,
                        device_id=usage_row.device_id,
                        determinant_type=determinant_type,
                        billing_period_start_at=usage_row.period_start_at,
                        billing_period_end_at=usage_row.period_end_at,
                        window_timezone_name=str(payload["window_timezone_name"]),
                        tariff_plan_code=None,
                        tou_bucket_code=None,
                        demand_window_code=None,
                        unit_of_measure=str(payload["unit_of_measure"]),
                        determinant_value=payload["determinant_value"],
                        source_usage_count=int(payload["source_usage_count"]),
                        quality_summary=str(payload["quality_summary"]),
                        calculation_status=str(payload["calculation_status"]),
                        revision_number=1,
                        revision_reason_code=revision_reason_code,
                        is_current=True,
                        supersedes_bill_determinant_id=None,
                        calculated_at=calculated_at,
                        details=dict(payload["details"]),
                    )
                )
                created += 1
            elif _same_snapshot(current_row, usage_row=usage_row, payload=payload):
                reused += 1
            else:
                current_row.is_current = False
                current_row.revision_reason_code = (
                    revision_reason_code or "re_determined"
                )
                session.add(
                    BillDeterminant(
                        pipeline_run_id=pipeline_run.id,
                        service_point_id=usage_row.service_point_id,
                        measuring_component_id=usage_row.measuring_component_id,
                        device_id=usage_row.device_id,
                        determinant_type=determinant_type,
                        billing_period_start_at=usage_row.period_start_at,
                        billing_period_end_at=usage_row.period_end_at,
                        window_timezone_name=str(payload["window_timezone_name"]),
                        tariff_plan_code=None,
                        tou_bucket_code=None,
                        demand_window_code=None,
                        unit_of_measure=str(payload["unit_of_measure"]),
                        determinant_value=payload["determinant_value"],
                        source_usage_count=int(payload["source_usage_count"]),
                        quality_summary=str(payload["quality_summary"]),
                        calculation_status=str(payload["calculation_status"]),
                        revision_number=current_row.revision_number + 1,
                        revision_reason_code=revision_reason_code or "re_determined",
                        is_current=True,
                        supersedes_bill_determinant_id=current_row.id,
                        calculated_at=calculated_at,
                        details=dict(payload["details"]),
                    )
                )
                superseded += 1

            latest_billing_period_end_at = (
                usage_row.period_end_at
                if latest_billing_period_end_at is None
                or usage_row.period_end_at > latest_billing_period_end_at
                else latest_billing_period_end_at
            )

        session.flush()

        summary = BillDeterminantCalculationSummary(
            determinant_type=determinant_type,
            groups=len(usage_rows),
            created=created,
            superseded=superseded,
            reused=reused,
            complete=complete,
            partial=partial,
            blocked=blocked,
        )
        details = {
            **pipeline_run.details,
            "groups": summary.groups,
            "created": summary.created,
            "superseded": summary.superseded,
            "reused": summary.reused,
            "complete": summary.complete,
            "partial": summary.partial,
            "blocked": summary.blocked,
            "source_usage_count": len(usage_rows),
        }
        if latest_billing_period_end_at is not None:
            upsert_processing_watermark(
                session,
                pipeline_name="bill_determinant",
                source_system=None,
                record_type=_DETERMINANT_WATERMARK_RECORD_TYPE[determinant_type],
                last_processed_at=latest_billing_period_end_at,
                details=details,
            )

        if summary.groups == 0:
            result_code = "bill_determinant_noop"
        elif summary.blocked > 0:
            result_code = "bill_determinant_completed_with_blocked"
        elif summary.partial > 0:
            result_code = "bill_determinant_completed_with_partial"
        else:
            result_code = "bill_determinant_completed"
        complete_pipeline_run(
            pipeline_run,
            result_code=result_code,
            details=details,
        )
        return summary
    except Exception:
        fail_pipeline_run(
            pipeline_run,
            result_code="bill_determinant_failed_exception",
            details={
                **pipeline_run.details,
                "source_usage_count": len(usage_rows),
            },
        )
        raise
