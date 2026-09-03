from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope
from ...boundary.input_records import ComparisonGroupRecord, ComparableMetricRecord, FactorAdjustedMetricRecord, ParetoFrontierRecord
from ...boundary.output_records import CandidatePolicyResolution, ScoringHeadInputRecord, ScoringPolicyReceiptRecord
from ...boundary.parsing import parse_artifact, require_inputs
from ...boundary.policy_records import ScoringPolicyContextRecord, ScoringPolicyRule
from ...boundary.requests import ModuleExecutionConfig
from ...domain.artifact_validation import validate_common_identity, validate_policy_time
from ...domain.enums import FrontierStatus
from ...domain.errors import ContractViolation, PolicyViolation, TemporalViolation
from ...domain.forbidden import scan_forbidden_fields
from ...domain.serialization import sha256_hex
from .artifact_support import build_outputs, output_lineage, unique_by

MODULE_ID = "P7.S4.M01"
REQUIRED = (
    "pareto_frontier_panel",
    "factor_adjusted_metric_panel",
    "comparable_candidate_metric_panel",
    "candidate_comparison_group_panel",
    "scoring_policy_context",
)


@dataclass(frozen=True, slots=True)
class BindingInputs:
    pareto: ArtifactEnvelope[ParetoFrontierRecord]
    adjusted: ArtifactEnvelope[FactorAdjustedMetricRecord]
    comparable: ArtifactEnvelope[ComparableMetricRecord]
    groups: ArtifactEnvelope[ComparisonGroupRecord]
    policy: ArtifactEnvelope[ScoringPolicyContextRecord]

    def artifacts(self) -> tuple[ArtifactEnvelope[Any], ...]:
        return (self.pareto, self.adjusted, self.comparable, self.groups, self.policy)


