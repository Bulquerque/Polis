from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope
from ...boundary.parsing import parse_artifact, require_inputs
from ...boundary.records import (
    ComparisonGroupRecord,
    ComparableMetricRecord,
    DominanceEvidence,
    DominanceRelationRecord,
    DominanceSurvivorRecord,
    DominatedCandidateRecord,
    FactorAdjustedMetricRecord,
    MetricPolicy,
    RankingPolicyRecord,
)
from ...boundary.requests import ModuleExecutionConfig
from ...domain.artifact_validation import validate_common_identity
from ...domain.enums import AdjustmentStatus, CandidateDominanceStatus, ComparisonStatus
from ...domain.errors import InternalInvariantViolation, ResourceBudgetExceeded
from ...domain.serialization import sha256_hex
from .artifact_support import build_outputs, output_lineage, single_policy, unique_by

MODULE_ID = "P7.S3.M03"
REQUIRED_INPUTS = (
    "factor_adjusted_metric_panel",
    "comparable_candidate_metric_panel",
    "candidate_comparison_group_panel",
    "ranking_policy_context",
)


@dataclass(frozen=True, slots=True)
class DominanceInputs:
    adjusted: ArtifactEnvelope[FactorAdjustedMetricRecord]
    comparable: ArtifactEnvelope[ComparableMetricRecord]
    groups: ArtifactEnvelope[ComparisonGroupRecord]
    policy_artifact: ArtifactEnvelope[RankingPolicyRecord]

    def artifacts(self) -> tuple[ArtifactEnvelope[Any], ...]:
        return (self.adjusted, self.comparable, self.groups, self.policy_artifact)


@dataclass(frozen=True, slots=True)
class CandidateVectors:
    complete: dict[str, dict[str, float]]
    incomplete: dict[str, tuple[str, ...]]


