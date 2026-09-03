"""Materialize P9 future-cycle feedback for the modern P5 and P7 consumers.

The materializers are deliberately narrow. They never activate a target policy,
never emit same-cycle feedback, and require an explicit P0 authorization receipt
for every package whose activation gate marked it as pending P0.
"""
from __future__ import annotations

from datetime import datetime
from importlib import import_module
from typing import Any

from pydantic import Field, model_validator

from .errors import ContractMismatchError
from .models import CompatibilityReceipt, CompatibilityState
from quant_pipeline.phase_09.subphases.s09_competition_promotion.enums import (
    FeedbackEffectType,
    FeedbackPhase,
    FeedbackValidationState,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models.common import (
    StrictModel,
)
from quant_pipeline.phase_09.subphases.s09_competition_promotion.models.feedback import (
    FeedbackPackage,
    ValidatedNextCycleFeedbackManifest,
)


class P0FeedbackAuthorization(StrictModel):
    authorization_id: str = Field(min_length=1)
    authorized_feedback_ids: tuple[str, ...]
    authorized_at: datetime
    authorizer: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self) -> "P0FeedbackAuthorization":
        if len(self.authorized_feedback_ids) != len(set(self.authorized_feedback_ids)):
            raise ValueError("authorized feedback IDs must be unique")
        return self


class ModernFeedbackMaterialization(StrictModel):
    target_phase: str
    report: dict[str, Any]
    manifest: dict[str, Any] | None = None
    receipt: CompatibilityReceipt


def _decision_map(manifest: ValidatedNextCycleFeedbackManifest):
    return {item.feedback_id: item for item in manifest.decisions}


def _authorized_packages(
    manifest: ValidatedNextCycleFeedbackManifest,
    target_phase: FeedbackPhase,
    authorization: P0FeedbackAuthorization | None,
) -> tuple[FeedbackPackage, ...]:
    decisions = _decision_map(manifest)
    authorized = set(() if authorization is None else authorization.authorized_feedback_ids)
    selected: list[FeedbackPackage] = []
    for package in manifest.accepted:
        if package.target_phase is not target_phase:
            continue
        decision = decisions[package.feedback_id]
        if decision.state is FeedbackValidationState.VALIDATED_PENDING_P0:
            if package.feedback_id not in authorized:
                raise ContractMismatchError(
                    f"P0 authorization missing for feedback {package.feedback_id}"
                )
        elif decision.state is not FeedbackValidationState.VALIDATED_FOR_FUTURE_CYCLE:
            raise ContractMismatchError(
                f"feedback {package.feedback_id} is not approved for future materialization"
            )
        selected.append(package)
    unknown = authorized - {item.feedback_id for item in manifest.accepted}
    if unknown:
        raise ContractMismatchError(f"P0 authorization references unknown feedback IDs: {sorted(unknown)}")
    return tuple(sorted(selected, key=lambda item: item.feedback_id))


def _exact_numeric(bound) -> float:
    if bound.minimum is None or bound.maximum is None or bound.minimum != bound.maximum:
        raise ContractMismatchError(
            f"feedback parameter {bound.parameter_name} requires an exact numeric value"
        )
    return float(bound.minimum)


def _single_categorical(package: FeedbackPackage) -> tuple[str, str]:
    if len(package.categorical_change_bounds) != 1:
        raise ContractMismatchError(
            f"feedback {package.feedback_id} requires one categorical bound"
        )
    bound = package.categorical_change_bounds[0]
    if len(bound.allowed_values) != 1:
        raise ContractMismatchError(
            f"feedback {package.feedback_id} requires one selected categorical value"
        )
    return bound.parameter_name, bound.allowed_values[0]


