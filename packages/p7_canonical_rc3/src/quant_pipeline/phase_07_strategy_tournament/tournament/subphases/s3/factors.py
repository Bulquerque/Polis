from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope
from ...boundary.parsing import parse_artifact, require_inputs
from ...boundary.records import (
    ComparableMetricRecord,
    EligibleCandidateRecord,
    FactorAdjustedMetricRecord,
    FactorAdjustmentAuditRecord,
    FactorExposureRecord,
    OptionFactorModelRecord,
    RankingPolicyRecord,
)
from ...boundary.requests import ModuleExecutionConfig
from ...domain.artifact_validation import validate_common_identity
from ...domain.enums import AdjustmentStatus, ComparisonStatus, Direction, FactorMode, ModelQualificationStatus
from ...domain.errors import ContractViolation, PolicyViolation, TemporalViolation
from .artifact_support import build_outputs, output_lineage, reason_counts, single_policy, unique_by

MODULE_ID = "P7.S3.M02"
REQUIRED_INPUTS = (
    "comparable_candidate_metric_panel",
    "eligible_strategy_candidate_panel",
    "ranking_policy_context",
)
OPTIONAL_MODEL = "option_factor_model_artifact"


@dataclass(frozen=True, slots=True)
class FactorInputs:
    metrics: ArtifactEnvelope[ComparableMetricRecord]
    candidates: ArtifactEnvelope[EligibleCandidateRecord]
    policy_artifact: ArtifactEnvelope[RankingPolicyRecord]
    model_artifact: ArtifactEnvelope[OptionFactorModelRecord] | None

    def artifacts(self) -> tuple[ArtifactEnvelope[Any], ...]:
        base: tuple[ArtifactEnvelope[Any], ...] = (self.metrics, self.candidates, self.policy_artifact)
        return (*base, self.model_artifact) if self.model_artifact else base


@dataclass(frozen=True, slots=True)
class FactorSpecification:
    intercept: float
    coefficients: dict[str, float]
    model_id: str | None


