from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Hashable, MutableMapping

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import InstrumentSpec
from quant_pipeline.phase_08_portfolio_control.foundation.enums import Side
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import deterministic_id
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import FillEvent

from .enums import PositionTransitionType
from .errors import PositionIntegrityError
from .input_models import S8InputBundle
from .position_math import MutablePosition, apply_trade
from .state_models import PhysicalPositionState, PositionTransition, VirtualPositionState

PositionStore = MutableMapping[Hashable, MutablePosition]


def empty_position() -> MutablePosition:
    return MutablePosition(Decimal("0"), Decimal("0"), None, None, Decimal("0"))


def copy_state(state: MutablePosition) -> MutablePosition:
    return MutablePosition(
        quantity=state.quantity,
        signed_cost_basis=state.signed_cost_basis,
        average_entry_price=state.average_entry_price,
        opened_at=state.opened_at,
        realized_pnl=state.realized_pnl,
    )


def initialize_positions(value: S8InputBundle) -> tuple[dict[str, MutablePosition], dict[tuple[str, str], MutablePosition]]:
    physical = {
        p.instrument_id: MutablePosition(
            p.quantity, p.signed_cost_basis, p.average_entry_price, p.opened_at, Decimal("0")
        )
        for p in value.prior_state.physical_positions
    }
    virtual = {
        (p.candidate_id, p.instrument_id): MutablePosition(
            p.quantity, p.signed_cost_basis, p.average_entry_price, p.opened_at, Decimal("0")
        )
        for p in value.prior_state.virtual_positions
    }
    return physical, virtual


def build_instrument_registry(value: S8InputBundle) -> dict[str, InstrumentSpec]:
    result: dict[str, InstrumentSpec] = {}
    for item in (*value.s7_handoff.authorization_bundle.instruments, *value.supplemental_instruments):
        prior = result.get(item.instrument_id)
        if prior is not None and prior != item:
            raise PositionIntegrityError(f"conflicting instrument spec: {item.instrument_id}")
        result[item.instrument_id] = item
    return result


def build_transition(
    source_id: str,
    at: datetime,
    instrument: str,
    candidate: str | None,
    before: MutablePosition,
    delta: Decimal,
    after: MutablePosition,
    realized: Decimal,
    cash: Decimal,
    currency: str,
    kind: PositionTransitionType,
) -> PositionTransition:
    return PositionTransition(
        transition_id=deterministic_id(
            "position-transition", source_id, instrument, candidate or "PHYSICAL", delta
        ),
        source_event_id=source_id,
        event_time=at,
        instrument_id=instrument,
        candidate_id=candidate,
        transition_type=kind,
        quantity_before=before.quantity,
        quantity_delta=delta,
        quantity_after=after.quantity,
        signed_cost_basis_before=before.signed_cost_basis,
        signed_cost_basis_after=after.signed_cost_basis,
        realized_pnl_delta=realized,
        cash_trade_delta=cash,
        currency=currency,
    )


def apply_position_delta(
    store: PositionStore,
    key: Hashable,
    source_id: str,
    at: datetime,
    instrument: str,
    candidate: str | None,
    delta: Decimal,
    price: Decimal,
    spec: InstrumentSpec,
    transitions: list[PositionTransition],
    allow_reversal: bool = False,
) -> None:
    before = store.get(key, empty_position())
    snapshot = copy_state(before)
    after, realized, cash, kind = apply_trade(
        before, delta, price, spec.contract_multiplier, at, allow_reversal
    )
    store[key] = after
    transitions.append(
        build_transition(
            source_id, at, instrument, candidate, snapshot, delta, after,
            realized, cash, spec.currency, kind,
        )
    )


def apply_fill(
    fill: FillEvent,
    instruments: dict[str, InstrumentSpec],
    physical: dict[str, MutablePosition],
    virtual: dict[tuple[str, str], MutablePosition],
    transitions: list[PositionTransition],
) -> None:
    spec = instruments.get(fill.instrument_id)
    if spec is None:
        raise PositionIntegrityError(f"missing instrument spec: {fill.instrument_id}")
    delta = fill.quantity if fill.side == Side.BUY else -fill.quantity
    apply_position_delta(
        physical, fill.instrument_id, fill.fill_id, fill.event_time,
        fill.instrument_id, None, delta, fill.price, spec, transitions,
    )
    for allocation in fill.virtual_allocations:
        apply_position_delta(
            virtual, (allocation.candidate_id, fill.instrument_id), fill.fill_id,
            fill.event_time, fill.instrument_id, allocation.candidate_id,
            allocation.allocated_target_quantity, fill.price, spec, transitions,
        )


def assert_dual_book(
    physical: dict[str, MutablePosition],
    virtual: dict[tuple[str, str], MutablePosition],
) -> None:
    quantities: dict[str, Decimal] = defaultdict(Decimal)
    bases: dict[str, Decimal] = defaultdict(Decimal)
    for (_, instrument_id), state in virtual.items():
        quantities[instrument_id] += state.quantity
        bases[instrument_id] += state.signed_cost_basis
    for instrument_id in set(physical) | set(quantities):
        p = physical.get(instrument_id, empty_position())
        if p.quantity != quantities[instrument_id] or p.signed_cost_basis != bases[instrument_id]:
            raise PositionIntegrityError(f"dual book mismatch: {instrument_id}")


def render_positions(
    as_of: datetime,
    physical: dict[str, MutablePosition],
    virtual: dict[tuple[str, str], MutablePosition],
) -> tuple[tuple[PhysicalPositionState, ...], tuple[VirtualPositionState, ...]]:
    p_out = tuple(
        PhysicalPositionState(
            instrument_id=key, as_of_time=as_of, quantity=state.quantity,
            signed_cost_basis=state.signed_cost_basis,
            average_entry_price=state.average_entry_price, opened_at=state.opened_at,
            realized_pnl=state.realized_pnl,
        )
        for key, state in sorted(physical.items()) if state.quantity != 0
    )
    v_out = tuple(
        VirtualPositionState(
            candidate_id=key[0], instrument_id=key[1], as_of_time=as_of,
            quantity=state.quantity, signed_cost_basis=state.signed_cost_basis,
            average_entry_price=state.average_entry_price, opened_at=state.opened_at,
            realized_pnl=state.realized_pnl,
        )
        for key, state in sorted(virtual.items()) if state.quantity != 0
    )
    return p_out, v_out
