from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from ...contracts.execution_authorization import InstrumentSpec, P8ExecutionAuthorizationBundle
from ...foundation.context import ModuleExecutionContext
from ...foundation.enums import OrderClass, OrderEventType, OrderStatus, PositionIntent, RiskRole, RuntimeControlMode, TimeInForce, VenueState
from ...foundation.errors import OverfillError, StateTransitionError
from ...foundation.event_ordering import ScheduledEvent, TimelinePriority, order_timeline
from ...foundation.hashing import content_sha256, deterministic_id
from .execution_state import OrderExecutionState, TERMINAL_ORDER_STATUSES, emit_order_event
from .fill_logic import allocations_for_fill, combo_fill, simple_quote_fill, simple_trade_fill
from .models import (
    CancelOrderCommand,
    ExecutionCommand,
    ExecutionResult,
    FillEvent,
    MarketEvent,
    OrderEvent,
    PlannedOrder,
    PlannedOrderBundle,
    Quote,
    QuoteEvent,
    ReplaceOrderCommand,
    RuntimeControlCommand,
    TradeEvent,
    VenueStatusEvent,
)
from .policies import ExecutionModelPolicy

MODULE_ID = "P8.S7.M05"


@dataclass
class _ExecutionRuntime:
    instruments: dict[str, InstrumentSpec]
    states: dict[str, OrderExecutionState]
    order_events: list[OrderEvent]
    fills: list[FillEvent]
    quotes: dict[tuple[str, str], Quote]
    venue_states: dict[str, VenueState]
    latency: timedelta
    policy: ExecutionModelPolicy
    active_mode: RuntimeControlMode
    processed_command_keys: set[str]
    last_command_sequence: int
    run_id: str
    cycle_id: str
    source_state_hash: str


def _build_timeline(
    orders: PlannedOrderBundle,
    market_events: tuple[MarketEvent, ...],
    commands: tuple[ExecutionCommand, ...],
) -> tuple[ScheduledEvent[tuple[str, object]], ...]:
    timeline: list[ScheduledEvent[tuple[str, object]]] = []
    for order in orders.orders:
        timeline.extend((
            ScheduledEvent(order.submit_at, TimelinePriority.ORDER_SUBMISSION, f"submit:{order.order_id}", ("submit", order.order_id)),
            ScheduledEvent(order.expire_at, TimelinePriority.ORDER_EXPIRATION, f"expire:{order.order_id}", ("expire", order.order_id)),
        ))
    for event in market_events:
        priority = TimelinePriority.VENUE_STATUS if isinstance(event, VenueStatusEvent) else TimelinePriority.MARKET_DATA
        timeline.append(ScheduledEvent(event.available_at, priority, f"market:{event.event_id}", ("market", event)))
    for command in commands:
        timeline.append(ScheduledEvent(command.event_time, TimelinePriority.SAFETY_COMMAND, f"command:{command.command_id}", ("command", command)))
    return order_timeline(timeline)


def _is_close_order(order: PlannedOrder) -> bool:
    close_intents = {PositionIntent.BUY_TO_CLOSE, PositionIntent.SELL_TO_CLOSE}
    return all(leg.position_intent in close_intents for leg in order.legs)


def _mode_allows_order(mode: RuntimeControlMode, order: PlannedOrder) -> bool:
    if mode == RuntimeControlMode.NORMAL:
        return True
    if mode in {RuntimeControlMode.CANCEL_OPEN_ORDERS, RuntimeControlMode.HALT}:
        return False
    if mode == RuntimeControlMode.HOLD_NO_NEW_RISK:
        return order.risk_role in {RiskRole.PROTECTIVE, RiskRole.RISK_REDUCING}
    if mode in {RuntimeControlMode.CLOSE_ONLY, RuntimeControlMode.CONTROLLED_FLATTEN}:
        return order.risk_role == RiskRole.RISK_REDUCING and _is_close_order(order)
    if mode == RuntimeControlMode.RISK_REDUCTION_ONLY:
        return order.risk_role == RiskRole.RISK_REDUCING
    if mode == RuntimeControlMode.HEDGE_ONLY:
        return order.risk_role == RiskRole.PROTECTIVE
    return False


