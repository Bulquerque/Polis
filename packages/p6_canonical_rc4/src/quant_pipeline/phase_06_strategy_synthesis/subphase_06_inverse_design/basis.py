"""Replication-basis construction for inverse payoff design."""

from __future__ import annotations

from decimal import Decimal

from ..domain.enums import CalculationStatus, InstrumentType, LegRole, Side
from ..domain.models import (
    ExecutableQuote,
    OptionContractReference,
    ReplicationBasisInstrument,
    StrategyLeg,
    TargetPayoffQualification,
    TargetPayoffRecord,
    UnderlyingObservation,
)
from ..domain.payoff import strategy_terminal_pnl
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id

ZERO = Decimal("0")
BasisLeg = tuple[StrategyLeg, Decimal | None]


def build_replication_basis(
    targets: tuple[TargetPayoffRecord, ...],
    qualifications: tuple[TargetPayoffQualification, ...],
    contracts: tuple[OptionContractReference, ...],
    quotes: tuple[ExecutableQuote, ...],
    underlyings: tuple[UnderlyingObservation, ...],
    configuration: Phase6RunConfiguration,
) -> tuple[ReplicationBasisInstrument, ...]:
    """Build a bounded basis using only observed, executable instruments."""
    qualified = {
        item.target_payoff_id
        for item in qualifications
        if item.qualified
    }
    quote_by_id = {item.contract_id: item for item in quotes}
    underlying_by_id = {
        item.underlying_id: item
        for item in underlyings
    }
    contracts_by_underlying = _group_contracts(contracts)
    output: list[ReplicationBasisInstrument] = []
    for target in targets:
        if target.target_payoff_id not in qualified:
            continue
        legs = _basis_legs(
            target,
            contracts_by_underlying.get(target.underlying_id, []),
            quote_by_id,
            underlying_by_id.get(target.underlying_id),
            configuration,
        )
        limit = configuration.solver.maximum_basis_size
        output.extend(
            _basis_record(target, leg, liquidity, configuration)
            for leg, liquidity in legs[:limit]
        )
    return tuple(output)


def _group_contracts(
    contracts: tuple[OptionContractReference, ...],
) -> dict[str, list[OptionContractReference]]:
    grouped: dict[str, list[OptionContractReference]] = {}
    for contract in contracts:
        grouped.setdefault(contract.underlying_id, []).append(contract)
    return grouped


def _basis_legs(
    target: TargetPayoffRecord,
    contracts: list[OptionContractReference],
    quote_by_id: dict[str, ExecutableQuote],
    underlying: UnderlyingObservation | None,
    configuration: Phase6RunConfiguration,
) -> list[BasisLeg]:
    output = _underlying_legs(underlying, configuration)
    center = sum(target.terminal_state_grid, ZERO) / Decimal(
        len(target.terminal_state_grid)
    )
    ordered = sorted(
        contracts,
        key=lambda item: (
            abs(item.strike - center),
            item.option_type.value,
            item.strike,
        ),
    )
    for contract in ordered:
        quote = quote_by_id.get(contract.contract_id)
        if quote is None:
            continue
        liquidity = _liquidity(quote)
        if quote.ask is not None:
            output.append(
                (_option_leg(contract, quote, Side.LONG, quote.ask), liquidity)
            )
        if quote.bid is not None:
            output.append(
                (_option_leg(contract, quote, Side.SHORT, quote.bid), liquidity)
            )
    return output


def _underlying_legs(
    observation: UnderlyingObservation | None,
    configuration: Phase6RunConfiguration,
) -> list[BasisLeg]:
    if observation is None:
        return []
    output: list[BasisLeg] = []
    if configuration.strategy.allow_long_underlying and observation.ask is not None:
        output.append(
            (_underlying_leg(observation, Side.LONG, observation.ask), None)
        )
    if configuration.strategy.allow_short_underlying and observation.bid is not None:
        output.append(
            (_underlying_leg(observation, Side.SHORT, observation.bid), None)
        )
    return output


def _basis_record(
    target: TargetPayoffRecord,
    leg: StrategyLeg,
    liquidity: Decimal | None,
    configuration: Phase6RunConfiguration,
) -> ReplicationBasisInstrument:
    vector = tuple(
        strategy_terminal_pnl((leg,), spot)
        for spot in target.terminal_state_grid
    )
    return ReplicationBasisInstrument(
        basis_id=stable_id(
            "basis",
            target.target_payoff_id,
            leg.instrument_id,
            leg.side,
        ),
        target_payoff_id=target.target_payoff_id,
        underlying_id=target.underlying_id,
        instrument_id=leg.instrument_id,
        leg=leg,
        payoff_vector=vector,
        entry_cost=abs(leg.entry_price_reference * leg.multiplier),
        liquidity=liquidity,
        margin_proxy=_margin_proxy(leg, target),
        quantity_lower_bound=0,
        quantity_upper_bound=configuration.budgets.max_quantity,
        status=CalculationStatus.AVAILABLE,
    )


def _option_leg(
    contract: OptionContractReference,
    quote: ExecutableQuote,
    side: Side,
    price: Decimal,
) -> StrategyLeg:
    return StrategyLeg(
        leg_id=stable_id("basis-leg", contract.contract_id, side),
        instrument_id=contract.contract_id,
        instrument_type=InstrumentType.OPTION,
        side=side,
        quantity=Decimal("1"),
        option_type=contract.option_type,
        strike=contract.strike,
        expiration=contract.expiration,
        exercise_style=contract.exercise_style,
        settlement_type=contract.settlement_type,
        multiplier=contract.multiplier,
        currency=contract.currency,
        exchange=contract.listing_exchange,
        entry_price_reference=price,
        price_selection_method="ASK" if side is Side.LONG else "BID",
        leg_role=LegRole.CORE,
        quote_quality=quote.quote_quality,
        source_quote_id=quote.source_id,
    )


def _underlying_leg(
    observation: UnderlyingObservation,
    side: Side,
    price: Decimal,
) -> StrategyLeg:
    return StrategyLeg(
        leg_id=stable_id("basis-leg", observation.underlying_id, side),
        instrument_id=observation.underlying_id,
        instrument_type=InstrumentType.UNDERLYING,
        side=side,
        quantity=Decimal("1"),
        multiplier=Decimal("1"),
        currency=observation.currency,
        exchange=observation.exchange,
        entry_price_reference=price,
        price_selection_method="ASK" if side is Side.LONG else "BID",
        leg_role=LegRole.DIRECTIONAL_OVERLAY,
    )


def _liquidity(quote: ExecutableQuote) -> Decimal | None:
    values = [
        value
        for value in (
            quote.bid_size,
            quote.ask_size,
            quote.volume,
            quote.open_interest,
        )
        if value is not None
    ]
    return min(values) if values else None


def _margin_proxy(
    leg: StrategyLeg,
    target: TargetPayoffRecord,
) -> Decimal | None:
    if leg.side is Side.LONG:
        return abs(leg.entry_price_reference * leg.multiplier)
    return target.risk_budget
