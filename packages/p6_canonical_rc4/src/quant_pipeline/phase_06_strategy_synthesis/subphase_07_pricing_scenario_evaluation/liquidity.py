"""Executable cost and liquidity assessment for P6.S7.

The module is intentionally isolated from payoff and Greek calculations so the
liquidity contract can evolve without turning the general S7 service module
into a catch-all.
"""
from __future__ import annotations

from decimal import Decimal

from ..domain.enums import CalculationStatus, InstrumentType
from ..domain.models import (
    CostLiquidityRecord,
    ExecutableQuote,
    StrategyCandidate,
    UnderlyingObservation,
)
from ..domain.payoff import strategy_entry_cash_flow
from ..foundation.configuration import Phase6RunConfiguration

ZERO = Decimal("0")
ONE = Decimal("1")
MINIMUM_MIDPOINT = Decimal("0.00000001")


def cost_liquidity(
    candidates: tuple[StrategyCandidate, ...],
    quotes: tuple[ExecutableQuote, ...],
    underlyings: tuple[UnderlyingObservation, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[CostLiquidityRecord, ...]:
    """Estimate executable costs and normalized spread-based liquidity."""
    quote_by_id = {item.contract_id: item for item in quotes}
    underlying_by_id = {item.underlying_id: item for item in underlyings}
    records: list[CostLiquidityRecord] = []
    for candidate in candidates:
        relative_spreads, liquidity_scores, missing_markets = _spread_liquidity_assessment(
            candidate, quote_by_id, underlying_by_id
        )
        quoted = strategy_entry_cash_flow(candidate.legs)
        fee = configuration.pricing.fee_per_leg * Decimal(len(candidate.legs))
        absolute_spread = _absolute_spread(candidate, quote_by_id, underlying_by_id)
        slippage = absolute_spread * configuration.pricing.slippage_fraction_of_spread
        records.append(
            CostLiquidityRecord(
                candidate_id=candidate.candidate_id,
                quoted_cost=quoted,
                conservative_entry_cost=quoted + fee + slippage,
                stress_entry_cost=quoted + fee + absolute_spread,
                fee_estimate=fee,
                slippage_estimate=slippage,
                weakest_leg_liquidity=min(liquidity_scores) if liquidity_scores else None,
                maximum_relative_spread=max(relative_spreads) if relative_spreads else None,
                atomic_combo_available=False,
                legging_required=len(candidate.legs) > 1,
                legging_risk_proxy=absolute_spread if len(candidate.legs) > 1 else ZERO,
                status=(
                    CalculationStatus.AVAILABLE
                    if missing_markets == 0 and relative_spreads
                    else CalculationStatus.DEGRADED
                ),
            )
        )
    return tuple(records)


def _spread_liquidity_assessment(
    candidate: StrategyCandidate,
    quote_by_id: dict[str, ExecutableQuote],
    underlying_by_id: dict[str, UnderlyingObservation],
) -> tuple[list[Decimal], list[Decimal], int]:
    relative_spreads: list[Decimal] = []
    liquidity_scores: list[Decimal] = []
    missing_markets = 0
    for leg in candidate.legs:
        market = _market_for_leg(candidate, leg, quote_by_id, underlying_by_id)
        if market is None or market.bid is None or market.ask is None:
            missing_markets += 1
            continue
        relative_spread = _relative_spread(market.bid, market.ask)
        relative_spreads.append(relative_spread)
        liquidity_scores.append(max(ZERO, ONE - min(relative_spread, ONE)))
    return relative_spreads, liquidity_scores, missing_markets


def _liquidity_inputs(
    candidate: StrategyCandidate,
    quote_by_id: dict[str, ExecutableQuote],
    underlying_by_id: dict[str, UnderlyingObservation] | None = None,
) -> tuple[list[Decimal], list[Decimal]]:
    """Preserve the original diagnostic return shape for tests and extensions."""
    underlying_by_id = underlying_by_id or {}
    relative_spreads: list[Decimal] = []
    depth_values_out: list[Decimal] = []
    for leg in candidate.legs:
        market = _market_for_leg(candidate, leg, quote_by_id, underlying_by_id)
        if market is None or market.bid is None or market.ask is None:
            continue
        relative_spreads.append(_relative_spread(market.bid, market.ask))
        if isinstance(market, ExecutableQuote):
            depth_values = [
                value
                for value in (market.bid_size, market.ask_size, market.volume, market.open_interest)
                if value is not None
            ]
            if depth_values:
                depth_values_out.append(min(depth_values))
    return relative_spreads, depth_values_out


def _relative_spread(bid: Decimal, ask: Decimal) -> Decimal:
    spread = max(ZERO, ask - bid)
    midpoint = (ask + bid) / Decimal("2")
    return spread / max(midpoint, MINIMUM_MIDPOINT)


def _market_for_leg(
    candidate: StrategyCandidate,
    leg: object,
    quote_by_id: dict[str, ExecutableQuote],
    underlying_by_id: dict[str, UnderlyingObservation],
) -> ExecutableQuote | UnderlyingObservation | None:
    if getattr(leg, "instrument_type", None) is InstrumentType.OPTION:
        return quote_by_id.get(getattr(leg, "instrument_id"))
    instrument_id = str(getattr(leg, "instrument_id", candidate.underlying_id))
    return underlying_by_id.get(instrument_id) or underlying_by_id.get(candidate.underlying_id)


def _absolute_spread(
    candidate: StrategyCandidate,
    quote_by_id: dict[str, ExecutableQuote],
    underlying_by_id: dict[str, UnderlyingObservation],
) -> Decimal:
    spread = ZERO
    for leg in candidate.legs:
        market = _market_for_leg(candidate, leg, quote_by_id, underlying_by_id)
        if market is None or market.bid is None or market.ask is None:
            continue
        spread += (market.ask - market.bid) * leg.quantity * leg.multiplier
    return spread