def _p5_records(package: FeedbackPackage) -> list[dict[str, Any]]:
    common = {
        "resolver_id": package.target_policy_id,
        "target_id": package.target_policy_id,
        "reason_code": package.reason_codes[0] if package.reason_codes else "P9_MODERN_FEEDBACK",
        "lineage_id": package.evidence_refs[0].artifact_ref.payload_sha256,
    }
    records: list[dict[str, Any]] = []
    if package.effect_type is FeedbackEffectType.POLICY_BOUND_CHANGE:
        for index, bound in enumerate(package.numeric_change_bounds):
            if bound.minimum is None or bound.maximum is None:
                raise ContractMismatchError("P5 hyperparameter bounds require minimum and maximum")
            records.append({
                "feedback_id": f"{package.feedback_id}:bound:{index}",
                "effect_type": "HYPERPARAMETER_BOUNDS",
                "effect_payload": {
                    "parameter": bound.parameter_name,
                    "minimum": float(bound.minimum),
                    "maximum": float(bound.maximum),
                },
                **common,
            })
    elif package.effect_type is FeedbackEffectType.ELIGIBILITY_REVIEW:
        _, value = _single_categorical(package)
        normalized = value.upper()
        if normalized not in {"ELIGIBLE", "INELIGIBLE", "TRUE", "FALSE", "ENABLED", "DISABLED"}:
            raise ContractMismatchError("P5 eligibility feedback uses an unsupported categorical value")
        records.append({
            "feedback_id": package.feedback_id,
            "effect_type": "CHALLENGER_ELIGIBILITY",
            "effect_payload": {"eligible": normalized in {"ELIGIBLE", "TRUE", "ENABLED"}},
            **common,
        })
    elif package.effect_type is FeedbackEffectType.CALIBRATION_REVIEW:
        if len(package.numeric_change_bounds) != 1:
            raise ContractMismatchError("P5 calibration feedback requires one exact threshold")
        bound = package.numeric_change_bounds[0]
        value = _exact_numeric(bound)
        records.append({
            "feedback_id": package.feedback_id,
            "effect_type": "APPROVED_THRESHOLDS",
            "effect_payload": {"threshold_name": bound.parameter_name, "value": value},
            **common,
        })
    elif package.effect_type is FeedbackEffectType.DEPRECATION_CANDIDATE:
        records.append({
            "feedback_id": package.feedback_id,
            "effect_type": "MODEL_DEPRECATION",
            "effect_payload": {"model_artifact_id": package.target_policy_id, "deprecated": True},
            **common,
        })
    elif package.effect_type is FeedbackEffectType.RESEARCH_REQUEST:
        values = {bound.parameter_name: bound.maximum for bound in package.numeric_change_bounds}
        attempts = values.get("maximum_attempts")
        seconds = values.get("maximum_compute_seconds")
        if attempts is None or seconds is None:
            raise ContractMismatchError(
                "P5 research requests require maximum_attempts and maximum_compute_seconds"
            )
        records.append({
            "feedback_id": package.feedback_id,
            "effect_type": "RESEARCH_BUDGET",
            "effect_payload": {
                "budget_name": package.target_policy_id,
                "maximum_attempts": int(attempts),
                "maximum_compute_seconds": float(seconds),
            },
            **common,
        })
    else:
        raise ContractMismatchError(
            f"P9 effect {package.effect_type} cannot be represented by P5-P9-FEEDBACK-V1"
        )
    return records


