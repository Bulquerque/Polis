"""S1: native P4 V14.9 boundary, view materialization and research lineage."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..boundary.p4_v149 import P4BoundaryCatalog, build_boundary_catalog, materialize_consumer_views
from ..domain.core import HandlerOutcome, ModuleStatus
from ..domain.feedback import PriorCycleFeedbackReport
from ..errors import ContractError, DataQualityError
from ..services.identifiers import stable_id
from pydantic import ValidationError
from ..services.p4_boundary import (
    build_consumption_receipt,
    normalize_conflicts,
    normalize_passports,
    plain_records,
)
from ..services.tabular import assert_no_forbidden_fields, normalize_view_bundle

_MANDATORY_VIEWS = {"TABULAR_INTERPRETABLE"}
_SUPPORTED_VIEWS = {
    "TABULAR_INTERPRETABLE", "CROSS_SECTIONAL_RANKED", "SEQUENCE_MULTI_HORIZON",
    "GRAPH_RELATIONAL", "TAIL_RISK_SPECIALIST", "REGIME_CONTEXT", "LATENT_FAMILY",
    "SPARSE_MODALITY_AWARE",
}


def m01(
    payload: dict[str, Any],
    *,
    context_as_of_time: datetime,
    context_generated_at: datetime,
    expected_cycle_id: str,
    expected_run_id: str | None = None,
) -> HandlerOutcome:
    catalog = build_boundary_catalog(
        handoff=_mapping(payload, "phase5_feature_handoff_manifest"),
        view_manifest=_mapping(payload, "model_consumer_view_manifest"),
        view_bundle=_mapping(payload, "model_consumer_view_bundle"),
        quality_gate=_mapping(payload, "p4_quality_gate_decision"),
        artifact_catalog=_mapping(payload, "p4_artifact_catalog"),
        expected_cycle_id=expected_cycle_id,
        p5_as_of_time=context_as_of_time,
        p5_generated_at=context_generated_at,
        expected_run_id=expected_run_id,
    )
    assert_no_forbidden_fields(
        catalog.artifacts["feature_lineage_report"].model_dump(mode="json"),
        path="feature_lineage_report",
    )
    bundle = {
        "p4_contract_version": catalog.handoff.schema_version,
        "run_id": catalog.handoff.run_id,
        "cycle_id": catalog.handoff.cycle_id,
        "as_of_time": catalog.handoff.as_of_time.isoformat(),
        "created_at": catalog.handoff.created_at.isoformat(),
        "lineage_id": catalog.handoff.lineage_id,
        "handoff_manifest_id": catalog.handoff.artifact_id,
        "handoff_manifest_hash": catalog.handoff.content_hash,
        "gate_decision": catalog.gate_state.handoff_decision,
        "completeness_status": catalog.gate_state.completeness_status,
        "artifact_names": sorted(catalog.artifacts),
        "artifact_ids": sorted(a.artifact_id for a in catalog.artifacts.values()),
    }
    report = {
        "compatible": True,
        "native_p4_v149_boundary": True,
        "wire_payloads_copied": False,
        "handoff_decision": catalog.gate_state.handoff_decision,
        "completeness_status": catalog.gate_state.completeness_status,
        "blocked_families": list(catalog.gate_state.blocked_families),
        "degraded_families": list(catalog.gate_state.degraded_families),
        "catalog_artifact_count": len(catalog.artifacts),
    }
    status = ModuleStatus.DEGRADED if catalog.gate_state.degraded else ModuleStatus.SUCCESS
    warnings = (
        (f"P4 handoff accepted with degradation: {catalog.gate_state.handoff_decision}",)
        if status is ModuleStatus.DEGRADED else ()
    )
    return HandlerOutcome(
        values=(bundle, report, catalog.model_dump(mode="json")), status=status, warnings=warnings
    )


def m02(payload: dict[str, Any]) -> HandlerOutcome:
    _mapping(payload, "validated_p4_contract_bundle")
    catalog = P4BoundaryCatalog.model_validate(_mapping(payload, "validated_p4_artifact_catalog"))
    views, compatibility_rows = materialize_consumer_views(catalog)
    normalized = normalize_view_bundle({"views": views})
    missing_mandatory = sorted(_MANDATORY_VIEWS - set(normalized))
    if missing_mandatory:
        raise ContractError(f"mandatory P4 views unavailable: {missing_mandatory}")
    unsupported = sorted(set(normalized) - _SUPPORTED_VIEWS)
    if unsupported:
        raise ContractError(f"unsupported P4 views materialized: {unsupported}")
    unavailable = sorted(
        row["view_id"] for row in compatibility_rows if not row["authorized"]
    )
    registry = {"views": [normalized[key] for key in sorted(normalized)]}
    compatibility = {"records": compatibility_rows}
    degraded = {
        "degraded": catalog.gate_state.degraded or bool(unavailable),
        "blocking": False,
        "p4_gate_decision": catalog.gate_state.handoff_decision,
        "completeness_status": catalog.gate_state.completeness_status,
        "unavailable_views": unavailable,
        "blocked_families": list(catalog.gate_state.blocked_families),
        "interpretable_path_available": "TABULAR_INTERPRETABLE" in normalized,
        "encoder_optional": True,
        "latent_view_available": "LATENT_FAMILY" in normalized,
        "native_projection": True,
    }
    status = ModuleStatus.DEGRADED if degraded["degraded"] else ModuleStatus.SUCCESS
    warnings = (f"P4 capabilities unavailable/degraded: {unavailable}",) if status is ModuleStatus.DEGRADED else ()
    return HandlerOutcome(values=(registry, compatibility, degraded), status=status, warnings=warnings)


def m03(payload: dict[str, Any]) -> HandlerOutcome:
    passport_records, lineage = normalize_passports(
        payload.get("approved_hypothesis_passport_registry"),
        payload.get("hypothesis_budget_report"),
        payload.get("research_attempt_ledger"),
    )
    rejected = plain_records(payload.get("rejected_feature_graveyard"), "rejected_feature_graveyard")
    observers = plain_records(payload.get("feature_observer_registry"), "feature_observer_registry")
    conflicts = normalize_conflicts(payload.get("perspective_conflict_panel"))
    lineage.update({
        "rejected_count": len(rejected),
        "observer_count": len(observers),
        "resolver_lineage": {},
    })
    passport_output = _records_output(passport_records, "P5_HYPOTHESIS_LINEAGE_NOT_SUPPLIED")
    conflict_output = _records_output(conflicts, "P5_PERSPECTIVE_CONFLICTS_NOT_SUPPLIED")
    lineage.setdefault(
        "availability",
        "AVAILABLE" if passport_records or rejected or observers or conflicts else "UNAVAILABLE",
    )
    lineage.setdefault(
        "status",
        "AVAILABLE" if lineage["availability"] == "AVAILABLE" else "UNAVAILABLE",
    )
    if lineage["availability"] == "UNAVAILABLE":
        lineage.setdefault("reason_code", "P5_RESEARCH_LINEAGE_NOT_SUPPLIED")
    status = ModuleStatus.SUCCESS if lineage["availability"] == "AVAILABLE" else ModuleStatus.DEGRADED
    warnings = () if status is ModuleStatus.SUCCESS else ("P4 research lineage was not supplied",)
    return HandlerOutcome(
        values=(passport_output, lineage, conflict_output), status=status, warnings=warnings
    )


def _records_output(records: list[dict[str, Any]], reason_code: str) -> dict[str, Any]:
    if records:
        return {"availability": "AVAILABLE", "status": "AVAILABLE", "records": records}
    return {
        "availability": "UNAVAILABLE",
        "status": "UNAVAILABLE",
        "reason_code": reason_code,
        "records": [],
    }


def m04(
    payload: dict[str, Any],
    *,
    current_cycle_id: str | None = None,
    current_as_of_time: datetime | None = None,
) -> HandlerOutcome:
    named_reports = _feedback_reports(payload)
    if not named_reports:
        return _empty_feedback_outcome()
    records: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name, raw_report in sorted(named_reports.items()):
        report = _validate_feedback_report(
            name, raw_report,
            current_cycle_id=current_cycle_id,
            current_as_of_time=current_as_of_time,
        )
        accepted = _accept_feedback_records(report, records=records, seen=seen)
        receipts.append(_feedback_receipt(name, report, accepted))
    return HandlerOutcome(values=(_feedback_output(records, receipts),))


def _feedback_reports(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    names = (
        "resolver_feedback_report",
        "signal_feedback_report",
        "resolver_promotion_decision_report",
    )
    return {name: payload[name] for name in names if isinstance(payload.get(name), dict)}


def _empty_feedback_outcome() -> HandlerOutcome:
    output = {
        "available": False,
        "status": "UNAVAILABLE",
        "records": [],
        "accepted_report_count": 0,
        "accepted_record_count": 0,
        "rejected_report_count": 0,
        "reason_codes": ["P5_PRIOR_CYCLE_FEEDBACK_NOT_SUPPLIED"],
    }
    return HandlerOutcome(
        values=(output,), status=ModuleStatus.DEGRADED,
        warnings=("no prior-cycle feedback was supplied",),
    )


def _validate_feedback_report(
    name: str,
    raw_report: dict[str, Any],
    *,
    current_cycle_id: str | None,
    current_as_of_time: datetime | None,
) -> PriorCycleFeedbackReport:
    try:
        report = PriorCycleFeedbackReport.model_validate(raw_report)
    except ValidationError as exc:
        details = exc.errors(include_url=False)[:5]
        raise DataQualityError(
            f"{name} violates the closed P9-P5 feedback contract: {details}"
        ) from exc
    if current_cycle_id and report.source_cycle_id == current_cycle_id:
        raise DataQualityError("feedback requires a distinct prior source_cycle_id")
    if current_as_of_time and report.available_at > current_as_of_time:
        raise DataQualityError("feedback was not available at the P5 decision time")
    return report


def _accept_feedback_records(
    report: PriorCycleFeedbackReport,
    *,
    records: list[dict[str, Any]],
    seen: set[str],
) -> int:
    accepted = 0
    for projected in report.projected_records():
        assert_no_forbidden_fields(projected, path="feedback")
        identifier = stable_id(projected)
        if identifier in seen:
            continue
        seen.add(identifier)
        records.append(projected)
        accepted += 1
    return accepted


def _feedback_receipt(
    name: str, report: PriorCycleFeedbackReport, accepted: int,
) -> dict[str, Any]:
    return {
        "input_name": name,
        "schema_version": report.schema_version,
        "source_run_id": report.source_run_id,
        "source_cycle_id": report.source_cycle_id,
        "promotion_decision_id": report.promotion_decision_id,
        "content_sha256": report.content_sha256,
        "accepted_record_count": accepted,
        "status": "ACCEPTED",
    }


def _feedback_output(
    records: list[dict[str, Any]], receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "available": True,
        "status": "AVAILABLE",
        "records": records,
        "report_receipts": receipts,
        "accepted_report_count": len(receipts),
        "accepted_record_count": len(records),
        "rejected_report_count": 0,
        "allowed_effect_types": [
            "CHALLENGER_ELIGIBILITY", "HYPERPARAMETER_BOUNDS", "RESEARCH_BUDGET",
            "APPROVED_THRESHOLDS", "MODEL_DEPRECATION",
        ],
    }


def m05(
    payload: dict[str, Any], *, run_id: str, cycle_id: str,
    as_of_time: datetime, created_at: datetime,
) -> HandlerOutcome:
    validated = _mapping(payload, "validated_p4_contract_bundle")
    registry = _mapping(payload, "authorized_consumer_view_registry")
    compatibility = _mapping(payload, "resolver_view_compatibility_matrix")
    degraded = _mapping(payload, "p4_degraded_mode_report")
    catalog = P4BoundaryCatalog.model_validate(_mapping(payload, "validated_p4_artifact_catalog"))
    view_ids = sorted(row["view_id"] for row in registry.get("views", []))
    compatibility_ids = sorted(
        row["view_id"] for row in compatibility.get("records", []) if row.get("authorized")
    )
    if view_ids != compatibility_ids:
        raise ContractError("view registry and compatibility matrix differ")
    receipt = build_consumption_receipt(
        catalog, run_id=run_id, cycle_id=cycle_id,
        as_of_time=as_of_time, created_at=created_at, view_registry=registry,
    )
    acknowledgement = {
        "receipt_id": receipt["artifact_id"],
        "accepted": not bool(degraded.get("blocking", False)),
        "p4_handoff_manifest_id": validated["handoff_manifest_id"],
        "p4_handoff_manifest_hash": validated["handoff_manifest_hash"],
        "consumed_views": view_ids,
        "wire_adaptations": [],
        "internal_projection": "P4_V14_9_TO_P5_CANONICAL_DOMAIN",
    }
    return HandlerOutcome(values=(receipt, acknowledgement))


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise DataQualityError(f"{name} must be an object")
    return value
