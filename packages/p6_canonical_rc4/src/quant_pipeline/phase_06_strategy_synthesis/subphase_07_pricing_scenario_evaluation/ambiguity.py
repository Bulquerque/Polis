"""Robust evaluation across explicit alternative probability measures."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..domain.enums import CapabilityStatus
from ..domain.models import (
    MarketBeliefState,
    RobustAmbiguityEvaluation,
    ScenarioEvaluation,
    StrategyCandidate,
)
from ..domain.statistics import expected_shortfall
from ..foundation.configuration import Phase6RunConfiguration

ZERO = Decimal("0")


def ambiguity_records(
    scenarios: tuple[ScenarioEvaluation, ...],
    beliefs: tuple[MarketBeliefState, ...],
    candidates: tuple[StrategyCandidate, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[RobustAmbiguityEvaluation, ...]:
    """Evaluate only ambiguity sets explicitly supplied by the belief bundle."""
    candidate_by_id = {item.candidate_id: item for item in candidates}
    belief_by_underlying = {
        item.underlying_id: item
        for item in beliefs
    }
    grouped: dict[str, list[ScenarioEvaluation]] = defaultdict(list)
    for scenario in scenarios:
        grouped[scenario.candidate_id].append(scenario)
    output = []
    for candidate_id, values in sorted(grouped.items()):
        candidate = candidate_by_id[candidate_id]
        belief = belief_by_underlying[candidate.underlying_id]
        output.append(
            _evaluate_candidate(
                candidate_id,
                values,
                belief,
                configuration,
            )
        )
    return tuple(output)


def _evaluate_candidate(
    candidate_id,
    values,
    belief,
    configuration,
) -> RobustAmbiguityEvaluation:
    ordered = sorted(values, key=lambda item: item.scenario_id)
    pnl = [item.scenario_pnl for item in ordered]
    nominal_probabilities = [
        item.scenario_probability
        for item in ordered
    ]
    nominal = _expectation(pnl, nominal_probabilities)
    if (
        belief.ambiguity_capability is not CapabilityStatus.AVAILABLE
        or not belief.ambiguity_probabilities
    ):
        return _unavailable(candidate_id, belief, nominal)
    alternatives = [
        tuple(probabilities)
        for probabilities in belief.ambiguity_probabilities
    ]
    expected = [_expectation(pnl, probabilities) for probabilities in alternatives]
    cvars = [
        expected_shortfall(pnl, list(probabilities))
        for probabilities in alternatives
    ]
    utilities = [
        _utility(pnl, probabilities, configuration)
        for probabilities in alternatives
    ]
    worst = min(expected)
    return RobustAmbiguityEvaluation(
        candidate_id=candidate_id,
        status=CapabilityStatus.AVAILABLE,
        nominal_expected_payoff=nominal,
        worst_case_expected_payoff=worst,
        worst_case_expected_utility=min(utilities),
        worst_case_cvar=max(cvars),
        ambiguity_regret=nominal - worst,
        distribution_sensitivity=max(expected) - min(expected),
        ambiguity_set_id=belief.ambiguity_set_id,
    )


def _unavailable(candidate_id, belief, nominal):
    return RobustAmbiguityEvaluation(
        candidate_id=candidate_id,
        status=CapabilityStatus.UNAVAILABLE,
        nominal_expected_payoff=nominal,
        worst_case_expected_payoff=None,
        worst_case_expected_utility=None,
        worst_case_cvar=None,
        ambiguity_regret=None,
        distribution_sensitivity=None,
        ambiguity_set_id=belief.ambiguity_set_id,
        reason_code="P6_AMBIGUITY_SET_UNAVAILABLE",
    )


def _expectation(values, probabilities):
    return sum(
        (value * probability for value, probability in zip(values, probabilities)),
        ZERO,
    )


def _utility(values, probabilities, configuration):
    mean = _expectation(values, probabilities)
    variance = sum(
        (
            probability * (value - mean) ** 2
            for value, probability in zip(values, probabilities)
        ),
        ZERO,
    )
    risk_aversion = configuration.target_payoff.risk_aversion
    return mean - risk_aversion * variance / Decimal("2")
