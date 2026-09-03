"""Entry pricing, payoff, Greeks, shape, and scenario evaluation services."""

from __future__ import annotations

from decimal import Decimal

from ..domain.enums import (
    CalculationStatus,
    CapabilityStatus,
    ExerciseStyle,
    InstrumentType,
    Side,
)
from ..domain.greeks import option_greeks
from ..domain.market_price import reference_spot
from ..domain.models import (
    AmbiguityEvaluationRecord,
    CostLiquidityRecord,
    ExecutableQuote,
    GreekState,
    MarketBeliefState,
    ScenarioEvaluation,
    StrategyCandidate,
    StrategyPayoffRecord,
    StrategyShapeRecord,
    UnderlyingObservation,
)
from ..domain.payoff import (
    break_even_points,
    critical_spots,
    right_tail_slope,
    strategy_entry_cash_flow,
    strategy_terminal_pnl,
)
from ..foundation.configuration import Phase6RunConfiguration
from .liquidity import _liquidity_inputs, cost_liquidity

ZERO = Decimal("0")
ONE = Decimal("1")
SECONDS_PER_YEAR = 31_536_000


def payoff_records(
    candidates: tuple[StrategyCandidate, ...],
    underlyings: tuple[UnderlyingObservation, ...],
    costs: tuple[CostLiquidityRecord, ...],
) -> tuple[StrategyPayoffRecord, ...]:
    """Calculate exact terminal payoff records on deterministic critical grids."""
    underlying_by_id = {item.underlying_id: item for item in underlyings}
    cost_by_id = {item.candidate_id: item for item in costs}
    records: list[StrategyPayoffRecord] = []
    for candidate in candidates:
        spot = _spot(underlying_by_id[candidate.underlying_id])
        grid = critical_spots(candidate.legs, spot)
        cost = cost_by_id[candidate.candidate_id]
        transaction_cost = cost.fee_estimate + cost.slippage_estimate
        pnl = tuple(
            strategy_terminal_pnl(candidate.legs, value, transaction_cost)
            for value in grid
        )
        slope = right_tail_slope(candidate.legs)
        finite = slope >= ZERO
        records.append(
            StrategyPayoffRecord(
                candidate_id=candidate.candidate_id,
                spot_grid=grid,
                terminal_pnl=pnl,
                entry_cash_flow=strategy_entry_cash_flow(candidate.legs),
                maximum_loss=max(ZERO, -min(pnl)) if finite else None,
                maximum_gain=max(pnl) if slope == ZERO else None,
                maximum_gain_unbounded=slope > ZERO,
                break_even_points=break_even_points(grid, pnl),
                right_tail_slope=slope,
                payoff_status=(
                    CalculationStatus.AVAILABLE
                    if finite
                    else CalculationStatus.BLOCKED
                ),
            )
        )
    return tuple(records)