def materialize_modern_p5_feedback(
    *,
    validated_manifest: ValidatedNextCycleFeedbackManifest,
    source_run_id: str,
    promotion_decision_id: str,
    created_at: datetime,
    available_at: datetime,
    checked_at: datetime,
    authorization: P0FeedbackAuthorization | None = None,
) -> ModernFeedbackMaterialization:
    packages = _authorized_packages(validated_manifest, FeedbackPhase.P5, authorization)

    boundary_models = import_module(
        "quant_pipeline.phase_05_underlying_forecasts.boundary.models"
    )
    feedback_models = import_module(
        "quant_pipeline.phase_05_underlying_forecasts.domain.feedback"
    )
    canonical_sha256 = boundary_models.canonical_sha256
    PriorCycleFeedbackRecord = feedback_models.PriorCycleFeedbackRecord
    PriorCycleFeedbackReport = feedback_models.PriorCycleFeedbackReport
    records = tuple(
        PriorCycleFeedbackRecord.model_validate(record)
        for package in packages
        for record in _p5_records(package)
    )
    source_cycle_ids = {package.source_cycle.cycle_id for package in packages}
    if len(source_cycle_ids) != 1:
        raise ContractMismatchError("P5 feedback materialization requires one source cycle")
    payload = {
        "schema_version": "P9-P5-FEEDBACK-V1",
        "feedback_route": "NEXT_CYCLE_ONLY",
        "source_phase": "P9",
        "source_run_id": source_run_id,
        "source_cycle_id": next(iter(source_cycle_ids)),
        "promotion_status": "PROMOTED",
        "promotion_decision_id": promotion_decision_id,
        "created_at": created_at,
        "available_at": available_at,
        "records": records,
    }
    digest = canonical_sha256(
        PriorCycleFeedbackReport.model_construct(
            **payload, content_sha256="0" * 64
        ).model_dump(mode="json", exclude={"content_sha256"})
    )
    report = PriorCycleFeedbackReport.model_validate({**payload, "content_sha256": digest})
    wire = report.model_dump(mode="json")
    receipt = CompatibilityReceipt(
        phase_id="P5",
        package_name="quant-pipeline-p5-canonical",
        package_version="modern",
        contract_name="P9-P5-FEEDBACK-V1",
        contract_version="1.0.0",
        state=CompatibilityState.COMPATIBLE_GOVERNED,
        checked_at=checked_at,
        run_id=source_run_id,
        cycle_id=report.source_cycle_id,
        source_payload_sha256=digest,
        output_payload_sha256=digest,
        limitations=("future-cycle only; activation remains owned by P5/P0",),
    )
    return ModernFeedbackMaterialization(target_phase="P5", report=wire, receipt=receipt)


def _p7_adjustments(package: FeedbackPackage) -> tuple[dict[str, Any], ...]:
    adjustments: list[dict[str, Any]] = []
    if package.effect_type is FeedbackEffectType.POLICY_BOUND_CHANGE:
        for bound in package.numeric_change_bounds:
            adjustments.append({
                "adjustment_type": "POLICY_PARAMETER_BOUND",
                "parameter": bound.parameter_name,
                "value": {
                    "minimum": bound.minimum,
                    "maximum": bound.maximum,
                    "maximum_absolute_delta": bound.maximum_absolute_delta,
                },
            })
    elif package.effect_type is FeedbackEffectType.ELIGIBILITY_REVIEW:
        parameter, value = _single_categorical(package)
        adjustments.append({
            "adjustment_type": "MODEL_ELIGIBILITY",
            "parameter": parameter,
            "value": value,
        })
    elif package.effect_type is FeedbackEffectType.CALIBRATION_REVIEW:
        for bound in package.numeric_change_bounds:
            adjustments.append({
                "adjustment_type": "ELIGIBILITY_THRESHOLD",
                "parameter": bound.parameter_name,
                "value": _exact_numeric(bound),
            })
    elif package.effect_type is FeedbackEffectType.DEPRECATION_CANDIDATE:
        adjustments.append({
            "adjustment_type": "DEPRECATION_NOTICE",
            "parameter": package.target_policy_id,
            "value": True,
        })
    else:
        raise ContractMismatchError(
            f"P9 effect {package.effect_type} cannot be represented by modern P7 feedback"
        )
    if not adjustments:
        raise ContractMismatchError(f"P7 feedback {package.feedback_id} has no materializable adjustment")
    return tuple(adjustments)


