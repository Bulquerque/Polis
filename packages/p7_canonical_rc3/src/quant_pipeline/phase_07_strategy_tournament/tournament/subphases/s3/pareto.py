from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ...boundary.artifacts import ArtifactEnvelope
from ...boundary.parsing import parse_artifact, require_inputs
from ...boundary.records import (
    DominanceRelationRecord,
    DominanceSurvivorRecord,
    DominatedCandidateRecord,
    FactorAdjustedMetricRecord,
    ParetoFrontierAuditRecord,
    ParetoFrontierRecord,
    ParetoGroupDiagnostic,
    RankingPolicyRecord,
)
from ...boundary.requests import ModuleExecutionConfig
from ...domain.artifact_validation import validate_common_identity
from ...domain.enums import CandidateDominanceStatus, FrontierStatus
from ...domain.errors import InternalInvariantViolation
from ...domain.serialization import sha256_hex
from .artifact_support import build_outputs, output_lineage, single_policy, unique_by

MODULE_ID = "P7.S3.M04"
REQUIRED_INPUTS = (
    "dominance_relation_panel",
    "dominated_candidate_panel",
    "dominance_survivor_panel",
    "factor_adjusted_metric_panel",
    "ranking_policy_context",
)


@dataclass(frozen=True, slots=True)
class ParetoInputs:
    relations: ArtifactEnvelope[DominanceRelationRecord]
    dominated: ArtifactEnvelope[DominatedCandidateRecord]
    survivors: ArtifactEnvelope[DominanceSurvivorRecord]
    adjusted: ArtifactEnvelope[FactorAdjustedMetricRecord]
    policy_artifact: ArtifactEnvelope[RankingPolicyRecord]

    def artifacts(self) -> tuple[ArtifactEnvelope[Any], ...]:
        return (self.relations, self.dominated, self.survivors, self.adjusted, self.policy_artifact)


@dataclass(frozen=True, slots=True)
class ParetoUniverse:
    comparable_by_group: dict[str, set[str]]
    incomparable_by_group: dict[str, set[str]]
    lineage_by_candidate: dict[str, str]
    incoming_count: dict[str, int]


def _parse_inputs(inputs: Mapping[str, Any], config: ModuleExecutionConfig) -> ParetoInputs:
    require_inputs(inputs, REQUIRED_INPUTS, MODULE_ID)
    types = (
        DominanceRelationRecord,
        DominatedCandidateRecord,
        DominanceSurvivorRecord,
        FactorAdjustedMetricRecord,
        RankingPolicyRecord,
    )
    parsed = [
        parse_artifact(
            inputs[name], record_type, expected_name=name, module_id=MODULE_ID,
            strict_hash_validation=config.strict_hash_validation,
        )
        for name, record_type in zip(REQUIRED_INPUTS, types, strict=True)
    ]
    result = ParetoInputs(*parsed)
    validate_common_identity(result.artifacts(), module_id=MODULE_ID)
    return result


def _layers(candidate_ids: set[str], relations: list[DominanceRelationRecord]) -> dict[str, int]:
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {candidate_id: 0 for candidate_id in candidate_ids}
    for relation in relations:
        if relation.dominator_candidate_id not in candidate_ids or relation.dominated_candidate_id not in candidate_ids:
            raise InternalInvariantViolation(
                "P7_S3_RELATION_CANDIDATE_UNKNOWN", "relation references candidate outside group", module_id=MODULE_ID
            )
        if relation.dominated_candidate_id not in outgoing[relation.dominator_candidate_id]:
            outgoing[relation.dominator_candidate_id].add(relation.dominated_candidate_id)
            indegree[relation.dominated_candidate_id] += 1
    remaining = set(candidate_ids)
    layers: dict[str, int] = {}
    layer_index = 0
    while remaining:
        current = sorted(candidate_id for candidate_id in remaining if indegree[candidate_id] == 0)
        if not current:
            raise InternalInvariantViolation(
                "P7_S3_DOMINANCE_CYCLE_DETECTED", "cannot construct Pareto layers from a cycle", module_id=MODULE_ID
            )
        for candidate_id in current:
            layers[candidate_id] = layer_index
            remaining.remove(candidate_id)
        for candidate_id in current:
            for child in outgoing[candidate_id]:
                indegree[child] -= 1
        layer_index += 1
    return layers


def _collect_universe(parsed: ParetoInputs) -> ParetoUniverse:
    dominated = unique_by(
        parsed.dominated.records, lambda row: row.candidate_id,
        code="P7_S3_DUPLICATE_DOMINATED_CANDIDATE", module_id=MODULE_ID,
    )
    survivors = unique_by(
        parsed.survivors.records, lambda row: row.candidate_id,
        code="P7_S3_DUPLICATE_SURVIVOR_CANDIDATE", module_id=MODULE_ID,
    )
    if set(dominated).intersection(survivors):
        raise InternalInvariantViolation(
            "P7_S3_DOMINANCE_PARTITION_OVERLAP", "candidate appears in both partitions", module_id=MODULE_ID
        )
    comparable: dict[str, set[str]] = defaultdict(set)
    incomparable: dict[str, set[str]] = defaultdict(set)
    lineage: dict[str, str] = {}
    incoming: dict[str, int] = defaultdict(int)
    for row in parsed.dominated.records:
        comparable[row.comparison_group_id].add(row.candidate_id)
        lineage[row.candidate_id] = row.lineage_id
        incoming[row.candidate_id] = row.incoming_relation_count
    for row in parsed.survivors.records:
        lineage[row.candidate_id] = row.lineage_id
        if row.eligible_for_pareto and row.status == CandidateDominanceStatus.SURVIVOR:
            comparable[row.comparison_group_id].add(row.candidate_id)
        else:
            incomparable[row.comparison_group_id].add(row.candidate_id)
    return ParetoUniverse(comparable, incomparable, lineage, dict(incoming))


