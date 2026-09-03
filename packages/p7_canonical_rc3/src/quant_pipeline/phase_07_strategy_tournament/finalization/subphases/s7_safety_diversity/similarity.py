"""Sparse, deterministic candidate similarity graph."""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from math import sqrt

from ...boundary.config import SimilarityPolicy
from ...boundary.outputs import SimilarityEdgeRecord, SimilaritySummaryRecord
from ...domain.models import Candidate, SimilarityResult
from ...errors import ErrorContext, PolicyViolation


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
    if not left or len(left) != len(right):
        return None
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 1.0 if left == right else None
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _pearson(left: tuple[float, ...], right: tuple[float, ...]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    centered_left = tuple(value - left_mean for value in left)
    centered_right = tuple(value - right_mean for value in right)
    return _cosine(centered_left, centered_right)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float | None:
    if not left and not right:
        return None
    return len(left & right) / len(left | right)


def _template(left: str | None, right: str | None) -> float | None:
    if left is None or right is None:
        return None
    return 1.0 if left == right else 0.0


def pair_similarity(left: Candidate, right: Candidate, policy: SimilarityPolicy) -> SimilarityResult:
    stage_values = {
        "payoff_shape": _cosine(left.payoff_shape, right.payoff_shape),
        "scenario_payoff": _pearson(left.scenario_payoff, right.scenario_payoff),
        "greek_vector": _cosine(left.greek_vector, right.greek_vector),
        "leg_jaccard": _jaccard(left.leg_ids, right.leg_ids),
        "origin_template": _template(left.origin_template, right.origin_template),
        "expiration_overlap": _jaccard(left.expiration_ids, right.expiration_ids),
    }
    weights = {stage.name: stage.weight for stage in policy.stages}
    total_weight = sum(weights.values())
    present = {name: value for name, value in stage_values.items() if value is not None}
    present_weight = sum(weights[name] for name in present)
    coverage = present_weight / total_weight
    if coverage < policy.minimum_weight_coverage:
        return SimilarityResult(None, tuple(sorted(present.items())), coverage)
    score = sum(weights[name] * value for name, value in present.items()) / present_weight
    return SimilarityResult(max(0.0, min(1.0, score)), tuple(sorted(present.items())), coverage)


def _select_edges(
    pair_results: dict[tuple[str, str], SimilarityResult], policy: SimilarityPolicy
) -> set[tuple[str, str]]:
    by_candidate: dict[str, list[tuple[float, tuple[str, str]]]] = defaultdict(list)
    for key, result in pair_results.items():
        if result.score is None or result.score < policy.minimum_edge_similarity:
            continue
        by_candidate[key[0]].append((result.score, key))
        by_candidate[key[1]].append((result.score, key))
    selected: set[tuple[str, str]] = set()
    for values in by_candidate.values():
        values.sort(key=lambda item: (-item[0], item[1]))
        selected.update(key for _, key in values[: policy.top_k_neighbors])
    return selected


def _evaluate_group(
    group_id: str, members: list[Candidate], policy: SimilarityPolicy
) -> tuple[list[SimilarityEdgeRecord], list[SimilaritySummaryRecord], list[str]]:
    pair_results: dict[tuple[str, str], SimilarityResult] = {}
    evaluated: dict[str, int] = defaultdict(int)
    insufficient: dict[str, int] = defaultdict(int)
    reasons: list[str] = []
    for left, right in combinations(members, 2):
        result = pair_similarity(left, right, policy)
        pair_results[(left.candidate_id, right.candidate_id)] = result
        evaluated[left.candidate_id] += 1
        evaluated[right.candidate_id] += 1
        if result.score is None:
            insufficient[left.candidate_id] += 1
            insufficient[right.candidate_id] += 1
            reasons.append("P7_SIMILARITY_INSUFFICIENT_EVIDENCE")
    return _materialize_group(group_id, members, pair_results, evaluated, insufficient, reasons, policy)


def _materialize_group(
    group_id: str,
    members: list[Candidate],
    pair_results: dict[tuple[str, str], SimilarityResult],
    evaluated: dict[str, int],
    insufficient: dict[str, int],
    reasons: list[str],
    policy: SimilarityPolicy,
) -> tuple[list[SimilarityEdgeRecord], list[SimilaritySummaryRecord], list[str]]:
    selected = _select_edges(pair_results, policy)
    neighbor_scores: dict[str, list[float]] = defaultdict(list)
    member_by_id = {item.candidate_id: item for item in members}
    edges: list[SimilarityEdgeRecord] = []
    for left, right in sorted(selected):
        result = pair_results[(left, right)]
        assert result.score is not None
        neighbor_scores[left].append(result.score)
        neighbor_scores[right].append(result.score)
        edges.append(_edge_record(group_id, member_by_id[left], member_by_id[right], result, policy))
    summaries = _summary_records(group_id, members, neighbor_scores, evaluated, insufficient, policy)
    return edges, summaries, reasons


def _edge_record(
    group_id: str,
    left: Candidate,
    right: Candidate,
    result: SimilarityResult,
    policy: SimilarityPolicy,
) -> SimilarityEdgeRecord:
    assert result.score is not None
    return SimilarityEdgeRecord(
        cycle_id=left.cycle_id,
        decision_time=left.decision_time,
        comparison_group_id=group_id,
        candidate_id_left=left.candidate_id,
        candidate_id_right=right.candidate_id,
        similarity_score=result.score,
        stage_scores=dict(result.stage_scores),
        evidence_weight_coverage=result.evidence_weight_coverage,
        policy_version=policy.policy_id,
        lineage_id=f"sim:{left.lineage_id}:{right.lineage_id}",
    )


def _summary_records(
    group_id: str,
    members: list[Candidate],
    neighbors: dict[str, list[float]],
    evaluated: dict[str, int],
    insufficient: dict[str, int],
    policy: SimilarityPolicy,
) -> list[SimilaritySummaryRecord]:
    denominator = min(policy.top_k_neighbors, max(0, len(members) - 1))
    records: list[SimilaritySummaryRecord] = []
    for member in members:
        scores = sorted(neighbors[member.candidate_id], reverse=True)
        mean_top = sum(scores[:denominator]) / denominator if denominator else 0.0
        records.append(SimilaritySummaryRecord(
            cycle_id=member.cycle_id,
            decision_time=member.decision_time,
            comparison_group_id=group_id,
            candidate_id=member.candidate_id,
            retained_neighbor_count=len(scores),
            evaluated_pair_count=evaluated[member.candidate_id],
            insufficient_evidence_pair_count=insufficient[member.candidate_id],
            top_similarity=scores[0] if scores else 0.0,
            mean_top_k_similarity=mean_top,
            policy_version=policy.policy_id,
            lineage_id=member.lineage_id,
        ))
    return records


def build_similarity_graph(
    candidates: tuple[Candidate, ...], policy: SimilarityPolicy
) -> tuple[tuple[SimilarityEdgeRecord, ...], tuple[SimilaritySummaryRecord, ...], tuple[str, ...]]:
    groups: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        groups[candidate.comparison_group_id].append(candidate)
    all_edges: list[SimilarityEdgeRecord] = []
    summaries: list[SimilaritySummaryRecord] = []
    reasons: list[str] = []
    for group_id, members in sorted(groups.items()):
        members.sort(key=lambda item: item.candidate_id)
        if len(members) > policy.max_group_size:
            context = ErrorContext("P7.S7.M01", candidate_ids=tuple(item.candidate_id for item in members))
            raise PolicyViolation("P7_SIMILARITY_GROUP_SIZE_EXCEEDED", group_id, context)
        group_edges, group_summaries, group_reasons = _evaluate_group(group_id, members, policy)
        all_edges.extend(group_edges)
        summaries.extend(group_summaries)
        reasons.extend(group_reasons)
    return tuple(all_edges), tuple(summaries), tuple(reasons)
