"""Transform physical belief states into explicit target payoff records."""

from __future__ import annotations

from decimal import Decimal

from ..domain.enums import (
    CalculationStatus,
    ObjectiveFamily,
    TargetPayoffMode,
)
from ..domain.market_price import reference_spot
from ..domain.models import (
    MarketBeliefState,
    MarketImpliedState,
    TargetPayoffRecord,
    UnderlyingObservation,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id

ZERO = Decimal("0")
ONE = Decimal("1")
TargetValues = tuple[tuple[Decimal, ...], CalculationStatus, str | None]


def transform_beliefs_to_targets(
    beliefs: tuple[MarketBeliefState, ...],
    implied_states: tuple[MarketImpliedState, ...],
    underlyings: tuple[UnderlyingObservation, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[TargetPayoffRecord, ...]:
    """Build one target payoff per configured objective family."""
    implied_by_underlying = {
        item.underlying_id: item
        for item in implied_states
    }
    spot_by_underlying = {
        item.underlying_id: _spot(item)
        for item in underlyings
    }
    output: list[TargetPayoffRecord] = []
    for belief in beliefs:
        output.extend(
            _belief_targets(
                belief,
                implied_by_underlying.get(belief.underlying_id),
                spot_by_underlying[belief.underlying_id],
                configuration,
            )
        )
    return tuple(output)


def _belief_targets(
    belief: MarketBeliefState,
    implied: MarketImpliedState | None,
    spot: Decimal,
    configuration: Phase6RunConfiguration,
) -> list[TargetPayoffRecord]:
    if not belief.scenarios:
        return []
    scenarios = tuple(
        sorted(
            belief.scenarios,
            key=lambda item: item.terminal_underlying_price,
        )
    )
    grid = tuple(item.terminal_underlying_price for item in scenarios)
    probabilities = tuple(item.probability for item in scenarios)
    output = []
    for objective in configuration.target_payoff.objective_families:
        mode = _mode_for_objective(objective, configuration)
        raw, status, reason = _raw_target(
            mode,
            objective,
            grid,
            probabilities,
            spot,
            implied,
            configuration,
        )
        output.append(
            _target_record(
                belief,
                implied,
                objective,
                mode,
                grid,
                probabilities,
                raw,
                status,
                reason,
                configuration,
            )
        )
    return output


def _target_record(
    belief: MarketBeliefState,
    implied: MarketImpliedState | None,
    objective: ObjectiveFamily,
    mode: TargetPayoffMode,
    grid: tuple[Decimal, ...],
    probabilities: tuple[Decimal, ...],
    raw: tuple[Decimal, ...],
    status: CalculationStatus,
    reason: str | None,
    configuration: Phase6RunConfiguration,
) -> TargetPayoffRecord:
    identifier = stable_id(
        "target-payoff",
        belief.belief_state_id,
        objective,
        mode,
        raw,
    )
    implied_id = None if implied is None else implied.market_implied_state_id
    return TargetPayoffRecord(
        target_payoff_id=identifier,
        underlying_id=belief.underlying_id,
        decision_time=belief.decision_time,
        horizon_days=belief.horizon_days,
        objective_family=objective,
        mode=mode,
        terminal_state_grid=grid,
        raw_target_payoff=raw,
        regularized_target_payoff=raw,
        scenario_probabilities=probabilities,
        cost_budget=configuration.risk.maximum_entry_cost,
        risk_budget=configuration.risk.maximum_loss_limit,
        complexity_budget=configuration.budgets.max_legs,
        belief_state_id=belief.belief_state_id,
        ambiguity_set_id=belief.ambiguity_set_id,
        market_implied_state_id=implied_id,
        confidence=belief.confidence,
        status=status,
        reason_code=reason,
    )


def _mode_for_objective(
    objective: ObjectiveFamily,
    configuration: Phase6RunConfiguration,
) -> TargetPayoffMode:
    preferred = {
        ObjectiveFamily.TAIL_HEDGE: TargetPayoffMode.TAIL_HEDGE,
        ObjectiveFamily.RANGE: TargetPayoffMode.RANGE_EXPRESSION,
    }.get(objective, TargetPayoffMode.SCENARIO_WEIGHTED)
    if preferred in configuration.target_payoff.modes:
        return preferred
    return configuration.target_payoff.modes[0]


def _raw_target(
    mode: TargetPayoffMode,
    objective: ObjectiveFamily,
    grid: tuple[Decimal, ...],
    probabilities: tuple[Decimal, ...],
    spot: Decimal,
    implied: MarketImpliedState | None,
    configuration: Phase6RunConfiguration,
) -> TargetValues:
    scale = max(spot, ONE)
    if mode is TargetPayoffMode.BELIEF_RATIO:
        return _belief_ratio_target(
            grid,
            probabilities,
            implied,
            configuration,
        )
    if mode is TargetPayoffMode.TAIL_HEDGE:
        raw = tuple(max(spot - value, ZERO) / scale for value in grid)
    elif mode is TargetPayoffMode.RANGE_EXPRESSION:
        raw = _range_target(grid, spot)
    elif mode is TargetPayoffMode.EXPECTED_UTILITY:
        risk_aversion = configuration.target_payoff.risk_aversion
        raw = tuple(_utility(value / scale, risk_aversion) for value in grid)
    else:
        raw = _objective_target(objective, grid, spot, scale)
    return raw, CalculationStatus.AVAILABLE, None


def _objective_target(
    objective: ObjectiveFamily,
    grid: tuple[Decimal, ...],
    spot: Decimal,
    scale: Decimal,
) -> tuple[Decimal, ...]:
    if objective is ObjectiveFamily.DIRECTIONAL_DOWN:
        return tuple(max(spot - value, ZERO) / scale for value in grid)
    if objective in {
        ObjectiveFamily.LONG_VOLATILITY,
        ObjectiveFamily.POSITIVE_CONVEXITY,
    }:
        return tuple(abs(value - spot) / scale for value in grid)
    if objective is ObjectiveFamily.SHORT_VOLATILITY_DEFINED_RISK:
        return tuple(max(ONE - abs(value - spot) / scale, ZERO) for value in grid)
    return tuple(max(value - spot, ZERO) / scale for value in grid)


def _range_target(
    grid: tuple[Decimal, ...],
    spot: Decimal,
) -> tuple[Decimal, ...]:
    radius = max((max(grid) - min(grid)) / Decimal("4"), ONE)
    return tuple(max(ONE - abs(value - spot) / radius, ZERO) for value in grid)


def _belief_ratio_target(
    grid: tuple[Decimal, ...],
    probabilities: tuple[Decimal, ...],
    implied: MarketImpliedState | None,
    configuration: Phase6RunConfiguration,
) -> TargetValues:
    if implied is None or implied.status is not CalculationStatus.AVAILABLE:
        return (
            tuple(ZERO for _ in grid),
            CalculationStatus.UNAVAILABLE,
            "P6_MARKET_IMPLIED_STATE_UNAVAILABLE",
        )
    epsilon = configuration.target_payoff.epsilon
    market = _interpolate_probabilities(
        grid,
        implied.state_grid,
        implied.risk_neutral_probabilities,
        epsilon,
    )
    raw = tuple(
        physical / max(risk_neutral, epsilon)
        for physical, risk_neutral in zip(probabilities, market)
    )
    return raw, CalculationStatus.AVAILABLE, None


def _interpolate_probabilities(
    target_grid: tuple[Decimal, ...],
    source_grid: tuple[Decimal, ...],
    source_probabilities: tuple[Decimal, ...],
    epsilon: Decimal,
) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    for target in target_grid:
        index = min(
            range(len(source_grid)),
            key=lambda item: abs(source_grid[item] - target),
        )
        values.append(max(source_probabilities[index], epsilon))
    total = sum(values, ZERO)
    return tuple(value / total for value in values)


def _utility(value: Decimal, risk_aversion: Decimal) -> Decimal:
    return value - risk_aversion * value * value / Decimal("2")


def _spot(observation: UnderlyingObservation) -> Decimal:
    for value in (observation.last, observation.ask, observation.bid):
        if value is not None:
            return value
    raise ValueError("underlying observation has no price")
