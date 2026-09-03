from __future__ import annotations

from decimal import Decimal

from quant_pipeline.phase_08_portfolio_control.contracts.execution_authorization import InstrumentSpec
from quant_pipeline.phase_08_portfolio_control.foundation.enums import SecurityType
from quant_pipeline.phase_08_portfolio_control.foundation.hashing import deterministic_id

from .enums import OptionType, PositionTransitionType, SettlementType
from .errors import LifecycleIntegrityError
from .input_models import S8InputBundle
from .lifecycle_models import (
    OptionAssignmentEvent,
    OptionCashSettlementEvent,
    OptionContractSpec,
    OptionExerciseEvent,
    SplitEvent,
)
from .position_math import MutablePosition
from .position_store import apply_position_delta, build_transition, copy_state
from .state_models import LifecycleLedgerRecord, PositionTransition, SettlementRecord


def _validate_allocations(event, expected_signed: Decimal) -> None:
    total = sum((x.signed_contract_quantity for x in event.candidate_allocations), Decimal("0"))
    if total != expected_signed:
        raise LifecycleIntegrityError(
            f"lifecycle candidate allocations mismatch: {event.event_id}"
        )


def _close_option(
    event,
    close_price: Decimal,
    signed_existing: Decimal,
    spec: InstrumentSpec,
    physical: dict[str, MutablePosition],
    virtual: dict[tuple[str, str], MutablePosition],
    transitions: list[PositionTransition],
) -> None:
    apply_position_delta(
        physical, event.instrument_id, event.event_id, event.event_time,
        event.instrument_id, None, -signed_existing, close_price, spec, transitions,
    )
    for allocation in event.candidate_allocations:
        apply_position_delta(
            virtual, (allocation.candidate_id, event.instrument_id), event.event_id,
            event.event_time, event.instrument_id, allocation.candidate_id,
            -allocation.signed_contract_quantity, close_price, spec, transitions,
        )


def _physical_settlement(
    event,
    option: OptionContractSpec,
    instruments: dict[str, InstrumentSpec],
    physical: dict[str, MutablePosition],
    virtual: dict[tuple[str, str], MutablePosition],
    transitions: list[PositionTransition],
    settlements: list[SettlementRecord],
) -> None:
    underlying = instruments.get(option.underlying_id)
    if underlying is None:
        raise LifecycleIntegrityError(
            f"missing underlying instrument spec: {option.underlying_id}"
        )
    units = event.contract_quantity * option.contract_multiplier
    if isinstance(event, OptionExerciseEvent):
        direction = Decimal("1") if option.option_type == OptionType.CALL else Decimal("-1")
    else:
        direction = Decimal("-1") if option.option_type == OptionType.CALL else Decimal("1")
    underlying_delta = direction * units
    apply_position_delta(
        physical, underlying.instrument_id, event.event_id, event.event_time,
        underlying.instrument_id, None, underlying_delta, option.strike,
        underlying, transitions, True,
    )
    for allocation in event.candidate_allocations:
        candidate_units = (
            abs(allocation.signed_contract_quantity) / event.contract_quantity
        ) * underlying_delta
        apply_position_delta(
            virtual, (allocation.candidate_id, underlying.instrument_id), event.event_id,
            event.event_time, underlying.instrument_id, allocation.candidate_id,
            candidate_units, option.strike, underlying, transitions, True,
        )
    cash = -underlying_delta * option.strike * underlying.contract_multiplier
    settlements.append(SettlementRecord(
        settlement_id=deterministic_id("settlement", event.event_id),
        source_event_id=event.event_id,
        event_time=event.event_time,
        currency=underlying.currency,
        cash_delta=cash,
        underlying_instrument_id=underlying.instrument_id,
        underlying_quantity_delta=underlying_delta,
        reason_code="PHYSICAL_OPTION_SETTLEMENT",
    ))


