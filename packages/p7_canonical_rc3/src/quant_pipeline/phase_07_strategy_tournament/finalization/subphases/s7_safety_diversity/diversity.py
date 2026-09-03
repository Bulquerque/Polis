"""Deterministic redundancy clusters and bounded diversity adjustment."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ...artifacts import sha256_value
from ...boundary.config import DiversityPolicy
from ...boundary.outputs import DiversityAdjustedScoreRecord, DiversityAdjustmentRecord, DiversityClusterRecord
from ...domain.models import Candidate
from ...errors import ErrorContext, IntegrityViolation


class _UnionFind:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != value:
            value, self.parent[value] = self.parent[value], root
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        self.parent[high] = low


@dataclass(frozen=True, slots=True)
class DiversityOutputs:
    clusters: tuple[DiversityClusterRecord, ...]
    adjustments: tuple[DiversityAdjustmentRecord, ...]
    scores: tuple[DiversityAdjustedScoreRecord, ...]


def _cluster_ids(
    group_id: str,
    candidate_ids: list[str],
    edge_scores: dict[tuple[str, str], float],
    threshold: float,
) -> dict[str, str]:
    union_find = _UnionFind(candidate_ids)
    for (left, right), similarity in sorted(edge_scores.items()):
        if left in union_find.parent and right in union_find.parent and similarity >= threshold:
            union_find.union(left, right)
    stages: dict[str, list[str]] = defaultdict(list)
    for candidate_id in candidate_ids:
        stages[union_find.find(candidate_id)].append(candidate_id)
    return {
        candidate_id: f"cluster:{sha256_value((group_id, tuple(sorted(stage))))[:16]}"
        for stage in stages.values()
        for candidate_id in stage
    }


def _neighbor_scores(
    candidate_ids: frozenset[str], edge_scores: dict[tuple[str, str], float]
) -> dict[str, list[float]]:
    neighbors: dict[str, list[float]] = defaultdict(list)
    for (left, right), similarity in edge_scores.items():
        if left in candidate_ids and right in candidate_ids:
            neighbors[left].append(similarity)
            neighbors[right].append(similarity)
    return neighbors


def _candidate_outputs(
    candidate: Candidate,
    cluster_id: str,
    density: float,
    policy: DiversityPolicy,
) -> tuple[DiversityClusterRecord, DiversityAdjustmentRecord, DiversityAdjustedScoreRecord]:
    penalty_cap = policy.max_penalty_fraction * policy.score_scale
    raw_penalty = policy.penalty_lambda * density * policy.score_scale
    applied_penalty = min(raw_penalty, penalty_cap)
    adjusted = None if candidate.hybrid_score is None else candidate.hybrid_score - applied_penalty
    cluster = DiversityClusterRecord(
        cycle_id=candidate.cycle_id,
        decision_time=candidate.decision_time,
        comparison_group_id=candidate.comparison_group_id,
        candidate_id=candidate.candidate_id,
        diversity_cluster_id=cluster_id,
        local_density=density,
        novelty_score=1.0 - density,
        policy_version=policy.policy_id,
        lineage_id=candidate.lineage_id,
    )
    adjustment = DiversityAdjustmentRecord(
        cycle_id=candidate.cycle_id,
        decision_time=candidate.decision_time,
        comparison_group_id=candidate.comparison_group_id,
        candidate_id=candidate.candidate_id,
        local_density=density,
        raw_penalty=raw_penalty,
        applied_penalty=applied_penalty,
        penalty_cap=penalty_cap,
        policy_version=policy.policy_id,
        lineage_id=candidate.lineage_id,
    )
    score = DiversityAdjustedScoreRecord(
        cycle_id=candidate.cycle_id,
        decision_time=candidate.decision_time,
        comparison_group_id=candidate.comparison_group_id,
        candidate_id=candidate.candidate_id,
        hybrid_score=candidate.hybrid_score,
        diversity_penalty=applied_penalty,
        diversity_adjusted_score=adjusted,
        score_confidence=candidate.score_confidence,
        score_status="VALID" if adjusted is not None else "NON_FINITE_OR_MISSING",
        policy_version=policy.policy_id,
        lineage_id=candidate.lineage_id,
    )
    return cluster, adjustment, score


def _adjust_group(
    group_id: str,
    members: list[Candidate],
    edge_scores: dict[tuple[str, str], float],
    policy: DiversityPolicy,
) -> DiversityOutputs:
    candidate_ids = [item.candidate_id for item in members]
    clusters = _cluster_ids(group_id, candidate_ids, edge_scores, policy.cluster_threshold)
    neighbors = _neighbor_scores(frozenset(candidate_ids), edge_scores)
    denominator = min(policy.density_top_k, max(0, len(members) - 1))
    cluster_records: list[DiversityClusterRecord] = []
    adjustment_records: list[DiversityAdjustmentRecord] = []
    score_records: list[DiversityAdjustedScoreRecord] = []
    for candidate in members:
        top_scores = sorted(neighbors[candidate.candidate_id], reverse=True)[:denominator]
        density = sum(top_scores) / denominator if denominator else 0.0
        cluster, adjustment, score = _candidate_outputs(candidate, clusters[candidate.candidate_id], density, policy)
        cluster_records.append(cluster)
        adjustment_records.append(adjustment)
        score_records.append(score)
    return DiversityOutputs(tuple(cluster_records), tuple(adjustment_records), tuple(score_records))


def _validated_edge_scores(
    candidates: tuple[Candidate, ...], edges: tuple[object, ...]
) -> dict[tuple[str, str], float]:
    group_by_id = {candidate.candidate_id: candidate.comparison_group_id for candidate in candidates}
    scores: dict[tuple[str, str], float] = {}
    for edge in edges:
        left = str(getattr(edge, "candidate_id_left"))
        right = str(getattr(edge, "candidate_id_right"))
        edge_group = str(getattr(edge, "comparison_group_id"))
        if left not in group_by_id or right not in group_by_id:
            context = ErrorContext("P7.S7.M02", candidate_ids=(left, right))
            raise IntegrityViolation("P7_CANDIDATE_RECONCILIATION_FAILED", "edge references unknown candidate", context)
        if group_by_id[left] != edge_group or group_by_id[right] != edge_group:
            context = ErrorContext("P7.S7.M02", candidate_ids=(left, right))
            raise IntegrityViolation("P7_SIMILARITY_CROSS_GROUP_FORBIDDEN", edge_group, context)
        key = tuple(sorted((left, right)))
        if key in scores:
            context = ErrorContext("P7.S7.M02", candidate_ids=key)
            raise IntegrityViolation("P7_DUPLICATE_CANDIDATE_ID", "duplicate similarity edge", context)
        scores[key] = float(getattr(edge, "similarity_score"))
    return scores


def adjust_diversity(
    candidates: tuple[Candidate, ...],
    edges: tuple[object, ...],
    policy: DiversityPolicy,
) -> tuple[tuple[DiversityClusterRecord, ...], tuple[DiversityAdjustmentRecord, ...], tuple[DiversityAdjustedScoreRecord, ...]]:
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        groups[candidate.comparison_group_id].append(candidate)
    edge_scores = _validated_edge_scores(candidates, edges)
    outputs = [
        _adjust_group(group_id, sorted(members, key=lambda item: item.candidate_id), edge_scores, policy)
        for group_id, members in sorted(groups.items())
    ]
    clusters = tuple(record for output in outputs for record in output.clusters)
    adjustments = tuple(record for output in outputs for record in output.adjustments)
    scores = tuple(record for output in outputs for record in output.scores)
    return clusters, adjustments, scores
