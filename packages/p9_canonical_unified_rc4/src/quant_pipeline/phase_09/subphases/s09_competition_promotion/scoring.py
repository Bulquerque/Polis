from __future__ import annotations

from collections.abc import Mapping

from .enums import OptimizationDirection
from .models.frontier import ConfigurationEvaluationCard
from .models.policy import CompetitionObjectivePolicy, SoftPenaltyRule


def oriented(value: float, direction: OptimizationDirection) -> float:
    return value if direction == OptimizationDirection.MAXIMIZE else -value


def penalty_value(value: float, rule: SoftPenaltyRule) -> float:
    if rule.direction == OptimizationDirection.MINIMIZE:
        excess = max(0.0, value - rule.reference_value)
    else:
        excess = max(0.0, rule.reference_value - value)
    return min(rule.cap, rule.weight * excess / rule.scale)


def configuration_utility(
    card: ConfigurationEvaluationCard,
    policy: CompetitionObjectivePolicy,
) -> float:
    metrics = card.metric_map()
    if policy.primary_score_id not in metrics:
        raise KeyError(f"missing primary score metric {policy.primary_score_id!r}")
    utility = oriented(metrics[policy.primary_score_id], policy.primary_direction)
    for rule in policy.soft_penalties:
        if rule.metric_id not in metrics:
            raise KeyError(f"missing penalty metric {rule.metric_id!r}")
        utility -= penalty_value(metrics[rule.metric_id], rule)
    return utility


def tie_break_key(
    metrics: Mapping[str, float],
    policy: CompetitionObjectivePolicy,
) -> tuple[float, ...]:
    ordered = sorted(policy.tie_breakers, key=lambda item: item.priority)
    return tuple(oriented(metrics[item.metric_id], item.direction) for item in ordered)
