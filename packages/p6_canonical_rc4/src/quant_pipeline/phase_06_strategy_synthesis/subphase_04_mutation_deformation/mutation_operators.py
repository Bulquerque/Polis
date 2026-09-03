"""Bounded mutation operators for canonical strategy candidates."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..domain.enums import (
    InstrumentType,
    LegRole,
    MutationOperator,
    ObjectiveFamily,
    Side,
)
from ..domain.models import (
    ExecutableQuote,
    OptionContractReference,
    StrategyCandidate,
    StrategyLeg,
    UnderlyingObservation,
)
from ..foundation.configuration import Phase6RunConfiguration
from ..foundation.hashing import stable_id
from .mutation_materialization import MutatedPair, build_child

ZERO = Decimal("0")
ContractSlice = tuple[str, str, str]


def contract_slices(
    contracts: tuple[OptionContractReference, ...],
) -> dict[ContractSlice, tuple[OptionContractReference, ...]]:
    """Index contracts by underlying, option type, and expiration."""
    grouped: dict[ContractSlice, list[OptionContractReference]] = defaultdict(list)
    for contract in contracts:
        key = (
            contract.underlying_id,
            contract.option_type.value,
            contract.expiration.isoformat(),
        )
        grouped[key].append(contract)
    return {
        key: tuple(sorted(values, key=lambda item: item.strike))
        for key, values in grouped.items()
    }


def move_strikes(
    parent: StrategyCandidate,
    slices: dict[ContractSlice, tuple[OptionContractReference, ...]],
    quote_by_id: dict[str, ExecutableQuote],
    configuration: Phase6RunConfiguration,
) -> list[MutatedPair]:
    """Move each option leg to its adjacent valid strikes."""
    output: list[MutatedPair] = []
    for index, leg in enumerate(parent.legs):
        if not _movable_option(leg):
            continue
        key = (
            parent.underlying_id,
            leg.option_type.value,
            leg.expiration.isoformat(),
        )
        contracts = slices.get(key, ())
        position = _contract_position(contracts, leg.instrument_id)
        if position is None:
            continue
        for offset in (-1, 1):
            target = position + offset
            if 0 <= target < len(contracts):
                pair = _replace_strike(
                    parent,
                    index,
                    contracts[target],
                    quote_by_id,
                    configuration,
                )
                if pair is not None:
                    output.append(pair)
    return output


def change_quantity(
    parent: StrategyCandidate,
    configuration: Phase6RunConfiguration,
) -> MutatedPair | None:
    """Increase one leg quantity within the configured bound."""
    for index, leg in enumerate(parent.legs):
        if leg.quantity >= configuration.budgets.max_quantity:
            continue
        updated = leg.quantity + Decimal("1")
        legs = list(parent.legs)
        legs[index] = leg.model_copy(update={"quantity": updated})
        return build_child(
            parent,
            tuple(legs),
            MutationOperator.CHANGE_QUANTITY,
            {
                "leg_index": str(index),
                "from": str(leg.quantity),
                "to": str(updated),
            },
            configuration,
        )
    return None


def add_underlying(
    parent: StrategyCandidate,
    observations: dict[str, UnderlyingObservation],
    configuration: Phase6RunConfiguration,
) -> MutatedPair | None:
    """Add a bounded static underlying overlay when policy permits it."""
    if not configuration.mutation.allow_underlying_overlay:
        return None
    if any(
        leg.instrument_type is InstrumentType.UNDERLYING
        for leg in parent.legs
    ):
        return None
    if len(parent.legs) >= configuration.budgets.max_legs:
        return None
    observation = observations.get(parent.underlying_id)
    if observation is None:
        return None
    side = _overlay_side(parent)
    price = observation.bid if side is Side.SHORT else observation.ask
    if price is None:
        return None
    leg = _underlying_leg(parent, observation, side, price, configuration)
    return build_child(
        parent,
        parent.legs + (leg,),
        MutationOperator.ADD_UNDERLYING,
        {"quantity": str(leg.quantity), "side": side.value},
        configuration,
    )


def remove_redundant(
    parent: StrategyCandidate,
    configuration: Phase6RunConfiguration,
) -> MutatedPair | None:
    """Aggregate duplicated positions and remove exact cancellations."""
    grouped, exemplars = _net_legs(parent)
    if len(grouped) == len(parent.legs):
        return None
    legs = _materialize_netted_legs(grouped, exemplars)
    if not legs:
        return None
    return build_child(
        parent,
        legs,
        MutationOperator.REMOVE_REDUNDANT_LEG,
        {},
        configuration,
    )


def _movable_option(leg: StrategyLeg) -> bool:
    return bool(
        leg.instrument_type is InstrumentType.OPTION
        and leg.expiration is not None
        and leg.option_type is not None
    )


def _contract_position(
    contracts: tuple[OptionContractReference, ...],
    instrument_id: str,
) -> int | None:
    for position, contract in enumerate(contracts):
        if contract.contract_id == instrument_id:
            return position
    return None


def _replace_strike(
    parent: StrategyCandidate,
    index: int,
    contract: OptionContractReference,
    quote_by_id: dict[str, ExecutableQuote],
    configuration: Phase6RunConfiguration,
) -> MutatedPair | None:
    leg = parent.legs[index]
    quote = quote_by_id.get(contract.contract_id)
    if quote is None:
        return None
    price = quote.ask if leg.side is Side.LONG else quote.bid
    if price is None:
        return None
    replacement = leg.model_copy(
        update=_replacement_fields(leg, contract, quote, price)
    )
    legs = list(parent.legs)
    legs[index] = replacement
    return build_child(
        parent,
        tuple(legs),
        MutationOperator.MOVE_STRIKE,
        {
            "leg_index": str(index),
            "from": leg.instrument_id,
            "to": contract.contract_id,
        },
        configuration,
    )


def _replacement_fields(
    leg: StrategyLeg,
    contract: OptionContractReference,
    quote: ExecutableQuote,
    price: Decimal,
) -> dict[str, object]:
    return {
        "leg_id": stable_id(
            "leg",
            contract.contract_id,
            leg.side,
            leg.quantity,
            leg.leg_role,
        ),
        "instrument_id": contract.contract_id,
        "strike": contract.strike,
        "expiration": contract.expiration,
        "exercise_style": contract.exercise_style,
        "settlement_type": contract.settlement_type,
        "multiplier": contract.multiplier,
        "currency": contract.currency,
        "exchange": contract.listing_exchange,
        "entry_price_reference": price,
        "source_quote_id": quote.source_id,
        "quote_quality": quote.quote_quality,
    }


def _overlay_side(parent: StrategyCandidate) -> Side:
    if parent.objective_family is ObjectiveFamily.DIRECTIONAL_DOWN:
        return Side.SHORT
    return Side.LONG


def _underlying_leg(
    parent: StrategyCandidate,
    observation: UnderlyingObservation,
    side: Side,
    price: Decimal,
    configuration: Phase6RunConfiguration,
) -> StrategyLeg:
    return StrategyLeg(
        leg_id=stable_id("leg", parent.candidate_id, "overlay", side),
        instrument_id=parent.underlying_id,
        instrument_type=InstrumentType.UNDERLYING,
        side=side,
        quantity=configuration.mutation.overlay_quantity,
        multiplier=Decimal("1"),
        currency=observation.currency,
        exchange=observation.exchange,
        entry_price_reference=price,
        price_selection_method="BID" if side is Side.SHORT else "ASK",
        leg_role=LegRole.DIRECTIONAL_OVERLAY,
    )


def _net_legs(
    parent: StrategyCandidate,
) -> tuple[
    dict[tuple[str, str], Decimal],
    dict[tuple[str, str], StrategyLeg],
]:
    grouped: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    exemplars: dict[tuple[str, str], StrategyLeg] = {}
    for leg in parent.legs:
        key = (leg.instrument_id, leg.instrument_type.value)
        direction = leg.quantity if leg.side is Side.LONG else -leg.quantity
        grouped[key] += direction
        exemplars[key] = leg
    return grouped, exemplars


def _materialize_netted_legs(
    grouped: dict[tuple[str, str], Decimal],
    exemplars: dict[tuple[str, str], StrategyLeg],
) -> tuple[StrategyLeg, ...]:
    legs: list[StrategyLeg] = []
    for key, quantity in sorted(grouped.items()):
        if quantity == ZERO:
            continue
        base = exemplars[key]
        legs.append(
            base.model_copy(
                update={
                    "side": Side.LONG if quantity > ZERO else Side.SHORT,
                    "quantity": abs(quantity),
                }
            )
        )
    return tuple(legs)