def apply_option_event(
    event,
    option: OptionContractSpec,
    instruments: dict[str, InstrumentSpec],
    physical: dict[str, MutablePosition],
    virtual: dict[tuple[str, str], MutablePosition],
    transitions: list[PositionTransition],
    lifecycle: list[LifecycleLedgerRecord],
    settlements: list[SettlementRecord],
) -> None:
    position = physical.get(event.instrument_id)
    if position is None or position.quantity == 0:
        raise LifecycleIntegrityError("lifecycle event requires open option position")
    if event.event_time < option.expiration and event.event_type.value in {"EXPIRATION", "CASH_SETTLEMENT"}:
        raise LifecycleIntegrityError("expiration/settlement cannot precede contract expiration")
    expected = (Decimal("1") if position.quantity > 0 else Decimal("-1")) * event.contract_quantity
    _validate_allocations(event, expected)
    if isinstance(event, OptionExerciseEvent) and position.quantity < event.contract_quantity:
        raise LifecycleIntegrityError("exercise exceeds long position")
    if isinstance(event, OptionAssignmentEvent) and position.quantity > -event.contract_quantity:
        raise LifecycleIntegrityError("assignment exceeds short position")
    if isinstance(event, (OptionExerciseEvent, OptionAssignmentEvent)) and option.settlement_type != SettlementType.PHYSICAL:
        raise LifecycleIntegrityError("exercise/assignment requires physical settlement")
    close_price = Decimal("0")
    if isinstance(event, OptionCashSettlementEvent):
        if option.settlement_type != SettlementType.CASH:
            raise LifecycleIntegrityError("cash settlement requires cash-settled contract")
        close_price = abs(event.cash_amount) / (event.contract_quantity * option.contract_multiplier)
    option_spec = instruments.get(event.instrument_id)
    if option_spec is None:
        raise LifecycleIntegrityError("missing option instrument spec")
    _close_option(event, close_price, expected, option_spec, physical, virtual, transitions)
    if isinstance(event, (OptionExerciseEvent, OptionAssignmentEvent)):
        _physical_settlement(event, option, instruments, physical, virtual, transitions, settlements)
    elif isinstance(event, OptionCashSettlementEvent):
        settlements.append(SettlementRecord(
            settlement_id=deterministic_id("settlement", event.event_id),
            source_event_id=event.event_id,
            event_time=event.event_time,
            currency=event.currency,
            cash_delta=event.cash_amount,
            underlying_instrument_id=None,
            reason_code="CASH_OPTION_SETTLEMENT",
        ))
    lifecycle.append(LifecycleLedgerRecord(
        event_id=event.event_id,
        event_time=event.event_time,
        instrument_id=event.instrument_id,
        event_type=event.event_type.value,
        reason_code="LIFECYCLE_APPLIED",
    ))


def apply_split(
    event: SplitEvent,
    value: S8InputBundle,
    instruments: dict[str, InstrumentSpec],
    physical: dict[str, MutablePosition],
    virtual: dict[tuple[str, str], MutablePosition],
    transitions: list[PositionTransition],
    lifecycle: list[LifecycleLedgerRecord],
) -> None:
    spec = instruments.get(event.instrument_id)
    if spec is None:
        raise LifecycleIntegrityError("split instrument unknown")
    if spec.security_type == SecurityType.OPTION and not value.policies.allow_option_contract_adjustments:
        raise LifecycleIntegrityError("option contract adjustment capability unavailable")
    if spec.security_type == SecurityType.OPTION or not value.policies.allow_equity_splits:
        raise LifecycleIntegrityError("split capability unavailable")
    ratio = event.ratio_numerator / event.ratio_denominator
    targets: list[tuple[object, dict, str | None]] = [(event.instrument_id, physical, None)]
    targets.extend((key, virtual, key[0]) for key in list(virtual) if key[1] == event.instrument_id)
    for key, store, candidate_id in targets:
        state = store.get(key)
        if state is None or state.quantity == 0:
            continue
        before = copy_state(state)
        state.quantity *= ratio
        state.average_entry_price = state.average_entry_price / ratio if state.average_entry_price else None
        store[key] = state
        transitions.append(build_transition(
            event.event_id, event.event_time, event.instrument_id, candidate_id,
            before, state.quantity - before.quantity, state, Decimal("0"),
            Decimal("0"), spec.currency, PositionTransitionType.CORPORATE_ACTION,
        ))
    lifecycle.append(LifecycleLedgerRecord(
        event_id=event.event_id,
        event_time=event.event_time,
        instrument_id=event.instrument_id,
        event_type=event.event_type.value,
        reason_code="SPLIT_APPLIED",
    ))
