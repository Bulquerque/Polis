"""P9.S8.M03 — ranking, dominance, confidence, and abstention attribution."""

from __future__ import annotations

from .errors import AttributionInvariantError

from itertools import combinations
from math import log2
from statistics import fmean

from pydantic import Field, model_validator
from scipy.stats import spearmanr

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    EvidenceClass,
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import AttributionQuality


class RankedCandidate(StrictModel):
    group_id: NonEmptyStr
    candidate_id: NonEmptyStr
    predicted_rank: int = Field(ge=1)
    predicted_score: float
    realized_utility: float | None = None
    evidence_class: EvidenceClass
    eligible: bool = True
    pre_blocked: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    dominates_candidate_ids: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_candidate(self) -> "RankedCandidate":
        if self.pre_blocked and self.eligible:
            raise ValueError("pre-blocked candidate cannot be eligible")
        return self


class RankingGroup(StrictModel):
    group_id: NonEmptyStr
    candidates: tuple[RankedCandidate, ...]
    abstained: bool = False
    abstention_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_group(self) -> "RankingGroup":
        if any(item.group_id != self.group_id for item in self.candidates):
            raise ValueError("candidate group_id mismatch")
        ids = [item.candidate_id for item in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate in ranking group")
        return self


class RankingAttributionPolicy(StrictModel):
    top_k: int = Field(default=3, ge=1)
    utility_tie_tolerance: float = Field(default=1e-12, ge=0.0)
    false_abstention_utility_threshold: float = Field(default=0.0)
    minimum_candidates: int = Field(default=2, ge=2)


class RankingGroupReport(StrictModel):
    group_id: NonEmptyStr
    eligible_count: int = Field(ge=0)
    observable_count: int = Field(ge=0)
    pairwise_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    spearman_correlation: float | None = Field(default=None, ge=-1.0, le=1.0)
    ndcg_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    ranking_regret: float | None = Field(default=None, ge=0.0)
    dominance_violations: tuple[NonEmptyStr, ...]
    abstention_state: NonEmptyStr
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...] = ()


class RankingAttributionResult(StrictModel):
    groups: tuple[RankingGroupReport, ...]
    mean_pairwise_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_ndcg_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    total_ranking_regret: float | None = Field(default=None, ge=0.0)
    aggregate_pnl_effect: float | None
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def evaluate_ranking(
    groups: tuple[RankingGroup, ...],
    policy: RankingAttributionPolicy,
) -> RankingAttributionResult:
    """Evaluate only eligible, outcome-observable candidates within each group."""

    reports = tuple(_evaluate_group(group, policy) for group in groups)
    pairwise = [item.pairwise_accuracy for item in reports if item.pairwise_accuracy is not None]
    ndcg = [item.ndcg_at_k for item in reports if item.ndcg_at_k is not None]
    regrets = [item.ranking_regret for item in reports if item.ranking_regret is not None]
    reasons = sorted({code for item in reports for code in item.reason_codes})
    quality = _aggregate_quality(item.quality for item in reports)
    total_regret = sum(regrets) if regrets else None
    payload = {
        "groups": [item.model_dump(mode="json") for item in reports],
        "mean_pairwise": fmean(pairwise) if pairwise else None,
        "mean_ndcg": fmean(ndcg) if ndcg else None,
        "total_regret": total_regret,
        "quality": quality,
        "reason_codes": reasons,
    }
    return RankingAttributionResult(
        groups=reports,
        mean_pairwise_accuracy=fmean(pairwise) if pairwise else None,
        mean_ndcg_at_k=fmean(ndcg) if ndcg else None,
        total_ranking_regret=total_regret,
        aggregate_pnl_effect=-total_regret if total_regret is not None else None,
        quality=quality,
        reason_codes=tuple(reasons),
        result_sha256=payload_sha256(payload),
    )