def _submit(order_id: str, at: datetime, runtime: _ExecutionRuntime) -> None:
    state = runtime.states[order_id]
    if state.status != OrderStatus.CREATED:
        return
    if not _mode_allows_order(runtime.active_mode, state.order):
        runtime.order_events.append(emit_order_event(
            state, OrderStatus.REJECTED, OrderEventType.REJECT, at,
            f"RUNTIME_MODE_BLOCKED:{runtime.active_mode.value}",
        ))
        return
    runtime.order_events.append(emit_order_event(state, OrderStatus.SUBMITTED, OrderEventType.SUBMITTED, at, "ORDER_SUBMITTED"))
    if runtime.venue_states[state.order.venue] != VenueState.OPEN:
        runtime.order_events.append(emit_order_event(state, OrderStatus.REJECTED, OrderEventType.REJECT, at, "VENUE_NOT_OPEN"))
        return
    runtime.order_events.append(emit_order_event(state, OrderStatus.ACCEPTED, OrderEventType.ACCEPTED, at, "ORDER_ACCEPTED"))


def _expire(order_id: str, at: datetime, runtime: _ExecutionRuntime) -> None:
    state = runtime.states[order_id]
    if state.status in {OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED}:
        runtime.order_events.append(emit_order_event(state, OrderStatus.EXPIRED, OrderEventType.EXPIRE, at, "ORDER_EXPIRED"))


def _replace(state: OrderExecutionState, command: ReplaceOrderCommand, at: datetime, runtime: _ExecutionRuntime) -> None:
    if not state.order.replace_allowed:
        raise StateTransitionError("venue does not allow order replacement")
    old_quantity = state.order.quantity
    new_quantity = command.new_quantity or old_quantity
    if new_quantity <= state.filled:
        raise StateTransitionError("replacement quantity must exceed filled quantity")
    if new_quantity > old_quantity:
        raise StateTransitionError("replacement cannot increase authorized order quantity")
    scale = new_quantity / old_quantity
    new_legs = tuple(
        leg.model_copy(update={
            "quantity": leg.quantity * scale,
            "virtual_allocations": tuple(
                allocation.model_copy(update={"allocated_target_quantity": allocation.allocated_target_quantity * scale})
                for allocation in leg.virtual_allocations
            ),
        })
        for leg in state.order.legs
    )
    state.order = state.order.model_copy(update={
        "quantity": new_quantity,
        "limit_price": command.new_limit_price if command.new_limit_price is not None else state.order.limit_price,
        "legs": new_legs,
    })
    runtime.order_events.append(emit_order_event(state, OrderStatus.REPLACED, OrderEventType.REPLACE, at, command.reason_code))
    runtime.order_events.append(emit_order_event(state, OrderStatus.ACCEPTED, OrderEventType.ACCEPTED, at, "REPLACEMENT_ACCEPTED"))


def _command(command: ExecutionCommand, at: datetime, runtime: _ExecutionRuntime) -> None:
    if isinstance(command, RuntimeControlCommand):
        command_key = command.idempotency_key or command.command_id
        if command_key in runtime.processed_command_keys:
            return
        if command.run_id is not None and command.run_id != runtime.run_id:
            raise StateTransitionError(f"foreign runtime command run: {command.command_id}")
        if command.cycle_id is not None and command.cycle_id != runtime.cycle_id:
            raise StateTransitionError(f"foreign runtime command cycle: {command.command_id}")
        if command.source_state_hash is not None and command.source_state_hash != runtime.source_state_hash:
            raise StateTransitionError(f"runtime command source state mismatch: {command.command_id}")
        if command.valid_until is not None and at > command.valid_until:
            raise StateTransitionError(f"expired runtime command: {command.command_id}")
        if not command.feasibility_proven and command.mode != RuntimeControlMode.NORMAL:
            raise StateTransitionError(f"runtime command lacks feasibility proof: {command.command_id}")
        if command.command_sequence <= runtime.last_command_sequence:
            raise StateTransitionError(f"non-increasing runtime command sequence: {command.command_id}")
        runtime.processed_command_keys.add(command_key)
        runtime.last_command_sequence = command.command_sequence
        runtime.active_mode = command.mode
        for state in runtime.states.values():
            if state.status in TERMINAL_ORDER_STATUSES:
                continue
            if not _mode_allows_order(command.mode, state.order):
                runtime.order_events.append(emit_order_event(
                    state, OrderStatus.CANCELLED, OrderEventType.CANCEL, at, command.reason_code,
                ))
        return
    state = runtime.states.get(command.order_id)
    if state is None or state.status in TERMINAL_ORDER_STATUSES:
        return
    if isinstance(command, CancelOrderCommand):
        runtime.order_events.append(emit_order_event(state, OrderStatus.CANCELLED, OrderEventType.CANCEL, at, command.reason_code))
        return
    _replace(state, command, at, runtime)