def _parse(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> BindingInputs:
    require_inputs(inputs, REQUIRED, MODULE_ID)
    kwargs = {"module_id": MODULE_ID, "strict_hash_validation": config.strict_hash_validation}
    parsed = BindingInputs(
        pareto=parse_artifact(inputs["pareto_frontier_panel"], ParetoFrontierRecord, expected_name="pareto_frontier_panel", **kwargs),
        adjusted=parse_artifact(inputs["factor_adjusted_metric_panel"], FactorAdjustedMetricRecord, expected_name="factor_adjusted_metric_panel", **kwargs),
        comparable=parse_artifact(inputs["comparable_candidate_metric_panel"], ComparableMetricRecord, expected_name="comparable_candidate_metric_panel", **kwargs),
        groups=parse_artifact(inputs["candidate_comparison_group_panel"], ComparisonGroupRecord, expected_name="candidate_comparison_group_panel", **kwargs),
        policy=parse_artifact(inputs["scoring_policy_context"], ScoringPolicyContextRecord, expected_name="scoring_policy_context", **kwargs),
    )
    validate_common_identity(parsed.artifacts(), module_id=MODULE_ID)
    validate_policy_time(parsed.policy, module_id=MODULE_ID)
    future_metrics = [row.candidate_id + ":" + row.metric_id for row in parsed.comparable.records if row.source_available_at > parsed.comparable.decision_time]
    if future_metrics:
        raise TemporalViolation(
            "P7_S4_METRIC_AVAILABLE_AFTER_DECISION",
            "metric source was not available at decision time",
            module_id=MODULE_ID,
            details={"metrics": sorted(future_metrics)},
        )
    if len(parsed.policy.records) != 1:
        raise ContractViolation("P7_S4_POLICY_RECORD_COUNT_INVALID", "scoring policy must contain one record", module_id=MODULE_ID)
    scan_forbidden_fields(inputs, set(parsed.policy.records[0].forbidden_field_names), module_id=MODULE_ID)
    return parsed


def _selector_match(value: str, selectors: tuple[str, ...]) -> bool:
    return "*" in selectors or value in selectors


def _specificity(rule: ScoringPolicyRule, policy: ScoringPolicyContextRecord, group: ComparisonGroupRecord) -> int:
    return (
        int(policy.operational_mode in rule.operational_modes)
        + int(group.objective_family in rule.objective_families)
        + int(group.horizon in rule.horizons)
    )


def _resolve_rule(policy: ScoringPolicyContextRecord, group: ComparisonGroupRecord) -> ScoringPolicyRule:
    matches = [
        rule for rule in policy.rules
        if _selector_match(policy.operational_mode, rule.operational_modes)
        and _selector_match(group.objective_family, rule.objective_families)
        and _selector_match(group.horizon, rule.horizons)
    ]
    if not matches:
        raise PolicyViolation(
            "P7_S4_SCORING_POLICY_NOT_FOUND",
            "no scoring rule matches candidate context",
            module_id=MODULE_ID,
            details={"candidate_id": group.candidate_id},
        )
    best = max(_specificity(rule, policy, group) for rule in matches)
    winners = [rule for rule in matches if _specificity(rule, policy, group) == best]
    if len(winners) != 1:
        raise PolicyViolation(
            "P7_S4_SCORING_POLICY_AMBIGUOUS",
            "multiple scoring rules have equal specificity",
            module_id=MODULE_ID,
            details={"candidate_id": group.candidate_id, "rules": sorted(row.rule_id for row in winners)},
        )
    return winners[0]


def _selected(frontier: ParetoFrontierRecord, rule: ScoringPolicyRule) -> bool:
    if frontier.frontier_status == FrontierStatus.INCOMPARABLE:
        return rule.include_incomparable
    return frontier.frontier_layer is not None and frontier.frontier_layer <= rule.max_frontier_layer



def _resolution(candidate_id: str, group: ComparisonGroupRecord, rule: ScoringPolicyRule) -> CandidatePolicyResolution:
    return CandidatePolicyResolution(
        candidate_id=candidate_id,
        comparison_group_id=group.comparison_group_id,
        rule_id=rule.rule_id,
        head_ids=tuple(head.head_id for head in rule.heads),
        penalty_rules=rule.penalty_rules,
        confidence_head_id=rule.confidence_head_id,
        confidence_shrinkage_strength=rule.confidence_shrinkage_strength,
    )


def _binding_records(
    candidate_id: str,
    group: ComparisonGroupRecord,
    rule: ScoringPolicyRule,
    policy: ScoringPolicyContextRecord,
) -> tuple[ScoringHeadInputRecord, ...]:
    records: list[ScoringHeadInputRecord] = []
    for head in rule.heads:
        for metric in head.metric_bindings:
            records.append(
                ScoringHeadInputRecord(
                    candidate_id=candidate_id,
                    comparison_group_id=group.comparison_group_id,
                    policy_id=policy.policy_id,
                    policy_version=policy.policy_version,
                    rule_id=rule.rule_id,
                    head_id=head.head_id,
                    head_weight=head.head_weight,
                    missing_head_action=head.missing_head_action,
                    missing_head_penalty=head.missing_head_penalty,
                    metric_id=metric.metric_id,
                    source_preference=metric.source_preference,
                    transformation=metric.transformation,
                    normalization=metric.normalization,
                    metric_weight=metric.metric_weight,
                    clip_lower=metric.clip_lower,
                    clip_upper=metric.clip_upper,
                    absolute_lower=metric.absolute_lower,
                    absolute_upper=metric.absolute_upper,
                    robust_scale=metric.robust_scale,
                    min_group_size=metric.min_group_size,
                    small_group_action=metric.small_group_action,
                    missing_metric_action=metric.missing_metric_action,
                    missing_metric_penalty=metric.missing_metric_penalty,
                    lineage_id=group.lineage_id,
                )
            )
    return tuple(records)


def _compile_candidates(
    policy: ScoringPolicyContextRecord,
    groups: dict[str, ComparisonGroupRecord],
    frontiers: dict[str, ParetoFrontierRecord],
) -> tuple[list[ScoringHeadInputRecord], list[CandidatePolicyResolution], Counter[str]]:
    bindings: list[ScoringHeadInputRecord] = []
    resolutions: list[CandidatePolicyResolution] = []
    rule_counts: Counter[str] = Counter()
    for candidate_id in sorted(frontiers):
        if candidate_id not in groups:
            raise ContractViolation(
                "P7_S4_CANDIDATE_GROUP_MISSING",
                "candidate lacks comparison group",
                module_id=MODULE_ID,
                details={"candidate_id": candidate_id},
            )
        group = groups[candidate_id]
        rule = _resolve_rule(policy, group)
        if not _selected(frontiers[candidate_id], rule):
            continue
        rule_counts[rule.rule_id] += 1
        resolutions.append(_resolution(candidate_id, group, rule))
        bindings.extend(_binding_records(candidate_id, group, rule, policy))
    return bindings, resolutions, rule_counts


def _policy_receipt(
    policy: ScoringPolicyContextRecord,
    candidate_count: int,
    bindings: list[ScoringHeadInputRecord],
    resolutions: list[CandidatePolicyResolution],
    rule_counts: Counter[str],
) -> ScoringPolicyReceiptRecord:
    return ScoringPolicyReceiptRecord(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        operational_mode=policy.operational_mode,
        policy_hash=sha256_hex(policy),
        candidate_count=candidate_count,
        selected_candidate_count=len(resolutions),
        excluded_candidate_count=candidate_count - len(resolutions),
        binding_count=len(bindings),
        resolutions=tuple(sorted(resolutions, key=lambda row: (row.comparison_group_id, row.candidate_id))),
        rule_counts=dict(sorted(rule_counts.items())),
        forbidden_field_scan_passed=True,
    )


def compile_scoring_bindings(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> dict[str, ArtifactEnvelope[Any]]:
    parsed = _parse(inputs, config)
    policy = parsed.policy.records[0]
    groups = unique_by(
        parsed.groups.records, lambda row: row.candidate_id,
        code="P7_S4_DUPLICATE_GROUP_BINDING", module_id=MODULE_ID,
    )
    frontiers = unique_by(
        parsed.pareto.records, lambda row: row.candidate_id,
        code="P7_S4_DUPLICATE_PARETO_CANDIDATE", module_id=MODULE_ID,
    )
    bindings, resolutions, rule_counts = _compile_candidates(policy, groups, frontiers)
    receipt = _policy_receipt(policy, len(frontiers), bindings, resolutions, rule_counts)
    lineage = output_lineage(MODULE_ID, parsed.artifacts())
    return build_outputs(
        module_id=MODULE_ID,
        base=parsed.pareto,
        execution_time=config.execution_time,
        lineage_id=lineage,
        named_records={
            "scoring_head_input_panel": tuple(sorted(bindings, key=lambda row: (row.comparison_group_id, row.candidate_id, row.head_id, row.metric_id))),
            "scoring_policy_receipt": (receipt,),
        },
    )
