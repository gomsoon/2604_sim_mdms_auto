from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models import BillCharge, BillDeterminant
from app.services.bill_determinants import (
    BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
)
from app.services.pipeline import (
    complete_pipeline_run,
    fail_pipeline_run,
    start_pipeline_run,
    upsert_processing_watermark,
)
from app.services.tariff_assignments import find_applicable_tariff_assignment


BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE = "flat_energy_charge"
SUPPORTED_BILL_CHARGE_TYPES = {
    BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
}

_CHARGE_SOURCE_DETERMINANT_TYPE = {
    BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE: BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
}

_CHARGE_WATERMARK_RECORD_TYPE = {
    BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE: "flat_energy_charge",
}

_RATE_SCALE = Decimal("0.00000001")
_CHARGE_SCALE = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class BillChargeCalculationSummary:
    charge_type: str
    groups: int
    created: int
    superseded: int
    reused: int
    complete: int
    partial: int
    blocked: int


def _normalize_rate(value: Decimal | int | float | str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        normalized = value
    else:
        normalized = Decimal(str(value))
    return normalized.quantize(_RATE_SCALE, rounding=ROUND_HALF_UP)


def _load_source_bill_determinants(
    session: Session,
    *,
    charge_type: str,
    service_point_id: int | None,
    measuring_component_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[BillDeterminant]:
    source_determinant_type = _CHARGE_SOURCE_DETERMINANT_TYPE[charge_type]
    statement: Select[tuple[BillDeterminant]] = (
        select(BillDeterminant)
        .where(BillDeterminant.determinant_type == source_determinant_type)
        .where(BillDeterminant.is_current.is_(True))
        .order_by(BillDeterminant.id.asc())
    )
    if service_point_id is not None:
        statement = statement.where(BillDeterminant.service_point_id == service_point_id)
    if measuring_component_id is not None:
        statement = statement.where(
            BillDeterminant.measuring_component_id == measuring_component_id
        )
    if date_from is not None:
        statement = statement.where(BillDeterminant.billing_period_start_at >= date_from)
    if date_to is not None:
        statement = statement.where(BillDeterminant.billing_period_end_at <= date_to)
    return session.execute(statement).scalars().all()


def _build_bill_charge_payload(
    session: Session,
    determinant_row: BillDeterminant,
    *,
    unit_rate_value: Decimal | None,
    trigger_type: str,
    details_context: dict[str, object] | None,
) -> dict[str, object]:
    provenance: dict[str, object] = {
        "trigger_type": trigger_type,
        "trigger_source": "bill_charge_calculation",
        "source_bill_determinant_ids": [determinant_row.id],
    }
    if details_context:
        replay_context = {
            key: value for key, value in details_context.items() if key != "trigger_source"
        }
        if details_context.get("trigger_source"):
            provenance["trigger_source"] = str(details_context["trigger_source"])
        if replay_context:
            provenance["replay_context"] = replay_context

    billing_context_snapshot = None
    billing_period_source = None
    if isinstance(determinant_row.details, dict):
        billing_context_snapshot = determinant_row.details.get("billing_context_snapshot")
        billing_period_source = determinant_row.details.get("billing_period_source")

    tariff_assignment = find_applicable_tariff_assignment(
        session=session,
        service_point_id=determinant_row.service_point_id,
        target_at=determinant_row.billing_period_start_at,
    )
    tariff_assignment_snapshot: dict[str, object] | None = None
    if tariff_assignment is not None:
        tariff_assignment_snapshot = {
            "tariff_assignment_id": tariff_assignment.id,
            "tariff_plan_code": tariff_assignment.tariff_plan_code,
            "tariff_version_code": tariff_assignment.tariff_version_code,
            "effective_from": tariff_assignment.effective_from.isoformat(),
            "effective_to": (
                tariff_assignment.effective_to.isoformat()
                if tariff_assignment.effective_to is not None
                else None
            ),
            "source_system": tariff_assignment.source_system,
            "source_reference": tariff_assignment.source_reference,
        }

    quantity_value = determinant_row.determinant_value
    currency_code = None
    if isinstance(billing_context_snapshot, dict):
        raw_currency = billing_context_snapshot.get("currency_code")
        if raw_currency:
            currency_code = str(raw_currency)

    calculation_status = determinant_row.calculation_status
    quality_summary = determinant_row.quality_summary
    charge_amount: Decimal | None = None

    if determinant_row.calculation_status == "blocked":
        calculation_status = "blocked"
        quality_summary = "blocked_source_determinant"
    elif tariff_assignment is None:
        calculation_status = "blocked"
        quality_summary = "blocked_missing_tariff_assignment"
    elif unit_rate_value is None:
        calculation_status = "blocked"
        quality_summary = "blocked_missing_tariff_rate"
    elif not currency_code:
        calculation_status = "blocked"
        quality_summary = "blocked_missing_currency_code"
    else:
        charge_amount = (quantity_value * unit_rate_value).quantize(
            _CHARGE_SCALE,
            rounding=ROUND_HALF_UP,
        )

    return {
        "currency_code": currency_code,
        "tariff_plan_code": (
            tariff_assignment.tariff_plan_code if tariff_assignment is not None else None
        ),
        "tariff_version_code": (
            tariff_assignment.tariff_version_code if tariff_assignment is not None else None
        ),
        "quantity_value": quantity_value,
        "unit_rate_value": unit_rate_value,
        "charge_amount": charge_amount,
        "calculation_status": calculation_status,
        "quality_summary": quality_summary,
        "details": {
            "billing_context_snapshot": billing_context_snapshot,
            "billing_period_source": billing_period_source,
            "tariff_assignment_snapshot": tariff_assignment_snapshot,
            "rate_snapshot": {
                "rate_kind": "flat_energy_rate",
                "unit_rate_value": str(unit_rate_value) if unit_rate_value is not None else None,
                "currency_code": currency_code,
            },
            "source_bill_determinant_snapshot": {
                "bill_determinant_id": determinant_row.id,
                "determinant_type": determinant_row.determinant_type,
                "billing_period_start_at": determinant_row.billing_period_start_at.isoformat(),
                "billing_period_end_at": determinant_row.billing_period_end_at.isoformat(),
                "unit_of_measure": determinant_row.unit_of_measure,
                "determinant_value": str(determinant_row.determinant_value),
                "calculation_status": determinant_row.calculation_status,
                "quality_summary": determinant_row.quality_summary,
                "revision_number": determinant_row.revision_number,
            },
            "provenance": provenance,
        },
    }


def _find_current_bill_charge(
    session: Session,
    *,
    determinant_row: BillDeterminant,
    charge_type: str,
) -> BillCharge | None:
    return session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == determinant_row.service_point_id)
        .where(BillCharge.measuring_component_id == determinant_row.measuring_component_id)
        .where(BillCharge.charge_type == charge_type)
        .where(BillCharge.billing_period_start_at == determinant_row.billing_period_start_at)
        .where(BillCharge.billing_period_end_at == determinant_row.billing_period_end_at)
        .where(BillCharge.is_current.is_(True))
        .limit(1)
    )


