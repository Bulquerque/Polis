"""Build terminal rankability states and group reports."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ...boundary.config import AbstentionPolicy
from ...boundary.outputs import (
    AbstainedRecord,
    BlockedRecord,
    DiversityAdjustedScoreRecord,
    GroupRankabilityRecord,
    RankableRecord,
)
from ...domain.models import Candidate
from ...errors import ErrorContext, InternalInvariantViolation
from .abstention import apply_group_coverage, candidate_abstention_reasons


@dataclass(frozen=True, slots=True)
class RankabilityOutputs:
    rankable: tuple[RankableRecord, ...]
    abstained: tuple[AbstainedRecord, ...]
    blocked: tuple[BlockedRecord, ...]
    group_reports: tuple[GroupRankabilityRecord, ...]
    reason_codes: tuple[str, ...]


def _validate_safety_partition(
    candidates: tuple[Candidate, ...], eligible_ids: set[str], blocked_map: dict[str, BlockedRecord]
) -> None:
    if eligible_ids & set(blocked_map):
        raise InternalInvariantViolation(
            "P7_TERMINAL_STATE_OVERLAP", "candidate is both eligible and blocked", ErrorContext("P7.S7.M04")
        )
    all_ids = {item.candidate_id for item in candidates}
    if eligible_ids | set(blocked_map) != all_ids:
        raise InternalInvariantViolation(
            "P7_CANDIDATE_CONSERVATION_FAILED", "safety outputs do not conserve candidates", ErrorContext("P7.S7.M04")
        )


def _candidate_terminal_records(
    candidates: tuple[Candidate, ...],
    eligible_ids: set[str],
    blocked_map: dict[str, BlockedRecord],
    adjusted: dict[str, DiversityAdjustedScoreRecord],
    policy: AbstentionPolicy,
) -> tuple[list[RankableRecord], list[AbstainedRecord], list[str], dict[str, tuple[str, ...]]]:
    reason_map = {
        candidate.candidate_id: candidate_abstention_reasons(candidate, policy)
        for candidate in candidates
        if candidate.candidate_id in eligible_ids
    }
    reason_map, group_reasons = apply_group_coverage(reason_map, candidates, frozenset(blocked_map), policy)
    rankable: list[RankableRecord] = []
    abstained: list[AbstainedRecord] = []
    emitted_reasons: list[str] = []
    by_id = {item.candidate_id: item for item in candidates}
    for candidate_id in sorted(eligible_ids):
        candidate = by_id[candidate_id]
        reasons = reason_map[candidate_id]
        emitted_reasons.extend(reasons)
        if reasons:
            abstained.append(_abstained_record(candidate, reasons, policy))
        else:
            rankable.append(_rankable_record(candidate, adjusted[candidate_id], policy))
    return rankable, abstained, emitted_reasons, group_reasons


def _rankable_record(
    candidate: Candidate, adjusted: DiversityAdjustedScoreRecord, policy: AbstentionPolicy
) -> RankableRecord:
    if adjusted.diversity_adjusted_score is None:
        context = ErrorContext("P7.S7.M04", candidate_ids=(candidate.candidate_id,))
        raise InternalInvariantViolation("P7_RANKABLE_SCORE_MISSING", candidate.candidate_id, context)
    required = (
        candidate.hybrid_score,
        candidate.robust_score,
        candidate.execution_quality,
        candidate.pareto_tier,
        candidate.score_confidence,
    )
    if any(value is None for value in required) or not candidate.leg_ids:
        context = ErrorContext("P7.S7.M04", candidate_ids=(candidate.candidate_id,))
        raise InternalInvariantViolation("P7_RANKING_DIMENSION_MISSING", candidate.candidate_id, context)
    return RankableRecord(
        cycle_id=candidate.cycle_id,
        decision_time=candidate.decision_time,
        comparison_group_id=candidate.comparison_group_id,
        candidate_id=candidate.candidate_id,
        hybrid_score=float(candidate.hybrid_score),
        diversity_penalty=adjusted.diversity_penalty,
        diversity_adjusted_score=adjusted.diversity_adjusted_score,
        score_confidence=float(candidate.score_confidence),
        robustness_stage=float(candidate.robust_score),
        execution_quality_stage=float(candidate.execution_quality),
        leg_count=len(candidate.leg_ids),
        pareto_tier=int(candidate.pareto_tier),
        model_id=candidate.model_id,
        score_semantics_version=candidate.score_semantics_version,
        calibration_status=candidate.calibration_status,
        calibration_version=candidate.calibration_version,
        ood_severity=candidate.ood_severity,
        model_disagreement=candidate.model_disagreement,
        policy_version=policy.policy_id,
        lineage_id=candidate.lineage_id,
    )


def _abstained_record(candidate: Candidate, reasons: tuple[str, ...], policy: AbstentionPolicy) -> AbstainedRecord:
    return AbstainedRecord(
        cycle_id=candidate.cycle_id,
        decision_time=candidate.decision_time,
        comparison_group_id=candidate.comparison_group_id,
        candidate_id=candidate.candidate_id,
        reason_codes=reasons,
        confidence=candidate.score_confidence,
        evidence_ids=(candidate.calibration_version, candidate.model_id),
        policy_version=policy.policy_id,
        lineage_id=candidate.lineage_id,
    )


def _group_reports(
    candidates: tuple[Candidate, ...],
    rankable: list[RankableRecord],
    abstained: list[AbstainedRecord],
    blocked: tuple[BlockedRecord, ...],
    group_reasons: dict[str, tuple[str, ...]],
    policy: AbstentionPolicy,
    lineage_id: str,
) -> tuple[GroupRankabilityRecord, ...]:
    received: dict[str, int] = defaultdict(int)
    rankable_count: dict[str, int] = defaultdict(int)
    abstained_count: dict[str, int] = defaultdict(int)
    blocked_count: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        received[candidate.comparison_group_id] += 1
    for item in rankable:
        rankable_count[item.comparison_group_id] += 1
    for item in abstained:
        abstained_count[item.comparison_group_id] += 1
    for item in blocked:
        blocked_count[item.comparison_group_id] += 1
    first = candidates[0] if candidates else None
    if first is None:
        return ()
    return tuple(
        GroupRankabilityRecord(
            cycle_id=first.cycle_id,
            decision_time=first.decision_time,
            comparison_group_id=group_id,
            received_count=count,
            rankable_count=rankable_count[group_id],
            abstained_count=abstained_count[group_id],
            blocked_count=blocked_count[group_id],
            coverage=rankable_count[group_id] / count,
            group_reason_codes=group_reasons.get(group_id, ()),
            policy_version=policy.policy_id,
            lineage_id=lineage_id,
        )
        for group_id, count in sorted(received.items())
    )


def build_rankability(
    candidates: tuple[Candidate, ...],
    eligible_ids: set[str],
    blocked_map: dict[str, BlockedRecord],
    adjusted: dict[str, DiversityAdjustedScoreRecord],
    policy: AbstentionPolicy,
    lineage_id: str,
) -> RankabilityOutputs:
    _validate_safety_partition(candidates, eligible_ids, blocked_map)
    rankable, abstained, reasons, group_reasons = _candidate_terminal_records(
        candidates, eligible_ids, blocked_map, adjusted, policy
    )
    blocked = tuple(blocked_map[candidate_id] for candidate_id in sorted(blocked_map))
    reports = _group_reports(candidates, rankable, abstained, blocked, group_reasons, policy, lineage_id)
    if len(rankable) + len(abstained) + len(blocked) != len(candidates):
        raise InternalInvariantViolation(
            "P7_CANDIDATE_CONSERVATION_FAILED", "terminal state count mismatch", ErrorContext("P7.S7.M04")
        )
    return RankabilityOutputs(tuple(rankable), tuple(abstained), blocked, reports, tuple(reasons))
