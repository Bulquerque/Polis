"""Deterministic lexicographic ranking within frozen comparison groups."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby

from ...artifacts import sha256_value
from ...boundary.s8_config import RankingPolicy
from ...boundary.s8_outputs import RankedStrategyRecord, RankingGroupSummaryRecord, RankingTieRecord
from ...domain.s8_models import RankingCandidate
from ...errors import ErrorContext, IntegrityViolation, PolicyViolation


@dataclass(frozen=True, slots=True)
class RankingOutputs:
    ranked: tuple[RankedStrategyRecord, ...]
    ties: tuple[RankingTieRecord, ...]
    groups: tuple[RankingGroupSummaryRecord, ...]


def _rounded(value: float, digits: int) -> float:
    return round(float(value), digits)


def _economic_key(item: RankingCandidate, policy: RankingPolicy) -> tuple[object, ...]:
    row = item.rankable
    return (
        row.pareto_tier,
        -_rounded(row.diversity_adjusted_score, policy.score_round_digits),
        -_rounded(row.score_confidence, policy.score_round_digits),
        -_rounded(row.robustness_stage, policy.score_round_digits),
        -_rounded(row.execution_quality_stage, policy.score_round_digits),
        row.leg_count,
    )


def _sort_key(item: RankingCandidate, policy: RankingPolicy) -> tuple[object, ...]:
    return _economic_key(item, policy) + (item.rankable.candidate_id,)


def _tie_map(items: list[RankingCandidate], policy: RankingPolicy) -> tuple[dict[str, str], list[RankingTieRecord]]:
    tie_by_candidate: dict[str, str] = {}
    records: list[RankingTieRecord] = []
    for key, grouped in groupby(items, key=lambda item: _economic_key(item, policy)):
        members = list(grouped)
        if len(members) < 2:
            continue
        ids = tuple(sorted(item.rankable.candidate_id for item in members))
        digest = sha256_value({"group": members[0].rankable.comparison_group_id, "key": key, "candidates": ids})
        tie_id = f"tie:{digest[:20]}"
        tie_by_candidate.update({candidate_id: tie_id for candidate_id in ids})
        first = members[0].rankable
        records.append(RankingTieRecord(
            cycle_id=first.cycle_id,
            decision_time=first.decision_time,
            comparison_group_id=first.comparison_group_id,
            economic_tie_id=tie_id,
            candidate_ids=ids,
            deterministic_order=ids,
            tie_key_sha256=digest,
            policy_version=policy.policy_id,
            lineage_id=first.lineage_id,
        ))
    return tie_by_candidate, records


def _rank_group(items: list[RankingCandidate], policy: RankingPolicy) -> tuple[list[RankedStrategyRecord], list[RankingTieRecord]]:
    if len(items) > policy.max_group_size:
        raise PolicyViolation("P7_RANKING_GROUP_TOO_LARGE", str(len(items)), ErrorContext("P7.S8.M01"))
    ordered = sorted(items, key=lambda item: _sort_key(item, policy))
    tie_map, ties = _tie_map(ordered, policy)
    ranked: list[RankedStrategyRecord] = []
    for position, item in enumerate(ordered, start=1):
        row, group, strategy, cluster = item.rankable, item.group, item.strategy, item.cluster
        ranked.append(RankedStrategyRecord(
            cycle_id=row.cycle_id,
            decision_time=row.decision_time,
            comparison_group_id=row.comparison_group_id,
            underlying_id=group.underlying_id,
            horizon=group.horizon,
            objective_family=group.objective_family,
            risk_bucket=group.risk_bucket,
            candidate_id=row.candidate_id,
            rank_position=position,
            economic_tie_id=tie_map.get(row.candidate_id),
            pareto_tier=row.pareto_tier,
            hybrid_score=row.hybrid_score,
            diversity_penalty=row.diversity_penalty,
            diversity_adjusted_score=row.diversity_adjusted_score,
            score_confidence=row.score_confidence,
            robustness_stage=row.robustness_stage,
            execution_quality_stage=row.execution_quality_stage,
            leg_count=row.leg_count,
            diversity_cluster_id=cluster.diversity_cluster_id,
            model_id=row.model_id,
            score_semantics_version=row.score_semantics_version,
            calibration_status=row.calibration_status,
            calibration_version=row.calibration_version,
            ood_severity=row.ood_severity,
            model_disagreement=row.model_disagreement,
            ranking_policy_version=policy.policy_id,
            lineage_id=strategy.strategy_lineage_id,
        ))
    return ranked, ties


def rank_candidates(candidates: tuple[RankingCandidate, ...], policy: RankingPolicy) -> RankingOutputs:
    by_group: dict[str, list[RankingCandidate]] = {}
    seen: set[str] = set()
    for item in candidates:
        candidate_id = item.rankable.candidate_id
        if candidate_id in seen:
            raise IntegrityViolation("P7_DUPLICATE_CANDIDATE_ID", candidate_id, ErrorContext("P7.S8.M01"))
        seen.add(candidate_id)
        by_group.setdefault(item.rankable.comparison_group_id, []).append(item)
    ranked_all: list[RankedStrategyRecord] = []
    ties_all: list[RankingTieRecord] = []
    summaries: list[RankingGroupSummaryRecord] = []
    for group_id in sorted(by_group):
        ranked, ties = _rank_group(by_group[group_id], policy)
        ranked_all.extend(ranked)
        ties_all.extend(ties)
        scores = [item.diversity_adjusted_score for item in ranked]
        first = ranked[0] if ranked else None
        summaries.append(RankingGroupSummaryRecord(
            cycle_id=first.cycle_id if first else by_group[group_id][0].rankable.cycle_id,
            decision_time=first.decision_time if first else by_group[group_id][0].rankable.decision_time,
            comparison_group_id=group_id,
            candidate_count=len(ranked),
            tie_count=len(ties),
            top_candidate_id=first.candidate_id if first else None,
            minimum_score=min(scores) if scores else None,
            maximum_score=max(scores) if scores else None,
            ranking_policy_version=policy.policy_id,
            lineage_id=first.lineage_id if first else by_group[group_id][0].strategy.strategy_lineage_id,
        ))
    return RankingOutputs(tuple(ranked_all), tuple(ties_all), tuple(summaries))