def _same_snapshot(
    current_row: BillCharge,
    *,
    determinant_row: BillDeterminant,
    payload: dict[str, object],
) -> bool:
    return (
        current_row.device_id == determinant_row.device_id
        and current_row.bill_determinant_id == determinant_row.id
        and current_row.currency_code == payload["currency_code"]
        and current_row.tariff_plan_code == payload["tariff_plan_code"]
        and current_row.tariff_version_code == payload["tariff_version_code"]
        and current_row.quantity_value == payload["quantity_value"]
        and current_row.unit_rate_value == payload["unit_rate_value"]
        and current_row.charge_amount == payload["charge_amount"]
        and current_row.calculation_status == payload["calculation_status"]
        and current_row.quality_summary == payload["quality_summary"]
    )


def calculate_bill_charges(
    session: Session,
    *,
    charge_type: str,
    unit_rate_value: Decimal | int | float | str | None,
    service_point_id: int | None = None,
    measuring_component_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    trigger_type: str = "manual",
    revision_reason_code: str | None = None,
    details_context: dict[str, object] | None = None,
) -> BillChargeCalculationSummary:
    if charge_type not in SUPPORTED_BILL_CHARGE_TYPES:
        raise ValueError(f"Unsupported bill charge type: {charge_type}")

    normalized_rate = _normalize_rate(unit_rate_value)
    determinant_rows = _load_source_bill_determinants(
        session,
        charge_type=charge_type,
        service_point_id=service_point_id,
        measuring_component_id=measuring_component_id,
        date_from=date_from,
        date_to=date_to,
    )
    pipeline_run = start_pipeline_run(
        session,
        pipeline_name="bill_charge",
        trigger_type=trigger_type,
        details={
            "charge_type": charge_type,
            "service_point_id": service_point_id,
            "measuring_component_id": measuring_component_id,
            "date_from": date_from.isoformat() if date_from is not None else None,
            "date_to": date_to.isoformat() if date_to is not None else None,
            "unit_rate_value": str(normalized_rate) if normalized_rate is not None else None,
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

        for determinant_row in determinant_rows:
            payload = _build_bill_charge_payload(
                session,
                determinant_row,
                unit_rate_value=normalized_rate,
                trigger_type=trigger_type,
                details_context=details_context,
            )
            if payload["calculation_status"] == "complete":
                complete += 1
            elif payload["calculation_status"] == "partial":
                partial += 1
            else:
                blocked += 1

            current_row = _find_current_bill_charge(
                session,
                determinant_row=determinant_row,
                charge_type=charge_type,
            )
            if current_row is None:
                session.add(
                    BillCharge(
                        pipeline_run_id=pipeline_run.id,
                        service_point_id=determinant_row.service_point_id,
                        measuring_component_id=determinant_row.measuring_component_id,
                        device_id=determinant_row.device_id,
                        bill_determinant_id=determinant_row.id,
                        charge_type=charge_type,
                        billing_period_start_at=determinant_row.billing_period_start_at,
                        billing_period_end_at=determinant_row.billing_period_end_at,
                        currency_code=payload["currency_code"],
                        tariff_plan_code=payload["tariff_plan_code"],
                        tariff_version_code=payload["tariff_version_code"],
                        quantity_value=payload["quantity_value"],
                        unit_rate_value=payload["unit_rate_value"],
                        charge_amount=payload["charge_amount"],
                        calculation_status=str(payload["calculation_status"]),
                        quality_summary=str(payload["quality_summary"]),
                        revision_number=1,
                        revision_reason_code=revision_reason_code,
                        is_current=True,
                        supersedes_bill_charge_id=None,
                        calculated_at=calculated_at,
                        details=dict(payload["details"]),
                    )
                )
                created += 1
            elif _same_snapshot(current_row, determinant_row=determinant_row, payload=payload):
                reused += 1
            else:
                current_row.is_current = False
                current_row.revision_reason_code = revision_reason_code or "re_charged"
                session.add(
                    BillCharge(
                        pipeline_run_id=pipeline_run.id,
                        service_point_id=determinant_row.service_point_id,
                        measuring_component_id=determinant_row.measuring_component_id,
                        device_id=determinant_row.device_id,
                        bill_determinant_id=determinant_row.id,
                        charge_type=charge_type,
                        billing_period_start_at=determinant_row.billing_period_start_at,
                        billing_period_end_at=determinant_row.billing_period_end_at,
                        currency_code=payload["currency_code"],
                        tariff_plan_code=payload["tariff_plan_code"],
                        tariff_version_code=payload["tariff_version_code"],
                        quantity_value=payload["quantity_value"],
                        unit_rate_value=payload["unit_rate_value"],
                        charge_amount=payload["charge_amount"],
                        calculation_status=str(payload["calculation_status"]),
                        quality_summary=str(payload["quality_summary"]),
                        revision_number=current_row.revision_number + 1,
                        revision_reason_code=revision_reason_code or "re_charged",
                        is_current=True,
                        supersedes_bill_charge_id=current_row.id,
                        calculated_at=calculated_at,
                        details=dict(payload["details"]),
                    )
                )
                superseded += 1

            latest_billing_period_end_at = (
                determinant_row.billing_period_end_at
                if latest_billing_period_end_at is None
                or determinant_row.billing_period_end_at > latest_billing_period_end_at
                else latest_billing_period_end_at
            )

        session.flush()

        summary = BillChargeCalculationSummary(
            charge_type=charge_type,
            groups=len(determinant_rows),
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
            "source_bill_determinant_count": len(determinant_rows),
        }
        if latest_billing_period_end_at is not None:
            upsert_processing_watermark(
                session,
                pipeline_name="bill_charge",
                source_system=None,
                record_type=_CHARGE_WATERMARK_RECORD_TYPE[charge_type],
                last_processed_at=latest_billing_period_end_at,
                details=details,
            )

        if summary.groups == 0:
            result_code = "bill_charge_noop"
        elif summary.blocked > 0:
            result_code = "bill_charge_completed_with_blocked"
        elif summary.partial > 0:
            result_code = "bill_charge_completed_with_partial"
        else:
            result_code = "bill_charge_completed"
        complete_pipeline_run(
            pipeline_run,
            result_code=result_code,
            details=details,
        )
        return summary
    except Exception:
        fail_pipeline_run(
            pipeline_run,
            result_code="bill_charge_failed_exception",
            details={
                **pipeline_run.details,
                "source_bill_determinant_count": len(determinant_rows),
            },
        )
        raise
