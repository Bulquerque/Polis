"""Pathwise mark proxy for scenarios that include explicit price paths."""

from __future__ import annotations

from decimal import Decimal

from ..domain.enums import (
    CalculationStatus,
    ExerciseStyle,
    InstrumentType,
    Side,
)
from ..domain.greeks import option_price
from ..domain.models import (
    CostLiquidityRecord,
    ExecutableQuote,
    MarketBeliefState,
    PathwiseValuationRecord,
    ScenarioEvaluation,
    StrategyCandidate,
)
from ..domain.payoff import strategy_entry_cash_flow
from ..foundation.configuration import Phase6RunConfiguration

ZERO = Decimal("0")
SECONDS_PER_YEAR = Decimal("31536000")


def pathwise_records(
    candidates: tuple[StrategyCandidate, ...],
    beliefs: tuple[MarketBeliefState, ...],
    quotes: tuple[ExecutableQuote, ...],
    costs: tuple[CostLiquidityRecord, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[PathwiseValuationRecord, ...]:
    """Build marks only when each required model input is available."""
    belief_by_underlying = {
        item.underlying_id: item
        for item in beliefs
    }
    quote_by_id = {item.contract_id: item for item in quotes}
    cost_by_id = {item.candidate_id: item for item in costs}
    output: list[PathwiseValuationRecord] = []
    for candidate in candidates:
        belief = belief_by_underlying.get(candidate.underlying_id)
        cost = cost_by_id.get(candidate.candidate_id)
        if belief is None or cost is None:
            continue
        output.extend(
            _candidate_records(
                candidate,
                belief,
                quote_by_id,
                cost,
                configuration,
            )
        )
    return tuple(output)


def merge_pathwise(
    scenarios: tuple[ScenarioEvaluation, ...],
    pathwise: tuple[PathwiseValuationRecord, ...],
) -> tuple[ScenarioEvaluation, ...]:
    """Attach available path marks without changing nominal scenario values."""
    by_key = {
        (item.candidate_id, item.scenario_id): item
        for item in pathwise
    }
    output = []
    for scenario in scenarios:
        path = by_key.get((scenario.candidate_id, scenario.scenario_id))
        if path is None or path.status is not CalculationStatus.AVAILABLE:
            output.append(scenario)
            continue
        output.append(
            scenario.model_copy(
                update={
                    "pathwise_mark_to_market": path.marks,
                    "maximum_path_loss": path.maximum_path_loss,
                }
            )
        )
    return tuple(output)


def _candidate_records(
    candidate: StrategyCandidate,
    belief: MarketBeliefState,
    quote_by_id: dict[str, ExecutableQuote],
    cost: CostLiquidityRecord,
    configuration: Phase6RunConfiguration,
) -> list[PathwiseValuationRecord]:
    output = []
    for scenario in belief.scenarios:
        if not scenario.path_prices:
            continue
        marks, status, reason = _candidate_path(
            candidate,
            scenario.path_prices,
            quote_by_id,
            cost,
            configuration,
        )
        maximum_loss = (
            max((max(-value, ZERO) for value in marks), default=ZERO)
            if marks
            else None
        )
        output.append(
            PathwiseValuationRecord(
                candidate_id=candidate.candidate_id,
                scenario_id=scenario.scenario_id,
                marks=marks,
                maximum_path_loss=maximum_loss,
                method=configuration.pricing.pathwise_method,
                status=status,
                reason_code=reason,
            )
        )
    return output


def _candidate_path(
    candidate: StrategyCandidate,
    path: tuple[Decimal, ...],
    quote_by_id: dict[str, ExecutableQuote],
    cost: CostLiquidityRecord,
    configuration: Phase6RunConfiguration,
) -> tuple[tuple[Decimal, ...], CalculationStatus, str | None]:
    marks: list[Decimal] = []
    entry = strategy_entry_cash_flow(candidate.legs)
    transaction_cost = cost.fee_estimate + cost.slippage_estimate
    for index, spot in enumerate(path):
        remaining = Decimal(len(path) - index - 1) / Decimal(len(path))
        mark, status, reason = _mark_candidate(
            candidate,
            spot,
            remaining,
            quote_by_id,
            configuration,
        )
        if status is not CalculationStatus.AVAILABLE:
            return (), status, reason
        marks.append(mark - entry - transaction_cost)
    return tuple(marks), CalculationStatus.AVAILABLE, None


def _mark_candidate(
    candidate: StrategyCandidate,
    spot: Decimal,
    remaining_fraction: Decimal,
    quote_by_id: dict[str, ExecutableQuote],
    configuration: Phase6RunConfiguration,
) -> tuple[Decimal, CalculationStatus, str | None]:
    mark = ZERO
    for leg in candidate.legs:
        if leg.instrument_type is InstrumentType.UNDERLYING:
            sign = ONE if leg.side is Side.LONG else -ONE
            mark += sign * spot * leg.quantity * leg.multiplier
            continue
        quote = quote_by_id.get(leg.instrument_id)
        if quote is None or quote.implied_volatility is None:
            return ZERO, CalculationStatus.UNAVAILABLE, (
                "P6_PATHWISE_MODEL_INPUT_UNAVAILABLE"
            )
        if leg.expiration is None:
            return ZERO, CalculationStatus.UNAVAILABLE, (
                "P6_PATHWISE_MODEL_INPUT_UNAVAILABLE"
            )
        if leg.exercise_style is not ExerciseStyle.EUROPEAN:
            return ZERO, CalculationStatus.BLOCKED, (
                "P6_EXERCISE_STYLE_UNSUPPORTED"
            )
        years = _remaining_years(leg.expiration, remaining_fraction, configuration)
        mark += option_price(
            leg,
            spot,
            quote.implied_volatility,
            years,
            configuration.pricing.risk_free_rate,
            configuration.pricing.dividend_yield,
        )
    return mark, CalculationStatus.AVAILABLE, None


def _remaining_years(expiration, remaining_fraction, configuration):
    seconds = max(
        (expiration - configuration.decision_time).total_seconds(),
        0,
    )
    return Decimal(str(seconds)) / SECONDS_PER_YEAR * remaining_fraction


ONE = Decimal("1")