def _evaluate_group(group: RankingGroup, policy: RankingAttributionPolicy) -> RankingGroupReport:
    candidates = [
        item
        for item in group.candidates
        if item.eligible and not item.pre_blocked and item.realized_utility is not None
    ]
    reasons: set[str] = set()
    if len(candidates) < policy.minimum_candidates:
        reasons.add("P9_ATTRIBUTION_RANKING_OUTCOME_UNOBSERVABLE")
        return RankingGroupReport(
            group_id=group.group_id,
            eligible_count=sum(item.eligible for item in group.candidates),
            observable_count=len(candidates),
            dominance_violations=(),
            abstention_state=_abstention_state(group, candidates, policy),
            quality=AttributionQuality.INSUFFICIENT_EVIDENCE,
            reason_codes=tuple(sorted(reasons)),
        )

    pairwise_correct = 0
    pairwise_total = 0
    for first, second in combinations(candidates, 2):
        if first.realized_utility is None or second.realized_utility is None:
            raise AttributionInvariantError("rankable candidates require realized utility")
        utility_delta = first.realized_utility - second.realized_utility
        if abs(utility_delta) <= policy.utility_tie_tolerance:
            continue
        predicted_delta = second.predicted_rank - first.predicted_rank
        pairwise_correct += int(predicted_delta * utility_delta > 0.0)
        pairwise_total += 1
    pairwise_accuracy = pairwise_correct / pairwise_total if pairwise_total else None

    predicted_order = sorted(candidates, key=lambda item: (item.predicted_rank, item.candidate_id))
    predicted_ranks = [item.predicted_rank for item in candidates]
    utilities = [float(item.realized_utility) for item in candidates]
    correlation_result = spearmanr(predicted_ranks, [-value for value in utilities])
    correlation = float(correlation_result.statistic)
    if correlation != correlation:  # NaN from constant inputs
        correlation = None

    ndcg = _ndcg(predicted_order, policy.top_k)
    best = max(candidates, key=lambda item: float(item.realized_utility))
    chosen = predicted_order[0]
    regret = max(0.0, float(best.realized_utility) - float(chosen.realized_utility))
    violations = _dominance_violations(candidates, chosen.candidate_id)
    if violations:
        reasons.add("P9_ATTRIBUTION_DOMINANCE_DIRECTION_INVALID")
    abstention_state = _abstention_state(group, candidates, policy)
    if abstention_state == "FALSE_ABSTENTION":
        reasons.add("P9_ATTRIBUTION_FALSE_ABSTENTION")
    quality = AttributionQuality.LIMITED if reasons else AttributionQuality.QUALIFIED
    return RankingGroupReport(
        group_id=group.group_id,
        eligible_count=sum(item.eligible for item in group.candidates),
        observable_count=len(candidates),
        pairwise_accuracy=pairwise_accuracy,
        spearman_correlation=correlation,
        ndcg_at_k=ndcg,
        ranking_regret=regret,
        dominance_violations=tuple(violations),
        abstention_state=abstention_state,
        quality=quality,
        reason_codes=tuple(sorted(reasons)),
    )


def _ndcg(ordered: list[RankedCandidate], top_k: int) -> float | None:
    values = [float(item.realized_utility) for item in ordered]
    if not values:
        return None
    minimum = min(values)
    relevance = [value - minimum for value in values]
    ideal = sorted(relevance, reverse=True)
    k = min(top_k, len(relevance))
    dcg = sum((2.0**relevance[index] - 1.0) / log2(index + 2.0) for index in range(k))
    idcg = sum((2.0**ideal[index] - 1.0) / log2(index + 2.0) for index in range(k))
    return dcg / idcg if idcg > 0.0 else 1.0


def _dominance_violations(candidates: list[RankedCandidate], chosen_id: str) -> list[str]:
    return sorted(
        item.candidate_id
        for item in candidates
        if chosen_id in set(item.dominates_candidate_ids)
    )


def _abstention_state(
    group: RankingGroup,
    candidates: list[RankedCandidate],
    policy: RankingAttributionPolicy,
) -> str:
    if not group.abstained:
        return "NOT_ABSTAINED"
    if not candidates:
        return "ABSTENTION_NOT_IDENTIFIABLE"
    best_utility = max(float(item.realized_utility) for item in candidates)
    if best_utility > policy.false_abstention_utility_threshold:
        return "FALSE_ABSTENTION"
    return "PRUDENT_ABSTENTION"


def _aggregate_quality(values: object) -> AttributionQuality:
    items = tuple(values)  # type: ignore[arg-type]
    if not items:
        return AttributionQuality.INSUFFICIENT_EVIDENCE
    if AttributionQuality.INVALID in items:
        return AttributionQuality.INVALID
    if AttributionQuality.NOT_IDENTIFIABLE in items:
        return AttributionQuality.NOT_IDENTIFIABLE
    if AttributionQuality.INSUFFICIENT_EVIDENCE in items:
        return AttributionQuality.INSUFFICIENT_EVIDENCE
    if AttributionQuality.LIMITED in items:
        return AttributionQuality.LIMITED
    return AttributionQuality.QUALIFIED
