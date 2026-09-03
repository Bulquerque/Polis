from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope
from ...boundary.input_records import ComparableMetricRecord, FactorAdjustedMetricRecord
from ...boundary.output_records import MetricScoreComponent, ScoringHeadInputRecord, ScoringHeadRecord, ScoringPolicyReceiptRecord
from ...boundary.parsing import parse_artifact, require_inputs
from ...boundary.requests import ModuleExecutionConfig
from ...domain.artifact_validation import validate_common_identity
from ...domain.enums import AdjustmentStatus, HeadStatus, MetricSourcePreference, MissingMetricAction, SmallGroupAction
from ...domain.errors import ContractViolation, InternalInvariantViolation
from ...domain.transformations import normalize_value, transform_value
from .artifact_support import build_outputs, output_lineage, unique_by

MODULE_ID = "P7.S4.M02"
REQUIRED = (
    "scoring_head_input_panel",
    "factor_adjusted_metric_panel",
    "comparable_candidate_metric_panel",
    "scoring_policy_receipt",
)


@dataclass(frozen=True, slots=True)
class ScoringInputs:
    bindings: ArtifactEnvelope[ScoringHeadInputRecord]
    adjusted: ArtifactEnvelope[FactorAdjustedMetricRecord]
    comparable: ArtifactEnvelope[ComparableMetricRecord]
    receipt: ArtifactEnvelope[ScoringPolicyReceiptRecord]

    def artifacts(self) -> tuple[ArtifactEnvelope[Any], ...]:
        return (self.bindings, self.adjusted, self.comparable, self.receipt)


@dataclass(frozen=True, slots=True)
class ResolvedMetric:
    value: float | None
    source_kind: str
    reason_code: str | None