def _parse_inputs(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> DominanceInputs:
    require_inputs(inputs, REQUIRED_INPUTS, MODULE_ID)
    types = (
        FactorAdjustedMetricRecord,
        ComparableMetricRecord,
        ComparisonGroupRecord,
        RankingPolicyRecord,
    )
    parsed = [
        parse_artifact(
            inputs[name], record_type, expected_name=name, module_id=MODULE_ID,
            strict_hash_validation=config.strict_hash_validation,
        )
        for name, record_type in zip(REQUIRED_INPUTS, types, strict=True)
    ]
    result = DominanceInputs(*parsed)
    validate_common_identity(result.artifacts(), module_id=MODULE_ID)
    return result


def _selected_value(row: FactorAdjustedMetricRecord | None) -> float | None:
    if row is None:
        return None
    allowed = {AdjustmentStatus.ADJUSTED, AdjustmentStatus.BYPASS, AdjustmentStatus.NOT_APPLICABLE}
    return row.adjusted_directed_value if row.adjustment_status in allowed else None


def _build_vectors(parsed: DominanceInputs, policy: RankingPolicyRecord) -> CandidateVectors:
    groups = unique_by(
        parsed.groups.records, lambda row: row.candidate_id,
        code="P7_S3_DUPLICATE_GROUP_BINDING", module_id=MODULE_ID,
    )
    adjusted = unique_by(
        parsed.adjusted.records, lambda row: (row.candidate_id, row.metric_id),
        code="P7_S3_DUPLICATE_ADJUSTED_METRIC", module_id=MODULE_ID,
    )
    comparable = unique_by(
        parsed.comparable.records, lambda row: (row.candidate_id, row.metric_id),
        code="P7_S3_DUPLICATE_COMPARABLE_METRIC", module_id=MODULE_ID,
    )
    complete: dict[str, dict[str, float]] = {}
    incomplete: dict[str, tuple[str, ...]] = {}
    for candidate_id in sorted(groups):
        vector: dict[str, float] = {}
        missing: list[str] = []
        for metric_id in policy.dominance.active_metric_ids:
            comparable_row = comparable.get((candidate_id, metric_id))
            value = _selected_value(adjusted.get((candidate_id, metric_id)))
            if comparable_row is None or comparable_row.comparison_status != ComparisonStatus.AVAILABLE or value is None:
                missing.append(metric_id)
            else:
                vector[metric_id] = value
        if missing:
            incomplete[candidate_id] = tuple(sorted(missing))
        else:
            complete[candidate_id] = vector
    return CandidateVectors(complete, incomplete)


def _tolerance(first: float, second: float, metric: MetricPolicy) -> float:
    return metric.epsilon_absolute + metric.epsilon_relative * max(abs(first), abs(second))


def _dominates(
    first: dict[str, float],
    second: dict[str, float],
    policy_by_metric: dict[str, MetricPolicy],
    active_metrics: tuple[str, ...],
) -> tuple[bool, tuple[DominanceEvidence, ...]]:
    evidence: list[DominanceEvidence] = []
    materially_better_any = False
    for metric_id in active_metrics:
        first_value, second_value = first[metric_id], second[metric_id]
        tolerance = _tolerance(first_value, second_value, policy_by_metric[metric_id])
        if first_value < second_value - tolerance:
            return False, ()
        materially_better = first_value > second_value + tolerance
        materially_better_any |= materially_better
        evidence.append(
            DominanceEvidence(
                metric_id=metric_id,
                dominator_value=first_value,
                dominated_value=second_value,
                tolerance=tolerance,
                materially_better=materially_better,
            )
        )
    return materially_better_any, tuple(evidence)


def _relation(
    group_id: str,
    dominator: str,
    dominated: str,
    evidence: tuple[DominanceEvidence, ...],
    policy_id: str,
) -> DominanceRelationRecord:
    payload = {
        "group": group_id,
        "dominator": dominator,
        "dominated": dominated,
        "evidence": [row.model_dump(mode="json") for row in evidence],
        "policy": policy_id,
    }
    return DominanceRelationRecord(
        comparison_group_id=group_id,
        dominator_candidate_id=dominator,
        dominated_candidate_id=dominated,
        evidence=evidence,
        policy_id=policy_id,
        relation_hash=sha256_hex(payload),
    )


def _compare_group(
    group_id: str,
    candidate_ids: list[str],
    vectors: dict[str, dict[str, float]],
    policy: RankingPolicyRecord,
) -> list[DominanceRelationRecord]:
    relations: list[DominanceRelationRecord] = []
    policy_by_metric = {row.metric_id: row for row in policy.metric_policies}
    for index, first_id in enumerate(candidate_ids):
        for second_id in candidate_ids[index + 1 :]:
            first_wins, first_evidence = _dominates(
                vectors[first_id], vectors[second_id], policy_by_metric, policy.dominance.active_metric_ids
            )
            second_wins, second_evidence = _dominates(
                vectors[second_id], vectors[first_id], policy_by_metric, policy.dominance.active_metric_ids
            )
            if first_wins and second_wins:
                raise InternalInvariantViolation(
                    "P7_S3_MUTUAL_DOMINANCE_DETECTED", "two candidates mutually dominate",
                    module_id=MODULE_ID, details={"candidate_ids": [first_id, second_id]},
                )
            if first_wins:
                relations.append(_relation(group_id, first_id, second_id, first_evidence, policy.policy_id))
            elif second_wins:
                relations.append(_relation(group_id, second_id, first_id, second_evidence, policy.policy_id))
    return relations


def _compute_relations(
    groups: dict[str, ComparisonGroupRecord],
    vectors: CandidateVectors,
    policy: RankingPolicyRecord,
) -> list[DominanceRelationRecord]:
    by_group: dict[str, list[str]] = defaultdict(list)
    for candidate_id in sorted(vectors.complete):
        by_group[groups[candidate_id].comparison_group_id].append(candidate_id)
    relations: list[DominanceRelationRecord] = []
    pair_count = 0
    for group_id in sorted(by_group):
        candidate_ids = by_group[group_id]
        if len(candidate_ids) > policy.dominance.exact_max_group_size:
            raise ResourceBudgetExceeded(
                "P7_S3_EXACT_GROUP_BUDGET_EXCEEDED", "group exceeds exact dominance budget",
                module_id=MODULE_ID, details={"comparison_group_id": group_id, "candidate_count": len(candidate_ids)},
            )
        pair_count += len(candidate_ids) * (len(candidate_ids) - 1) // 2
        if pair_count > policy.dominance.exact_max_pair_comparisons:
            raise ResourceBudgetExceeded(
                "P7_S3_PAIR_BUDGET_EXCEEDED", "pair comparison budget exceeded",
                module_id=MODULE_ID, details={"pair_comparisons": pair_count},
            )
        relations.extend(_compare_group(group_id, candidate_ids, vectors.complete, policy))
    return relations


def _assert_acyclic(candidate_ids: set[str], relations: list[DominanceRelationRecord]) -> None:
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {candidate_id: 0 for candidate_id in candidate_ids}
    for relation in relations:
        if relation.dominated_candidate_id not in outgoing[relation.dominator_candidate_id]:
            outgoing[relation.dominator_candidate_id].add(relation.dominated_candidate_id)
            indegree[relation.dominated_candidate_id] += 1
    queue = deque(sorted(candidate_id for candidate_id, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in sorted(outgoing[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(candidate_ids):
        raise InternalInvariantViolation(
            "P7_S3_DOMINANCE_CYCLE_DETECTED", "strict dominance contains a cycle", module_id=MODULE_ID
        )


def _partition_candidates(
    groups: dict[str, ComparisonGroupRecord],
    vectors: CandidateVectors,
    relations: list[DominanceRelationRecord],
    policy: RankingPolicyRecord,
) -> tuple[tuple[DominatedCandidateRecord, ...], tuple[DominanceSurvivorRecord, ...]]:
    incoming: dict[str, set[str]] = defaultdict(set)
    for relation in relations:
        incoming[relation.dominated_candidate_id].add(relation.dominator_candidate_id)
    dominated: list[DominatedCandidateRecord] = []
    survivors: list[DominanceSurvivorRecord] = []
    for candidate_id in sorted(groups):
        group = groups[candidate_id]
        if candidate_id in vectors.incomplete:
            reason = (
                "P7_S3_CANDIDATE_BLOCKED_REQUIRED_METRIC"
                if policy.dominance.missing_required_metric_action == "BLOCK_CANDIDATE"
                else "P7_S3_CANDIDATE_INCOMPARABLE_REQUIRED_METRIC"
            )
            survivors.append(
                DominanceSurvivorRecord(
                    candidate_id=candidate_id,
                    comparison_group_id=group.comparison_group_id,
                    status=CandidateDominanceStatus.INCOMPARABLE_MISSING_REQUIRED,
                    eligible_for_pareto=False,
                    reason_code=reason,
                    lineage_id=group.lineage_id,
                )
            )
        elif incoming[candidate_id]:
            dominators = tuple(sorted(incoming[candidate_id]))
            dominated.append(
                DominatedCandidateRecord(
                    candidate_id=candidate_id,
                    comparison_group_id=group.comparison_group_id,
                    status=CandidateDominanceStatus.DOMINATED,
                    dominator_candidate_ids=dominators,
                    incoming_relation_count=len(dominators),
                    lineage_id=group.lineage_id,
                )
            )
        else:
            survivors.append(
                DominanceSurvivorRecord(
                    candidate_id=candidate_id,
                    comparison_group_id=group.comparison_group_id,
                    status=CandidateDominanceStatus.SURVIVOR,
                    eligible_for_pareto=True,
                    reason_code=None,
                    lineage_id=group.lineage_id,
                )
            )
    return tuple(dominated), tuple(survivors)


def filter_strict_dominance(
    inputs: Mapping[str, Any],
    config: ModuleExecutionConfig,
) -> dict[str, ArtifactEnvelope[Any]]:
    parsed = _parse_inputs(inputs, config)
    policy = single_policy(parsed.policy_artifact, module_id=MODULE_ID)
    groups = unique_by(
        parsed.groups.records, lambda row: row.candidate_id,
        code="P7_S3_DUPLICATE_GROUP_BINDING", module_id=MODULE_ID,
    )
    vectors = _build_vectors(parsed, policy)
    relations = _compute_relations(groups, vectors, policy)
    _assert_acyclic(set(vectors.complete), relations)
    dominated, survivors = _partition_candidates(groups, vectors, relations, policy)
    if len(dominated) + len(survivors) != len(groups):
        raise InternalInvariantViolation(
            "P7_S3_CANDIDATE_CONSERVATION_FAILED", "candidate identities were not conserved", module_id=MODULE_ID
        )
    return build_outputs(
        module_id=MODULE_ID,
        base=parsed.adjusted,
        execution_time=config.execution_time,
        lineage_id=output_lineage(MODULE_ID, parsed.artifacts()),
        named_records={
            "dominance_relation_panel": tuple(
                sorted(relations, key=lambda row: (row.comparison_group_id, row.dominator_candidate_id, row.dominated_candidate_id))
            ),
            "dominated_candidate_panel": tuple(sorted(dominated, key=lambda row: (row.comparison_group_id, row.candidate_id))),
            "dominance_survivor_panel": tuple(sorted(survivors, key=lambda row: (row.comparison_group_id, row.candidate_id))),
        },
    )