def _event_venue(event: MarketEvent) -> str:
    return event.quote.venue if isinstance(event, QuoteEvent) else event.venue


def _relevant(order: PlannedOrder, event: MarketEvent) -> bool:
    if isinstance(event, QuoteEvent):
        return order.order_class == OrderClass.MLEG or event.quote.instrument_id == order.legs[0].instrument_id
    if isinstance(event, TradeEvent):
        return order.order_class == OrderClass.SIMPLE and event.instrument_id == order.legs[0].instrument_id
    return False


def _fill_candidate(
    state: OrderExecutionState,
    event: MarketEvent,
    runtime: _ExecutionRuntime,
) -> tuple[Decimal, Decimal | None, dict[str, Decimal] | None] | None:
    order = state.order
    if order.order_class == OrderClass.MLEG and isinstance(event, QuoteEvent):
        combo = combo_fill(order, runtime.quotes, runtime.policy)
        return None if combo is None else (combo[0], None, combo[1])
    if order.order_class == OrderClass.SIMPLE:
        leg = order.legs[0]
        if isinstance(event, QuoteEvent) and event.quote.instrument_id == leg.instrument_id:
            simple = simple_quote_fill(order, event.quote, state.remaining, runtime.policy)
        elif isinstance(event, TradeEvent) and event.instrument_id == leg.instrument_id:
            simple = simple_trade_fill(order, event, state.remaining, runtime.policy)
        else:
            simple = None
        return None if simple is None else (simple[0], simple[1], None)
    return None


def _append_combo_fills(
    state: OrderExecutionState,
    quantity: Decimal,
    prices: dict[str, Decimal],
    event: MarketEvent,
    at: datetime,
    runtime: _ExecutionRuntime,
) -> None:
    order = state.order
    if quantity != order.quantity or state.filled != 0:
        raise StateTransitionError("combo fills must be atomic")
    for index, leg in enumerate(order.legs):
        leg_quantity = quantity * leg.ratio_quantity
        instrument = runtime.instruments[leg.instrument_id]
        runtime.fills.append(FillEvent(
            fill_id=deterministic_id("fill", order.order_id, leg.instrument_id, at),
            order_id=order.order_id,
            structure_id=order.structure_id,
            execution_group_id=order.execution_group_id,
            instrument_id=leg.instrument_id,
            event_time=at,
            side=leg.side,
            quantity=leg_quantity,
            price=prices[leg.instrument_id],
            contract_multiplier=instrument.contract_multiplier,
            fee=runtime.policy.fee_per_unit * leg_quantity,
            virtual_allocations=allocations_for_fill(order, index, leg_quantity),
            market_event_id=event.event_id,
        ))
    state.filled += quantity


def _append_simple_fill(
    state: OrderExecutionState,
    quantity: Decimal,
    price: Decimal,
    event: MarketEvent,
    at: datetime,
    runtime: _ExecutionRuntime,
) -> None:
    order = state.order
    leg = order.legs[0]
    instrument = runtime.instruments[leg.instrument_id]
    state.filled += quantity
    runtime.fills.append(FillEvent(
        fill_id=deterministic_id("fill", order.order_id, len(runtime.fills), at),
        order_id=order.order_id,
        structure_id=order.structure_id,
        execution_group_id=order.execution_group_id,
        instrument_id=leg.instrument_id,
        event_time=at,
        side=leg.side,
        quantity=quantity,
        price=price,
        contract_multiplier=instrument.contract_multiplier,
        fee=runtime.policy.fee_per_unit * quantity,
        virtual_allocations=allocations_for_fill(order, 0, quantity),
        market_event_id=event.event_id,
    ))


