from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import InstrumentSpec

from .enums import PositionTransitionType
from .errors import PositionIntegrityError
from .input_models import S8InputBundle
from .position_math import MutablePosition
from .position_store import build_transition, copy_state, empty_position
from .state_models import PositionTransition


def _release_basis(
    state: MutablePosition,
    new_quantity: Decimal,
    spec: InstrumentSpec,
) -> tuple[Decimal, Decimal]:
    release_quantity = abs(state.quantity) - abs(new_quantity)
    sign = Decimal("1") if state.quantity > 0 else Decimal("-1")
    basis_per_unit = abs(state.signed_cost_basis) / abs(state.quantity)
    release_basis = sign * basis_per_unit * release_quantity
    state.quantity = new_quantity
    state.signed_cost_basis -= release_basis
    state.average_entry_price = (
        abs(state.signed_cost_basis) / (abs(new_quantity) * spec.contract_multiplier)
        if new_quantity else None
    )
    if new_quantity == 0:
        state.opened_at = None
    return release_quantity, release_basis


def _receive_basis(
    state: MutablePosition,
    new_quantity: Decimal,
    add_quantity: Decimal,
    allocated_basis: Decimal,
    spec: InstrumentSpec,
    opened_at,
) -> None:
    state.quantity = new_quantity
    state.signed_cost_basis += allocated_basis
    state.average_entry_price = abs(state.signed_cost_basis) / (
        abs(new_quantity) * spec.contract_multiplier
    )
    state.opened_at = state.opened_at or opened_at


def apply_virtual_reallocations(
    value: S8InputBundle,
    instruments: dict[str, InstrumentSpec],
    virtual: dict[tuple[str, str], MutablePosition],
    transitions: list[PositionTransition],
) -> None:
    by_instrument: dict[str, list] = defaultdict(list)
    for item in value.s7_handoff.s7_result.receipt.virtual_reallocations:
        by_instrument[item.instrument_id].append(item)
    for instrument_id, items in by_instrument.items():
        _apply_instrument_reallocations(value, instrument_id, items, instruments, virtual, transitions)


def _apply_instrument_reallocations(
    value: S8InputBundle,
    instrument_id: str,
    items: list,
    instruments: dict[str, InstrumentSpec],
    virtual: dict[tuple[str, str], MutablePosition],
    transitions: list[PositionTransition],
) -> None:
    if sum((x.signed_quantity_delta for x in items), Decimal("0")) != 0:
        raise PositionIntegrityError(f"virtual reallocations do not net to zero: {instrument_id}")
    spec = instruments.get(instrument_id)
    if spec is None:
        raise PositionIntegrityError(f"missing instrument spec: {instrument_id}")
    pools = {Decimal("1"): [Decimal("0"), Decimal("0")], Decimal("-1"): [Decimal("0"), Decimal("0")]}
    receivers: list[tuple] = []
    for item in items:
        key = (item.candidate_id, instrument_id)
        state = virtual.get(key, empty_position())
        new_quantity = state.quantity + item.signed_quantity_delta
        if state.quantity and new_quantity and (state.quantity > 0) != (new_quantity > 0):
            raise PositionIntegrityError("virtual reallocation cannot cross zero")
        if abs(new_quantity) < abs(state.quantity):
            before = copy_state(state)
            release_quantity, release_basis = _release_basis(state, new_quantity, spec)
            virtual[key] = state
            sign = Decimal("1") if before.quantity > 0 else Decimal("-1")
            pools[sign][0] += release_quantity
            pools[sign][1] += release_basis
            transitions.append(build_transition(
                item.reallocation_id, value.valuation_time, instrument_id,
                item.candidate_id, before, item.signed_quantity_delta, state,
                Decimal("0"), Decimal("0"), spec.currency,
                PositionTransitionType.REALLOCATION,
            ))
        elif abs(new_quantity) > abs(state.quantity):
            receivers.append((item, key, state, new_quantity))
    _allocate_receivers(value, instrument_id, spec, receivers, pools, virtual, transitions)
    if any(quantity != 0 or basis != 0 for quantity, basis in pools.values()):
        raise PositionIntegrityError("unallocated virtual cost basis remains")


def _allocate_receivers(value, instrument_id, spec, receivers, pools, virtual, transitions) -> None:
    for item, key, state, new_quantity in receivers:
        sign = Decimal("1") if new_quantity > 0 else Decimal("-1")
        add_quantity = abs(new_quantity) - abs(state.quantity)
        pool_quantity, pool_basis = pools[sign]
        if pool_quantity <= 0 or add_quantity > pool_quantity:
            raise PositionIntegrityError("reallocation has no matching cost-basis donor")
        before = copy_state(state)
        allocated_basis = pool_basis * (add_quantity / pool_quantity)
        _receive_basis(state, new_quantity, add_quantity, allocated_basis, spec, value.valuation_time)
        virtual[key] = state
        pools[sign][0] -= add_quantity
        pools[sign][1] -= allocated_basis
        transitions.append(build_transition(
            item.reallocation_id, value.valuation_time, instrument_id,
            item.candidate_id, before, item.signed_quantity_delta, state,
            Decimal("0"), Decimal("0"), spec.currency,
            PositionTransitionType.REALLOCATION,
        ))