def _parse(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> ScoringInputs:
    require_inputs(inputs, REQUIRED, MODULE_ID)
    kwargs = {"module_id": MODULE_ID, "strict_hash_validation": config.strict_hash_validation}
    parsed = ScoringInputs(
        bindings=parse_artifact(inputs["scoring_head_input_panel"], ScoringHeadInputRecord, expected_name="scoring_head_input_panel", **kwargs),
        adjusted=parse_artifact(inputs["factor_adjusted_metric_panel"], FactorAdjustedMetricRecord, expected_name="factor_adjusted_metric_panel", **kwargs),
        comparable=parse_artifact(inputs["comparable_candidate_metric_panel"], ComparableMetricRecord, expected_name="comparable_candidate_metric_panel", **kwargs),
        receipt=parse_artifact(inputs["scoring_policy_receipt"], ScoringPolicyReceiptRecord, expected_name="scoring_policy_receipt", **kwargs),
    )
    validate_common_identity(parsed.artifacts(), module_id=MODULE_ID)
    if len(parsed.receipt.records) != 1:
        raise ContractViolation("P7_S4_RECEIPT_RECORD_COUNT_INVALID", "scoring receipt must contain one record", module_id=MODULE_ID)
    return parsed


def _metric_maps(parsed: ScoringInputs) -> tuple[dict[tuple[str, str], ComparableMetricRecord], dict[tuple[str, str], FactorAdjustedMetricRecord]]:
    comparable = unique_by(
        parsed.comparable.records,
        lambda row: (row.candidate_id, row.metric_id),
        code="P7_S4_DUPLICATE_COMPARABLE_METRIC",
        module_id=MODULE_ID,
    )
    adjusted = unique_by(
        parsed.adjusted.records,
        lambda row: (row.candidate_id, row.metric_id),
        code="P7_S4_DUPLICATE_FACTOR_METRIC",
        module_id=MODULE_ID,
    )
    return comparable, adjusted


def _resolve_metric(
    binding: ScoringHeadInputRecord,
    comparable: dict[tuple[str, str], ComparableMetricRecord],
    adjusted: dict[tuple[str, str], FactorAdjustedMetricRecord],
) -> ResolvedMetric:
    key = (binding.candidate_id, binding.metric_id)
    base = comparable.get(key)
    factor = adjusted.get(key)
    if binding.source_preference == MetricSourcePreference.COMPARABLE_ONLY:
        if base is not None and base.directed_value is not None and base.comparison_status == "AVAILABLE":
            return ResolvedMetric(base.directed_value, "COMPARABLE", None)
        return ResolvedMetric(None, "COMPARABLE", "P7_S4_COMPARABLE_METRIC_UNAVAILABLE")
    if factor is not None and factor.adjustment_status == AdjustmentStatus.ADJUSTED and factor.adjusted_directed_value is not None:
        return ResolvedMetric(factor.adjusted_directed_value, "FACTOR_ADJUSTED", None)
    if binding.source_preference == MetricSourcePreference.FACTOR_ADJUSTED_REQUIRED:
        return ResolvedMetric(None, "FACTOR_ADJUSTED", "P7_S4_FACTOR_ADJUSTED_METRIC_REQUIRED")
    if factor is not None and factor.directed_value is not None and factor.adjustment_status in {AdjustmentStatus.BYPASS, AdjustmentStatus.NOT_APPLICABLE}:
        return ResolvedMetric(factor.directed_value, "COMPARABLE", None)
    if base is not None and base.directed_value is not None and base.comparison_status == "AVAILABLE":
        return ResolvedMetric(base.directed_value, "COMPARABLE", None)
    return ResolvedMetric(None, "COMPARABLE", "P7_S4_METRIC_UNAVAILABLE")


def _binding_signature(binding: ScoringHeadInputRecord) -> tuple[Any, ...]:
    return (
        binding.comparison_group_id,
        binding.metric_id,
        binding.source_preference,
        binding.transformation,
        binding.normalization,
        binding.clip_lower,
        binding.clip_upper,
        binding.absolute_lower,
        binding.absolute_upper,
        binding.robust_scale,
    )


def _value_groups(
    bindings: tuple[ScoringHeadInputRecord, ...],
    comparable: dict[tuple[str, str], ComparableMetricRecord],
    adjusted: dict[tuple[str, str], FactorAdjustedMetricRecord],
) -> dict[tuple[Any, ...], tuple[float, ...]]:
    values: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    for binding in bindings:
        resolved = _resolve_metric(binding, comparable, adjusted)
        if resolved.value is None:
            continue
        transformed = transform_value(resolved.value, binding.transformation, binding.clip_lower, binding.clip_upper)
        values[_binding_signature(binding)].append(transformed)
    return {key: tuple(rows) for key, rows in values.items()}


def _missing_stage(binding: ScoringHeadInputRecord, reason: str) -> MetricScoreComponent:
    action = binding.missing_metric_action
    if action == MissingMetricAction.PENALIZE_HEAD:
        return MetricScoreComponent(
            metric_id=binding.metric_id,
            source_kind="MISSING_PENALTY",
            raw_directed_value=None,
            transformed_value=None,
            normalized_value=binding.missing_metric_penalty,
            metric_weight=binding.metric_weight,
            contribution=binding.missing_metric_penalty * binding.metric_weight,
            status="PENALIZED",
            reason_code=reason,
        )
    status = "RENORMALIZED" if action == MissingMetricAction.RENORMALIZE_METRICS else ("BLOCKED" if action == MissingMetricAction.BLOCK_HEAD else "UNAVAILABLE")
    return MetricScoreComponent(
        metric_id=binding.metric_id,
        source_kind="COMPARABLE",
        raw_directed_value=None,
        transformed_value=None,
        normalized_value=None,
        metric_weight=binding.metric_weight,
        contribution=0.0,
        status=status,
        reason_code=reason,
    )


def _score_stage(
    binding: ScoringHeadInputRecord,
    resolved: ResolvedMetric,
    group_values: tuple[float, ...],
) -> MetricScoreComponent:
    if resolved.value is None:
        return _missing_stage(binding, resolved.reason_code or "P7_S4_METRIC_UNAVAILABLE")
    transformed = transform_value(resolved.value, binding.transformation, binding.clip_lower, binding.clip_upper)
    if len(group_values) < binding.min_group_size:
        if binding.small_group_action == SmallGroupAction.BLOCK:
            return _missing_stage(binding, "P7_S4_SMALL_GROUP_BLOCKED")
        if binding.small_group_action == SmallGroupAction.UNAVAILABLE:
            return _missing_stage(binding, "P7_S4_SMALL_GROUP_UNAVAILABLE")
        normalized = normalize_value(
            transformed,
            group_values,
            method="ABSOLUTE_RANGE",
            absolute_lower=binding.absolute_lower,
            absolute_upper=binding.absolute_upper,
            robust_scale=binding.robust_scale,
        )
    else:
        normalized = normalize_value(
            transformed,
            group_values,
            method=binding.normalization,
            absolute_lower=binding.absolute_lower,
            absolute_upper=binding.absolute_upper,
            robust_scale=binding.robust_scale,
        )
    return MetricScoreComponent(
        metric_id=binding.metric_id,
        source_kind=resolved.source_kind,
        raw_directed_value=resolved.value,
        transformed_value=transformed,
        normalized_value=normalized,
        metric_weight=binding.metric_weight,
        contribution=normalized * binding.metric_weight,
        status="AVAILABLE",
        reason_code=None,
    )


def _head_record(bindings: tuple[ScoringHeadInputRecord, ...], stages: tuple[MetricScoreComponent, ...]) -> ScoringHeadRecord:
    first = bindings[0]
    statuses = {row.status for row in stages}
    if "BLOCKED" in statuses:
        head_status, score, reason = HeadStatus.BLOCKED, None, "P7_S4_HEAD_BLOCKED_REQUIRED_METRIC"
    elif "UNAVAILABLE" in statuses:
        head_status, score, reason = HeadStatus.UNAVAILABLE, None, "P7_S4_HEAD_UNAVAILABLE_METRIC"
    else:
        usable = tuple(row for row in stages if row.normalized_value is not None)
        weight = sum(row.metric_weight for row in usable)
        if weight <= 0.0:
            head_status, score, reason = HeadStatus.UNAVAILABLE, None, "P7_S4_HEAD_NO_USABLE_METRICS"
        else:
            score = sum(row.contribution for row in usable) / weight
            head_status = HeadStatus.PENALIZED if "PENALIZED" in statuses else (HeadStatus.RENORMALIZED if "RENORMALIZED" in statuses else HeadStatus.AVAILABLE)
            reason = None
    effective_weight = sum(row.metric_weight for row in stages if row.normalized_value is not None)
    return ScoringHeadRecord(
        candidate_id=first.candidate_id,
        comparison_group_id=first.comparison_group_id,
        policy_id=first.policy_id,
        policy_version=first.policy_version,
        rule_id=first.rule_id,
        head_id=first.head_id,
        head_weight=first.head_weight,
        missing_head_action=first.missing_head_action,
        missing_head_penalty=first.missing_head_penalty,
        head_status=head_status,
        head_score=score,
        effective_metric_weight=effective_weight,
        expected_metric_count=len(bindings),
        available_metric_count=sum(row.normalized_value is not None for row in stages),
        stages=stages,
        reason_code=reason,
        lineage_id=first.lineage_id,
    )


def calculate_multi_head_scores(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> dict[str, ArtifactEnvelope[Any]]:
    parsed = _parse(inputs, config)
    comparable, adjusted = _metric_maps(parsed)
    groups: dict[tuple[str, str], list[ScoringHeadInputRecord]] = defaultdict(list)
    for binding in parsed.bindings.records:
        groups[(binding.candidate_id, binding.head_id)].append(binding)
    value_groups = _value_groups(parsed.bindings.records, comparable, adjusted)
    records: list[ScoringHeadRecord] = []
    for key in sorted(groups):
        bindings = tuple(sorted(groups[key], key=lambda row: row.metric_id))
        stages = tuple(
            _score_stage(
                binding,
                _resolve_metric(binding, comparable, adjusted),
                value_groups.get(_binding_signature(binding), ()),
            )
            for binding in bindings
        )
        record = _head_record(bindings, stages)
        if record.head_score is not None and not 0.0 <= record.head_score <= 1.0:
            raise InternalInvariantViolation("P7_S4_HEAD_SCORE_OUT_OF_RANGE", "head score is outside [0,1]", module_id=MODULE_ID)
        records.append(record)
    lineage = output_lineage(MODULE_ID, parsed.artifacts())
    return build_outputs(
        module_id=MODULE_ID,
        base=parsed.bindings,
        execution_time=config.execution_time,
        lineage_id=lineage,
        named_records={"scoring_head_panel": tuple(sorted(records, key=lambda row: (row.comparison_group_id, row.candidate_id, row.head_id)))},
    )