def materialize_modern_p7_feedback(
    *,
    validated_manifest: ValidatedNextCycleFeedbackManifest,
    source_run_id: str,
    decision_time: datetime,
    created_at: datetime,
    checked_at: datetime,
    authorization: P0FeedbackAuthorization | None = None,
) -> ModernFeedbackMaterialization:
    packages = _authorized_packages(validated_manifest, FeedbackPhase.P7, authorization)

    canonical_module = import_module(
        "quant_pipeline.phase_07_strategy_tournament.foundation.canonical"
    )
    feedback_models = import_module(
        "quant_pipeline.phase_07_strategy_tournament.foundation.models"
    )
    content_sha256 = canonical_module.content_sha256
    ArtifactEnvelope = feedback_models.ArtifactEnvelope
    FeedbackManifest = feedback_models.FeedbackManifest
    FeedbackRecord = feedback_models.FeedbackRecord
    if not packages:
        raise ContractMismatchError("no modern P7 feedback is available for materialization")
    source_cycles = {(item.source_cycle.cycle_id, item.source_cycle.ordinal) for item in packages}
    target_cycles = {(item.target_cycle.cycle_id, item.target_cycle.ordinal) for item in packages}
    if len(source_cycles) != 1 or len(target_cycles) != 1:
        raise ContractMismatchError("P7 feedback materialization requires one source and target cycle")
    source_cycle_id, source_sequence = next(iter(source_cycles))
    target_cycle_id, target_sequence = next(iter(target_cycles))
    records = tuple(
        FeedbackRecord(
            feedback_id=package.feedback_id,
            source_cycle_id=source_cycle_id,
            source_cycle_sequence=source_sequence,
            target_cycle_id=target_cycle_id,
            target_cycle_sequence=target_sequence,
            promotion_status="PROMOTED",
            scope={
                "target_policy_id": package.target_policy_id,
                "target_policy_version": package.target_policy_version,
                "feedback_type": package.feedback_type,
            },
            evidence_ids=tuple(ref.evidence_id for ref in package.evidence_refs),
            valid_from_cycle_sequence=target_sequence,
            expires_at=None,
            adjustments=_p7_adjustments(package),
        )
        for package in packages
    )
    base = {
        "artifact_id": f"ranking_feedback_report:{source_run_id}:{target_cycle_id}",
        "artifact_name": "ranking_feedback_report",
        "schema_version": "2.0.0",
        "producer_phase": "P9",
        "producer_module_id": "P9.S9.M07",
        "destination_phase": "P7",
        "pipeline_version": "P9-MODERN-FEEDBACK-V1",
        "run_id": source_run_id,
        "cycle_id": target_cycle_id,
        "decision_time": decision_time,
        "available_at": created_at,
        "created_at": created_at,
        "record_count": len(records),
        "grain": "one_record_per_promoted_feedback_item",
        "lineage_id": f"p9-feedback:{source_cycle_id}:{target_cycle_id}",
        "capability_status": "AVAILABLE",
        "records": tuple(item.model_dump(mode="json") for item in records),
    }
    placeholder = ArtifactEnvelope.model_validate({**base, "content_sha256": "0" * 64})
    digest = content_sha256(placeholder.hash_payload())
    report = ArtifactEnvelope.model_validate({**base, "content_sha256": digest})
    manifest = FeedbackManifest(
        manifest_id=f"ranking-feedback-manifest:{source_run_id}:{target_cycle_id}",
        schema_version="2.0.0",
        producer_phase="P9",
        destination_phase="P7",
        source_cycle_id=source_cycle_id,
        source_cycle_sequence=source_sequence,
        target_cycle_id=target_cycle_id,
        target_cycle_sequence=target_sequence,
        promotion_status="PROMOTED",
        report_artifact_id=report.artifact_id,
        report_content_sha256=report.content_sha256,
        decision_time=decision_time,
        created_at=created_at,
    )
    receipt = CompatibilityReceipt(
        phase_id="P7",
        package_name="quant-pipeline-p7-strategy-tournament",
        package_version="modern",
        contract_name="P9-P7-FEEDBACK-V2",
        contract_version="2.0.0",
        state=CompatibilityState.COMPATIBLE_GOVERNED,
        checked_at=checked_at,
        run_id=source_run_id,
        cycle_id=target_cycle_id,
        source_payload_sha256=digest,
        output_payload_sha256=digest,
        limitations=("future-cycle only; activation remains owned by P7/P0",),
    )
    return ModernFeedbackMaterialization(
        target_phase="P7",
        report=report.model_dump(mode="json"),
        manifest=manifest.model_dump(mode="json"),
        receipt=receipt,
    )