def _apply_market_event(event: MarketEvent, at: datetime, runtime: _ExecutionRuntime) -> None:
    if isinstance(event, VenueStatusEvent):
        runtime.venue_states[event.venue] = event.state
        return
    if isinstance(event, QuoteEvent):
        runtime.quotes[(event.quote.instrument_id, event.quote.venue)] = event.quote
    for state in runtime.states.values():
        if not _eligible_for_event(state, event, at, runtime):
            continue
        candidate = _fill_candidate(state, event, runtime)
        if candidate is not None and state.order.time_in_force == TimeInForce.FOK and candidate[0] < state.remaining:
            candidate = None
        if candidate is None:
            if _relevant(state.order, event) and state.order.time_in_force in {TimeInForce.IOC, TimeInForce.FOK}:
                runtime.order_events.append(emit_order_event(
                    state, OrderStatus.CANCELLED, OrderEventType.CANCEL, at,
                    f"{state.order.time_in_force.value}_NOT_FILLED",
                ))
            continue
        quantity, price, combo_prices = candidate
        if state.order.order_class == OrderClass.MLEG:
            if not combo_prices:
                raise StateTransitionError("combo fill candidate lacks leg prices")
            _append_combo_fills(state, quantity, combo_prices, event, at, runtime)
        else:
            if price is None:
                raise StateTransitionError("simple fill candidate lacks execution price")
            _append_simple_fill(state, quantity, price, event, at, runtime)
        _finish_fill_state(state, at, runtime)


def _eligible_for_event(
    state: OrderExecutionState,
    event: MarketEvent,
    at: datetime,
    runtime: _ExecutionRuntime,
) -> bool:
    if state.status not in {OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED}:
        return False
    order = state.order
    return (
        at >= order.submit_at + runtime.latency
        and event.available_at <= at
        and order.venue == _event_venue(event)
        and runtime.venue_states[order.venue] == VenueState.OPEN
    )


def _finish_fill_state(state: OrderExecutionState, at: datetime, runtime: _ExecutionRuntime) -> None:
    if state.filled > state.order.quantity:
        raise OverfillError(f"overfill: {state.order.order_id}")
    if state.filled == state.order.quantity:
        runtime.order_events.append(emit_order_event(state, OrderStatus.FILLED, OrderEventType.FILL, at, "ORDER_FILLED"))
        return
    runtime.order_events.append(emit_order_event(
        state, OrderStatus.PARTIALLY_FILLED, OrderEventType.PARTIAL_FILL, at, "ORDER_PARTIALLY_FILLED",
    ))
    if state.order.time_in_force == TimeInForce.IOC:
        runtime.order_events.append(emit_order_event(
            state, OrderStatus.CANCELLED, OrderEventType.CANCEL, at, "IOC_REMAINDER_CANCELLED",
        ))


def execute(
    orders: PlannedOrderBundle,
    market_events: tuple[MarketEvent, ...],
    commands: tuple[ExecutionCommand, ...],
    bundle: P8ExecutionAuthorizationBundle,
    context: ModuleExecutionContext,
    policy: ExecutionModelPolicy,
) -> ExecutionResult:
    del context  # decision-time validity is enforced in M01 and encoded in each planned order
    runtime = _ExecutionRuntime(
        instruments={item.instrument_id: item for item in bundle.instruments},
        states={order.order_id: OrderExecutionState(order=order) for order in orders.orders},
        order_events=[],
        fills=[],
        quotes={},
        venue_states=defaultdict(lambda: VenueState.OPEN),
        latency=timedelta(milliseconds=policy.latency_milliseconds),
        policy=policy,
        active_mode=RuntimeControlMode.NORMAL,
        processed_command_keys=set(),
        last_command_sequence=-1,
        run_id=bundle.run_id,
        cycle_id=bundle.cycle_id,
        source_state_hash=bundle.content_sha256,
    )
    for scheduled in _build_timeline(orders, market_events, commands):
        kind, item = scheduled.payload
        if kind == "submit":
            _submit(item, scheduled.available_at, runtime)
        elif kind == "expire":
            _expire(item, scheduled.available_at, runtime)
        elif kind == "command":
            _command(item, scheduled.available_at, runtime)
        else:
            _apply_market_event(item, scheduled.available_at, runtime)
    payload = {
        "order_events": tuple(runtime.order_events),
        "fill_events": tuple(runtime.fills),
        "final_status_by_order": {key: value.status for key, value in sorted(runtime.states.items())},
    }
    return ExecutionResult(**payload, content_sha256=content_sha256(payload))