def _metric_vectors(parsed: ParetoInputs) -> dict[str, dict[str, float]]:
    vectors: dict[str, dict[str, float]] = defaultdict(dict)
    for row in parsed.adjusted.records:
        if row.adjusted_directed_value is not None:
            vectors[row.candidate_id][row.metric_id] = row.adjusted_directed_value
    return vectors


def _group_records(
    group_id: str,
    universe: ParetoUniverse,
    relations: list[DominanceRelationRecord],
    vectors: dict[str, dict[str, float]],
    policy: RankingPolicyRecord,
) -> tuple[list[ParetoFrontierRecord], ParetoGroupDiagnostic]:
    candidates = universe.comparable_by_group[group_id]
    layer_map = _layers(candidates, relations) if candidates else {}
    records: list[ParetoFrontierRecord] = []
    for candidate_id in sorted(candidates):
        vector = {
            metric_id: vectors[candidate_id][metric_id]
            for metric_id in policy.dominance.active_metric_ids
            if metric_id in vectors[candidate_id]
        }
        if len(vector) != len(policy.dominance.active_metric_ids):
            raise InternalInvariantViolation(
                "P7_S3_PARETO_VECTOR_INCOMPLETE", "comparable candidate has incomplete vector",
                module_id=MODULE_ID, details={"candidate_id": candidate_id},
            )
        layer = layer_map[candidate_id]
        records.append(
            ParetoFrontierRecord(
                candidate_id=candidate_id,
                comparison_group_id=group_id,
                frontier_layer=layer,
                frontier_status=FrontierStatus.FRONTIER if layer == 0 else FrontierStatus.DOMINATED_LAYER,
                dominated_by_count=universe.incoming_count.get(candidate_id, 0),
                metric_vector_hash=sha256_hex(vector),
                policy_id=policy.policy_id,
                lineage_id=universe.lineage_by_candidate[candidate_id],
            )
        )
    for candidate_id in sorted(universe.incomparable_by_group[group_id]):
        records.append(
            ParetoFrontierRecord(
                candidate_id=candidate_id,
                comparison_group_id=group_id,
                frontier_layer=None,
                frontier_status=FrontierStatus.INCOMPARABLE,
                dominated_by_count=0,
                metric_vector_hash=None,
                policy_id=policy.policy_id,
                lineage_id=universe.lineage_by_candidate[candidate_id],
            )
        )
    comparable_count = len(candidates)
    diagnostic = ParetoGroupDiagnostic(
        comparison_group_id=group_id,
        candidate_count=comparable_count + len(universe.incomparable_by_group[group_id]),
        comparable_candidate_count=comparable_count,
        incomparable_candidate_count=len(universe.incomparable_by_group[group_id]),
        relation_count=len(relations),
        layer_count=max(layer_map.values()) + 1 if layer_map else 0,
        pair_comparisons=comparable_count * (comparable_count - 1) // 2,
    )
    return records, diagnostic


def build_pareto_frontiers(
    inputs: Mapping[str, Any],
    config: ModuleExecutionConfig,
) -> dict[str, ArtifactEnvelope[Any]]:
    parsed = _parse_inputs(inputs, config)
    policy = single_policy(parsed.policy_artifact, module_id=MODULE_ID)
    universe = _collect_universe(parsed)
    vectors = _metric_vectors(parsed)
    relations_by_group: dict[str, list[DominanceRelationRecord]] = defaultdict(list)
    for relation in parsed.relations.records:
        relations_by_group[relation.comparison_group_id].append(relation)
    records: list[ParetoFrontierRecord] = []
    diagnostics: list[ParetoGroupDiagnostic] = []
    groups = sorted(set(universe.comparable_by_group) | set(universe.incomparable_by_group))
    for group_id in groups:
        group_rows, diagnostic = _group_records(
            group_id, universe, relations_by_group[group_id], vectors, policy
        )
        records.extend(group_rows)
        diagnostics.append(diagnostic)
    ordered = tuple(
        sorted(records, key=lambda row: (row.comparison_group_id, row.frontier_layer is None, row.frontier_layer or 0, row.candidate_id))
    )
    audit = ParetoFrontierAuditRecord(
        policy_id=policy.policy_id,
        exact_algorithm=True,
        group_count=len(diagnostics),
        candidate_count=len(ordered),
        frontier_count=sum(row.frontier_status == FrontierStatus.FRONTIER for row in ordered),
        incomparable_count=sum(row.frontier_status == FrontierStatus.INCOMPARABLE for row in ordered),
        diagnostics=tuple(diagnostics),
        permutation_invariant_serialization=True,
    )
    return build_outputs(
        module_id=MODULE_ID,
        base=parsed.relations,
        execution_time=config.execution_time,
        lineage_id=output_lineage(MODULE_ID, parsed.artifacts()),
        named_records={"pareto_frontier_panel": ordered, "pareto_frontier_audit_report": (audit,)},
    )