def greek_records(
    candidates: tuple[StrategyCandidate, ...],
    quotes: tuple[ExecutableQuote, ...],
    underlyings: tuple[UnderlyingObservation, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[GreekState, ...]:
    """Calculate basic candidate Greeks without hiding unsupported contracts."""
    quote_by_id = {item.contract_id: item for item in quotes}
    underlying_by_id = {item.underlying_id: item for item in underlyings}
    return tuple(
        _candidate_greeks(candidate, quote_by_id, underlying_by_id, configuration)
        for candidate in candidates
    )


def _candidate_greeks(
    candidate: StrategyCandidate,
    quote_by_id: dict[str, ExecutableQuote],
    underlying_by_id: dict[str, UnderlyingObservation],
    configuration: Phase6RunConfiguration,
) -> GreekState:
    spot = _spot(underlying_by_id[candidate.underlying_id])
    totals = [ZERO, ZERO, ZERO, ZERO]
    status = CalculationStatus.AVAILABLE
    for leg in candidate.legs:
        if leg.instrument_type is InstrumentType.UNDERLYING:
            sign = ONE if leg.side is Side.LONG else -ONE
            totals[0] += sign * leg.quantity * leg.multiplier
            continue
        quote = quote_by_id.get(leg.instrument_id)
        if not _greek_inputs_supported(leg, quote):
            status = CalculationStatus.UNAVAILABLE
            break
        years = Decimal(
            str(
                max(
                    (leg.expiration - configuration.decision_time).total_seconds()
                    / SECONDS_PER_YEAR,
                    0,
                )
            )
        )
        values = option_greeks(
            leg,
            spot,
            quote.implied_volatility,
            years,
            configuration.pricing.risk_free_rate,
            configuration.pricing.dividend_yield,
        )
        totals = [left + right for left, right in zip(totals, values)]
    return GreekState(
        candidate_id=candidate.candidate_id,
        delta=totals[0] if status is CalculationStatus.AVAILABLE else None,
        gamma=totals[1] if status is CalculationStatus.AVAILABLE else None,
        vega=totals[2] if status is CalculationStatus.AVAILABLE else None,
        theta=totals[3] if status is CalculationStatus.AVAILABLE else None,
        calculation_method=configuration.pricing.greek_method,
        calculation_time=configuration.created_at,
        status=status,
    )


def _greek_inputs_supported(leg: object, quote: ExecutableQuote | None) -> bool:
    return bool(
        quote is not None
        and quote.implied_volatility is not None
        and getattr(leg, "expiration", None) is not None
        and getattr(leg, "exercise_style", None) is ExerciseStyle.EUROPEAN
    )


def shape_records(
    payoffs: tuple[StrategyPayoffRecord, ...],
) -> tuple[StrategyShapeRecord, ...]:
    """Extract deterministic profit/loss regions and tail shape."""
    records: list[StrategyShapeRecord] = []
    for payoff in payoffs:
        profit: list[tuple[Decimal, Decimal]] = []
        loss: list[tuple[Decimal, Decimal]] = []
        intervals = zip(
            payoff.spot_grid,
            payoff.spot_grid[1:],
            payoff.terminal_pnl,
            payoff.terminal_pnl[1:],
        )
        for left, right, left_pnl, right_pnl in intervals:
            if left_pnl >= ZERO and right_pnl >= ZERO:
                profit.append((left, right))
            if left_pnl < ZERO and right_pnl < ZERO:
                loss.append((left, right))
        records.append(
            StrategyShapeRecord(
                candidate_id=payoff.candidate_id,
                break_even_points=payoff.break_even_points,
                profit_intervals=tuple(profit),
                loss_intervals=tuple(loss),
                bounded_below=payoff.maximum_loss is not None,
                maximum_gain_unbounded=payoff.maximum_gain_unbounded,
                right_tail_slope=payoff.right_tail_slope,
            )
        )
    return tuple(records)


def scenario_records(
    candidates: tuple[StrategyCandidate, ...],
    beliefs: tuple[MarketBeliefState, ...],
    costs: tuple[CostLiquidityRecord, ...],
) -> tuple[ScenarioEvaluation, ...]:
    """Evaluate candidates only when native P5 scenario capability is available."""
    belief_by_underlying = {item.underlying_id: item for item in beliefs}
    cost_by_id = {item.candidate_id: item for item in costs}
    records: list[ScenarioEvaluation] = []
    for candidate in candidates:
        belief = belief_by_underlying.get(candidate.underlying_id)
        if belief is None or belief.scenario_capability is not CapabilityStatus.AVAILABLE:
            continue
        cost = cost_by_id[candidate.candidate_id]
        transaction_cost = cost.fee_estimate + cost.slippage_estimate
        for scenario in belief.scenarios:
            payoff = strategy_terminal_pnl(
                candidate.legs,
                scenario.terminal_underlying_price,
                ZERO,
            )
            records.append(
                ScenarioEvaluation(
                    candidate_id=candidate.candidate_id,
                    scenario_id=scenario.scenario_id,
                    scenario_probability=scenario.probability,
                    terminal_payoff=payoff,
                    maximum_path_loss=None,
                    scenario_cost=transaction_cost,
                    scenario_pnl=payoff - transaction_cost,
                )
            )
    return tuple(records)


def ambiguity_records(
    candidates: tuple[StrategyCandidate, ...],
) -> tuple[AmbiguityEvaluationRecord, ...]:
    """Publish explicit Wave 2 ambiguity unavailability per candidate."""
    return tuple(
        AmbiguityEvaluationRecord(
            candidate_id=item.candidate_id,
            status=CapabilityStatus.UNAVAILABLE,
        )
        for item in candidates
    )


def _spot(observation: UnderlyingObservation) -> Decimal:
    return reference_spot(observation)