def _parse_inputs(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> FactorInputs:
    require_inputs(inputs, REQUIRED_INPUTS, MODULE_ID)
    metrics = parse_artifact(
        inputs[REQUIRED_INPUTS[0]], ComparableMetricRecord, expected_name=REQUIRED_INPUTS[0],
        module_id=MODULE_ID, strict_hash_validation=config.strict_hash_validation,
    )
    candidates = parse_artifact(
        inputs[REQUIRED_INPUTS[1]], EligibleCandidateRecord, expected_name=REQUIRED_INPUTS[1],
        module_id=MODULE_ID, strict_hash_validation=config.strict_hash_validation,
    )
    policy = parse_artifact(
        inputs[REQUIRED_INPUTS[2]], RankingPolicyRecord, expected_name=REQUIRED_INPUTS[2],
        module_id=MODULE_ID, strict_hash_validation=config.strict_hash_validation,
    )
    model = None
    if OPTIONAL_MODEL in inputs:
        model = parse_artifact(
            inputs[OPTIONAL_MODEL], OptionFactorModelRecord, expected_name=OPTIONAL_MODEL,
            module_id=MODULE_ID, strict_hash_validation=config.strict_hash_validation,
        )
    parsed = FactorInputs(metrics, candidates, policy, model)
    validate_common_identity(parsed.artifacts(), module_id=MODULE_ID)
    return parsed


def _qualified_model_specification(
    parsed: FactorInputs,
    policy: RankingPolicyRecord,
) -> FactorSpecification:
    if parsed.model_artifact is None:
        raise ContractViolation(
            "P7_S3_FACTOR_MODEL_MISSING", "qualified residual mode requires a model", module_id=MODULE_ID
        )
    if len(parsed.model_artifact.records) != 1:
        raise ContractViolation(
            "P7_S3_FACTOR_MODEL_RECORD_COUNT_INVALID", "factor model must contain one record", module_id=MODULE_ID
        )
    model = parsed.model_artifact.records[0]
    factor_policy = policy.factor_adjustment
    if model.training_cutoff_at > parsed.model_artifact.decision_time:
        raise TemporalViolation(
            "P7_S3_FACTOR_MODEL_FUTURE_CUTOFF", "factor model cutoff is after decision time",
            module_id=MODULE_ID, details={"model_id": model.model_id},
        )
    if model.qualification_status != ModelQualificationStatus.QUALIFIED:
        raise PolicyViolation(
            "P7_S3_FACTOR_MODEL_NOT_QUALIFIED", "factor model is not qualified",
            module_id=MODULE_ID, details={"model_id": model.model_id},
        )
    if model.factor_schema_version != factor_policy.factor_schema_version:
        raise ContractViolation(
            "P7_S3_FACTOR_SCHEMA_MISMATCH", "factor schema differs from policy", module_id=MODULE_ID
        )
    if model.target_metric_id != factor_policy.target_metric_id:
        raise ContractViolation(
            "P7_S3_FACTOR_TARGET_MISMATCH", "factor target differs from policy", module_id=MODULE_ID
        )
    if set(model.coefficients) != set(factor_policy.factor_ids):
        raise ContractViolation(
            "P7_S3_FACTOR_SET_MISMATCH", "factor coefficients differ from policy", module_id=MODULE_ID
        )
    return FactorSpecification(model.intercept, dict(model.coefficients), model.model_id)


def _resolve_specification(parsed: FactorInputs, policy: RankingPolicyRecord) -> FactorSpecification:
    factor_policy = policy.factor_adjustment
    if factor_policy.mode == FactorMode.BYPASS:
        return FactorSpecification(0.0, {}, None)
    if factor_policy.mode == FactorMode.STATIC_PREMIA:
        if set(factor_policy.static_coefficients) != set(factor_policy.factor_ids):
            raise PolicyViolation(
                "P7_S3_STATIC_FACTOR_SET_MISMATCH", "static coefficients differ from factor set", module_id=MODULE_ID
            )
        return FactorSpecification(
            factor_policy.static_intercept,
            dict(factor_policy.static_coefficients),
            f"static:{policy.policy_id}",
        )
    return _qualified_model_specification(parsed, policy)


def _passthrough_metric(metric: ComparableMetricRecord) -> FactorAdjustedMetricRecord:
    return FactorAdjustedMetricRecord(
        candidate_id=metric.candidate_id,
        comparison_group_id=metric.comparison_group_id,
        metric_id=metric.metric_id,
        raw_value=metric.canonical_value,
        directed_value=metric.directed_value,
        adjusted_raw_value=metric.canonical_value,
        adjusted_directed_value=metric.directed_value,
        adjustment_status=AdjustmentStatus.NOT_APPLICABLE,
        adjustment_model_id=None,
        total_factor_contribution=None,
        intercept=None,
        reason_code=metric.reason_code,
        lineage_id=metric.lineage_id,
    )


def _unavailable_target(metric: ComparableMetricRecord, model_id: str | None) -> FactorAdjustedMetricRecord:
    status = AdjustmentStatus.BLOCKED if metric.comparison_status == ComparisonStatus.BLOCKED else AdjustmentStatus.UNAVAILABLE
    return FactorAdjustedMetricRecord(
        candidate_id=metric.candidate_id,
        comparison_group_id=metric.comparison_group_id,
        metric_id=metric.metric_id,
        raw_value=metric.canonical_value,
        directed_value=metric.directed_value,
        adjusted_raw_value=None,
        adjusted_directed_value=None,
        adjustment_status=status,
        adjustment_model_id=model_id,
        total_factor_contribution=None,
        intercept=None,
        reason_code=metric.reason_code or "P7_S3_FACTOR_TARGET_UNAVAILABLE",
        lineage_id=metric.lineage_id,
    )


def _missing_exposure_target(
    metric: ComparableMetricRecord,
    action: str,
    spec: FactorSpecification,
) -> FactorAdjustedMetricRecord:
    mapping = {
        "BYPASS_TARGET": (
            AdjustmentStatus.BYPASS,
            metric.canonical_value,
            metric.directed_value,
            "P7_S3_FACTOR_EXPOSURE_BYPASS",
        ),
        "BLOCK": (AdjustmentStatus.BLOCKED, None, None, "P7_S3_FACTOR_EXPOSURE_REQUIRED"),
        "UNAVAILABLE": (AdjustmentStatus.UNAVAILABLE, None, None, "P7_S3_FACTOR_EXPOSURE_UNAVAILABLE"),
    }
    status, raw, directed, reason = mapping[action]
    return FactorAdjustedMetricRecord(
        candidate_id=metric.candidate_id,
        comparison_group_id=metric.comparison_group_id,
        metric_id=metric.metric_id,
        raw_value=metric.canonical_value,
        directed_value=metric.directed_value,
        adjusted_raw_value=raw,
        adjusted_directed_value=directed,
        adjustment_status=status,
        adjustment_model_id=spec.model_id,
        total_factor_contribution=None,
        intercept=spec.intercept,
        reason_code=reason,
        lineage_id=metric.lineage_id,
    )


def _adjust_target(
    metric: ComparableMetricRecord,
    candidate: EligibleCandidateRecord,
    policy: RankingPolicyRecord,
    spec: FactorSpecification,
) -> tuple[FactorAdjustedMetricRecord, tuple[FactorExposureRecord, ...], float]:
    factor_policy = policy.factor_adjustment
    missing = set(factor_policy.factor_ids) - set(candidate.factor_values)
    if missing:
        return _missing_exposure_target(metric, factor_policy.missing_exposure_action, spec), (), 0.0
    exposures: list[FactorExposureRecord] = []
    contributions: list[float] = []
    for factor_id in factor_policy.factor_ids:
        exposure = candidate.factor_values[factor_id]
        coefficient = spec.coefficients[factor_id]
        contribution = exposure * coefficient
        contributions.append(contribution)
        exposures.append(
            FactorExposureRecord(
                candidate_id=metric.candidate_id,
                comparison_group_id=metric.comparison_group_id,
                factor_id=factor_id,
                exposure_value=exposure,
                coefficient=coefficient,
                contribution=contribution,
                model_id=spec.model_id or "unavailable",
                factor_schema_version=factor_policy.factor_schema_version,
                lineage_id=metric.lineage_id,
            )
        )
    predicted = spec.intercept + sum(contributions)
    adjusted_raw = metric.canonical_value - predicted  # type: ignore[operator]
    direction = next(row.direction for row in policy.metric_policies if row.metric_id == metric.metric_id)
    adjusted_directed = adjusted_raw if direction == Direction.MAXIMIZE else -adjusted_raw
    record = FactorAdjustedMetricRecord(
        candidate_id=metric.candidate_id,
        comparison_group_id=metric.comparison_group_id,
        metric_id=metric.metric_id,
        raw_value=metric.canonical_value,
        directed_value=metric.directed_value,
        adjusted_raw_value=adjusted_raw,
        adjusted_directed_value=adjusted_directed,
        adjustment_status=AdjustmentStatus.ADJUSTED,
        adjustment_model_id=spec.model_id,
        total_factor_contribution=sum(contributions),
        intercept=spec.intercept,
        reason_code=None,
        lineage_id=metric.lineage_id,
    )
    error = abs(metric.canonical_value - adjusted_raw - predicted)  # type: ignore[operator]
    return record, tuple(exposures), error


def _process_target(
    metric: ComparableMetricRecord,
    candidate: EligibleCandidateRecord,
    policy: RankingPolicyRecord,
    spec: FactorSpecification,
) -> tuple[FactorAdjustedMetricRecord, tuple[FactorExposureRecord, ...], float]:
    if metric.comparison_status != ComparisonStatus.AVAILABLE or metric.canonical_value is None:
        return _unavailable_target(metric, spec.model_id), (), 0.0
    if policy.factor_adjustment.mode == FactorMode.BYPASS:
        record = _missing_exposure_target(metric, "BYPASS_TARGET", spec)
        return record, (), 0.0
    return _adjust_target(metric, candidate, policy, spec)


def adjust_factor_exposure(
    inputs: Mapping[str, Any],
    config: ModuleExecutionConfig,
) -> dict[str, ArtifactEnvelope[Any]]:
    parsed = _parse_inputs(inputs, config)
    policy = single_policy(parsed.policy_artifact, module_id=MODULE_ID)
    spec = _resolve_specification(parsed, policy)
    candidates = unique_by(
        parsed.candidates.records, lambda row: row.candidate_id,
        code="P7_S3_DUPLICATE_CANDIDATE", module_id=MODULE_ID,
    )
    metrics = unique_by(
        parsed.metrics.records, lambda row: (row.candidate_id, row.metric_id),
        code="P7_S3_DUPLICATE_COMPARABLE_METRIC", module_id=MODULE_ID,
    )
    adjusted: list[FactorAdjustedMetricRecord] = []
    exposures: list[FactorExposureRecord] = []
    errors: list[float] = []
    for key in sorted(metrics):
        metric = metrics[key]
        if metric.metric_id != policy.factor_adjustment.target_metric_id:
            adjusted.append(_passthrough_metric(metric))
            continue
        record, exposure_rows, error = _process_target(metric, candidates[metric.candidate_id], policy, spec)
        adjusted.append(record)
        exposures.extend(exposure_rows)
        errors.append(error)
    ordered = tuple(sorted(adjusted, key=lambda row: (row.comparison_group_id, row.candidate_id, row.metric_id)))
    audit = FactorAdjustmentAuditRecord(
        policy_id=policy.policy_id,
        mode=policy.factor_adjustment.mode,
        model_id=spec.model_id,
        model_status="QUALIFIED" if policy.factor_adjustment.mode == FactorMode.QUALIFIED_RESIDUAL else policy.factor_adjustment.mode.value,
        target_metric_id=policy.factor_adjustment.target_metric_id,
        adjusted_candidate_count=sum(row.adjustment_status == AdjustmentStatus.ADJUSTED for row in ordered),
        bypassed_candidate_count=sum(row.adjustment_status == AdjustmentStatus.BYPASS for row in ordered),
        unavailable_candidate_count=sum(row.adjustment_status == AdjustmentStatus.UNAVAILABLE for row in ordered),
        blocked_candidate_count=sum(row.adjustment_status == AdjustmentStatus.BLOCKED for row in ordered),
        conservation_max_abs_error=max(errors, default=0.0),
        reason_counts=reason_counts(row.reason_code for row in ordered),
    )
    return build_outputs(
        module_id=MODULE_ID,
        base=parsed.metrics,
        execution_time=config.execution_time,
        lineage_id=output_lineage(MODULE_ID, parsed.artifacts()),
        named_records={
            "factor_exposure_panel": tuple(sorted(exposures, key=lambda row: (row.comparison_group_id, row.candidate_id, row.factor_id))),
            "factor_adjusted_metric_panel": ordered,
            "factor_adjustment_audit_report": (audit,),
        },
    )
