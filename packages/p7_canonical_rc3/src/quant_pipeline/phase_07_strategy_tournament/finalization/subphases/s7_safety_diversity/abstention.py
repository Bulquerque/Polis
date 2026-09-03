"""Selective rankability gate with candidate conservation."""
from __future__ import annotations

from collections import defaultdict

from ...boundary.config import AbstentionPolicy
from ...domain.models import Candidate


def candidate_abstention_reasons(candidate: Candidate, policy: AbstentionPolicy) -> tuple[str, ...]:
    reasons: list[str] = []
    if candidate.score_confidence is None:
        reasons.append("P7_CONFIDENCE_UNAVAILABLE")
    elif candidate.score_confidence < policy.minimum_confidence:
        reasons.append("P7_CONFIDENCE_BELOW_MINIMUM")
    if candidate.interval_lower is not None and candidate.interval_upper is not None:
        if candidate.interval_upper - candidate.interval_lower > policy.maximum_score_interval_width:
            reasons.append("P7_SCORE_UNCERTAINTY_TOO_WIDE")
    if candidate.model_disagreement is not None and candidate.model_disagreement > policy.maximum_model_disagreement:
        reasons.append("P7_MODEL_DISAGREEMENT_HIGH")
    if candidate.calibration_status not in policy.accepted_calibration_statuses:
        reasons.append("P7_CALIBRATION_INSUFFICIENT")
    if candidate.ood_severity in policy.moderate_ood_values:
        reasons.append("P7_MODERATE_OOD_ABSTAIN")
    return tuple(sorted(set(reasons)))


def apply_group_coverage(
    candidate_reasons: dict[str, tuple[str, ...]],
    candidates: tuple[Candidate, ...],
    blocked_ids: frozenset[str],
    policy: AbstentionPolicy,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    by_group: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_group[candidate.comparison_group_id].append(candidate)
    group_reasons: dict[str, tuple[str, ...]] = {}
    updated = dict(candidate_reasons)
    for group_id, members in sorted(by_group.items()):
        eligible = [item for item in members if item.candidate_id not in blocked_ids]
        provisional = [item for item in eligible if not updated.get(item.candidate_id)]
        coverage = len(provisional) / len(eligible) if eligible else 0.0
        reasons: list[str] = []
        if not provisional:
            reasons.append("P7_NO_RANKABLE_CANDIDATES")
        elif len(provisional) < policy.minimum_group_rankable_count or coverage < policy.minimum_group_rankable_fraction:
            reasons.append("P7_GROUP_COVERAGE_INSUFFICIENT")
            for candidate in provisional:
                updated[candidate.candidate_id] = ("P7_GROUP_COVERAGE_INSUFFICIENT",)
        confidence_reasons = {"P7_CONFIDENCE_BELOW_MINIMUM", "P7_CONFIDENCE_UNAVAILABLE"}
        if eligible and all(confidence_reasons.intersection(updated.get(item.candidate_id, ())) for item in eligible):
            reasons.append("P7_ALL_CANDIDATES_LOW_CONFIDENCE")
        group_reasons[group_id] = tuple(sorted(set(reasons)))
    return updated, group_reasons
