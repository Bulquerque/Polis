"""P9.S3.M07 — conservative provisional trial comparison.

This module deliberately does not claim the formal Hansen-Lunde-Nason MCS.
Final dependent-bootstrap and multiple-testing qualification belongs to P9.S5.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from itertools import combinations

from .common import content_sha256
from .comparison_models import (
    ComparisonPolicy,
    ConfigurationLineage,
    EquivalenceGroup,
    PairwiseComparison,
    ProvisionalModelConfidenceSet,
    TrialComparisonResult,
)
from .reason_codes import ReasonCode
from .scoring_models import ComparisonLossRecord, ConfigurationScoreAggregate


def compare_trials(
    aggregates: tuple[ConfigurationScoreAggregate, ...],
    losses: tuple[ComparisonLossRecord, ...],
    lineage: tuple[ConfigurationLineage, ...],
    policy: ComparisonPolicy,
    *,
    cohort_id: str,
) -> TrialComparisonResult:
    selected_aggregates = {
        item.configuration_id: item
        for item in aggregates
        if item.cohort_id == cohort_id and item.status == "QUALIFIED"
    }
    lineage_map = {item.configuration_id: item for item in lineage}
    if set(selected_aggregates) - set(lineage_map):
        raise ValueError("missing lineage for one or more configurations")

    equivalence_map: dict[str, list[str]] = defaultdict(list)
    for configuration_id in sorted(selected_aggregates):
        equivalence_map[lineage_map[configuration_id].economic_fingerprint].append(configuration_id)
    equivalence_groups = tuple(
        EquivalenceGroup(economic_fingerprint=fingerprint, configuration_ids=tuple(ids))
        for fingerprint, ids in sorted(equivalence_map.items())
    )

    representative_ids = tuple(ids[0] for _, ids in sorted(equivalence_map.items()))
    loss_map: dict[str, dict[str, Decimal]] = defaultdict(dict)
    for item in losses:
        if item.cohort_id == cohort_id and item.configuration_id in representative_ids:
            loss_map[item.configuration_id][item.unit_id] = item.loss

    pairwise: list[PairwiseComparison] = []
    dominated: set[str] = set()
    reasons: set[str] = {ReasonCode.PROVISIONAL_ONLY.value}
    if len(representative_ids) < 2:
        reasons.add(ReasonCode.INSUFFICIENT_CONFIGURATIONS.value)
    for left, right in combinations(representative_ids, 2):
        common = sorted(set(loss_map[left]) & set(loss_map[right]))
        if len(common) < policy.minimum_common_units:
            pairwise.append(
                PairwiseComparison(
                    configuration_a=left,
                    configuration_b=right,
                    common_unit_count=len(common),
                    mean_loss_a=None,
                    mean_loss_b=None,
                    a_dominates_b=False,
                    b_dominates_a=False,
                    comparable=False,
                )
            )
            reasons.add(ReasonCode.COMPARISON_NOT_IDENTIFIABLE.value)
            continue
        left_losses = [loss_map[left][unit] for unit in common]
        right_losses = [loss_map[right][unit] for unit in common]
        mean_left = sum(left_losses, Decimal("0")) / Decimal(len(common))
        mean_right = sum(right_losses, Decimal("0")) / Decimal(len(common))
        worst_left = max(left_losses)
        worst_right = max(right_losses)
        a_dominates = (
            mean_left <= mean_right + policy.dominance_tolerance
            and worst_left <= worst_right + policy.dominance_tolerance
            and (
                mean_left < mean_right - policy.dominance_tolerance
                or worst_left < worst_right - policy.dominance_tolerance
            )
        )
        b_dominates = (
            mean_right <= mean_left + policy.dominance_tolerance
            and worst_right <= worst_left + policy.dominance_tolerance
            and (
                mean_right < mean_left - policy.dominance_tolerance
                or worst_right < worst_left - policy.dominance_tolerance
            )
        )
        if a_dominates:
            dominated.add(right)
        if b_dominates:
            dominated.add(left)
        pairwise.append(
            PairwiseComparison(
                configuration_a=left,
                configuration_b=right,
                common_unit_count=len(common),
                mean_loss_a=mean_left,
                mean_loss_b=mean_right,
                a_dominates_b=a_dominates,
                b_dominates_a=b_dominates,
                comparable=True,
            )
        )

    non_dominated = tuple(sorted(set(representative_ids) - dominated))
    if not non_dominated:
        reasons.add(ReasonCode.INSUFFICIENT_CONFIGURATIONS.value)
        provisional_ids: tuple[str, ...] = ()
    else:
        means = {
            configuration_id: (
                sum(loss_map[configuration_id].values(), Decimal("0"))
                / Decimal(len(loss_map[configuration_id]))
            )
            for configuration_id in non_dominated
            if loss_map[configuration_id]
        }
        if not means:
            provisional_ids = non_dominated
        else:
            best = min(means.values())
            provisional_ids = tuple(
                sorted(
                    configuration_id
                    for configuration_id, value in means.items()
                    if value <= best + policy.mean_loss_tolerance
                )
            )

    provisional = ProvisionalModelConfidenceSet(
        policy_id=policy.policy_id,
        cohort_id=cohort_id,
        configuration_ids=provisional_ids,
    )
    body = {
        "policy_id": policy.policy_id,
        "cohort_id": cohort_id,
        "pairwise": tuple(pairwise),
        "equivalence_groups": equivalence_groups,
        "non_dominated_configuration_ids": non_dominated,
        "provisional_model_set": provisional,
        "reason_codes": tuple(sorted(reasons)),
    }
    return TrialComparisonResult(**body, content_sha256=content_sha256(body))
