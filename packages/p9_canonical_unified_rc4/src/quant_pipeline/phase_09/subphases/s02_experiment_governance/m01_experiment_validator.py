from __future__ import annotations

from quant_pipeline.phase_09.contracts.integrity import payload_sha256

from .contracts.base import CapabilityState, ExperimentValidationState
from .contracts.experiment import (
    ExperimentValidationInput,
    ExperimentValidationOutcome,
    ExperimentValidationReport,
    ValidatedExperimentSpecification,
)


class ExperimentSpecificationValidator:
    """Validates an experiment before any search-space or trial construction."""

    def validate(self, request: ExperimentValidationInput) -> ExperimentValidationOutcome:
        spec = request.specification
        reasons: list[str] = []
        limitations: list[str] = []

        if set(spec.development_dataset_ids) & set(spec.evaluation_dataset_ids):
            reasons.append("P9_S2_SPEC_DEVELOPMENT_EVALUATION_OVERLAP")
        if set(spec.development_dataset_ids) & set(spec.final_holdout_dataset_ids):
            reasons.append("P9_S2_SPEC_HOLDOUT_LEAKAGE")
        if set(spec.evaluation_dataset_ids) & set(spec.final_holdout_dataset_ids):
            reasons.append("P9_S2_SPEC_HOLDOUT_LEAKAGE")
        if spec.temporal_evaluation.final_holdout_required and not spec.final_holdout_dataset_ids:
            reasons.append("P9_S2_SPEC_FINAL_HOLDOUT_MISSING")
        if not request.promotion_policy.hard_guardrails_non_compensable:
            reasons.append("P9_S2_SPEC_HARD_GUARDRAILS_COMPENSABLE")

        metric_ids = (
            (spec.primary_metric_id,)
            + spec.hard_guardrail_metric_ids
            + spec.diagnostic_metric_ids
        )
        for metric_id in metric_ids:
            metric = request.metric_registry.metric(metric_id)
            if metric is None:
                reasons.append("P9_S2_SPEC_METRIC_UNKNOWN")
                continue
            if metric_id == spec.primary_metric_id and not metric.allowed_for_tuning:
                reasons.append("P9_S2_SPEC_PRIMARY_METRIC_NOT_TUNABLE")
            if metric_id in spec.hard_guardrail_metric_ids and not metric.hard_guardrail_eligible:
                reasons.append("P9_S2_SPEC_GUARDRAIL_NOT_ELIGIBLE")

        for target_module_id in spec.target_module_ids:
            phase = target_module_id.split(".", 1)[0]
            if phase not in {"P5", "P6", "P7", "P8"}:
                reasons.append("P9_S2_SPEC_TARGET_UNKNOWN")

        unavailable_capability = False
        limited_capability = False
        for capability_id in spec.required_capability_ids:
            capability = request.capability_registry.capability(capability_id)
            if capability is None:
                reasons.append("P9_S2_SPEC_CAPABILITY_UNKNOWN")
                unavailable_capability = True
                continue
            if capability.owner_module_id not in spec.target_module_ids:
                reasons.append("P9_S2_SPEC_CAPABILITY_OWNER_NOT_TARGETED")
            if capability.supported_strategy_ids:
                if spec.search_strategy not in capability.supported_strategy_ids:
                    reasons.append("P9_S2_SPEC_SEARCH_STRATEGY_UNSUPPORTED")
            if capability.state in {CapabilityState.UNAVAILABLE, CapabilityState.RESERVED}:
                reasons.append("P9_S2_SPEC_CAPABILITY_UNAVAILABLE")
                unavailable_capability = True
            elif capability.state is CapabilityState.LIMITED:
                limited_capability = True
                if capability.limitation is not None:
                    limitations.append(capability.limitation)

        if spec.search_strategy.value == "BOHB":
            reasons.append("P9_S2_SPEC_BOHB_CAPABILITY_RESERVED")
            unavailable_capability = True

        unique_reasons = tuple(sorted(set(reasons)))
        unique_limitations = tuple(dict.fromkeys(limitations))
        if unavailable_capability:
            state = ExperimentValidationState.CAPABILITY_UNAVAILABLE
        elif any(reason.endswith("HOLDOUT_LEAKAGE") for reason in unique_reasons):
            state = ExperimentValidationState.HOLDOUT_POLICY_INVALID
        elif unique_reasons:
            state = ExperimentValidationState.SPEC_INVALID
        elif limited_capability:
            state = ExperimentValidationState.SPEC_VALID_WITH_LIMITATIONS
        else:
            state = ExperimentValidationState.SPEC_VALID

        report = ExperimentValidationReport(
            state=state,
            reason_codes=unique_reasons,
            limitations=unique_limitations,
            checked_metric_ids=tuple(metric_ids),
            checked_capability_ids=spec.required_capability_ids,
            checked_target_module_ids=spec.target_module_ids,
        )
        if state not in {
            ExperimentValidationState.SPEC_VALID,
            ExperimentValidationState.SPEC_VALID_WITH_LIMITATIONS,
        }:
            return ExperimentValidationOutcome(validated=None, report=report)

        validated = ValidatedExperimentSpecification(
            specification=spec,
            cohort_id=request.frozen_cohort.cohort_id,
            cohort_sha256=request.frozen_cohort.cohort_sha256,
            metric_registry_sha256=request.metric_registry.registry_sha256,
            capability_registry_sha256=request.capability_registry.registry_sha256,
            promotion_policy=request.promotion_policy,
            specification_sha256=payload_sha256(
                {
                    "specification": spec,
                    "cohort_id": request.frozen_cohort.cohort_id,
                    "cohort_sha256": request.frozen_cohort.cohort_sha256,
                    "metric_registry_sha256": request.metric_registry.registry_sha256,
                    "capability_registry_sha256": request.capability_registry.registry_sha256,
                    "promotion_policy": request.promotion_policy,
                }
            ),
        )
        return ExperimentValidationOutcome(validated=validated, report=report)
