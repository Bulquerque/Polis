from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from math import gcd

from ...contracts.execution_authorization import ExecutionAuthorization, InstrumentSpec, P8ExecutionAuthorizationBundle
from ...foundation.context import ModuleExecutionContext
from ...foundation.enums import OrderClass, OrderType, RiskRole, SecurityType, Side, StructureType, TimeInForce, Urgency, VenueState
from ...foundation.errors import CapabilityError
from ...foundation.hashing import content_sha256, deterministic_id
from .models import (
    ExecutionStructureBundle,
    ExecutionStructurePlan,
    MarketStateSnapshot,
    OrderIntent,
    OrderIntentBundle,
    PlannedOrder,
    PlannedOrderBundle,
    PlannedOrderLeg,
    Quote,
    RoutingBlock,
    VenueCapabilities,
)
from .policies import RoutingPolicy

MODULE_ID = "P8.S7.M03"
BPS = Decimal("10000")


@dataclass(frozen=True, slots=True)
class _RoutingState:
    bundle: P8ExecutionAuthorizationBundle
    market: MarketStateSnapshot
    context: ModuleExecutionContext
    policy: RoutingPolicy
    instruments: dict[str, InstrumentSpec]
    authorizations: dict[str, ExecutionAuthorization]
    quotes: dict[tuple[str, str], Quote]
    capabilities: dict[str, VenueCapabilities]


def _floor_increment(value: Decimal, increment: Decimal) -> Decimal:
    return (value / increment).to_integral_value(rounding=ROUND_DOWN) * increment


def _protected_limit(intent: OrderIntent, quote: Quote, protection_bps: Decimal) -> Decimal:
    protection = protection_bps / BPS
    if intent.side == Side.BUY:
        return min(quote.ask_price, quote.mid * (Decimal("1") + protection))
    return max(quote.bid_price, quote.mid * (Decimal("1") - protection))


def _select_order_type(intent: OrderIntent, auth: ExecutionAuthorization, policy: RoutingPolicy) -> OrderType:
    market_allowed = auth.allow_market_order and OrderType.MARKET in auth.allowed_order_types
    if intent.urgency == Urgency.CRITICAL and policy.use_market_for_critical and market_allowed:
        return OrderType.MARKET
    if policy.default_order_type == OrderType.MARKET and not market_allowed:
        if OrderType.LIMIT in auth.allowed_order_types:
            return OrderType.LIMIT
    elif policy.default_order_type in auth.allowed_order_types:
        return policy.default_order_type
    if OrderType.LIMIT in auth.allowed_order_types:
        return OrderType.LIMIT
    raise CapabilityError(f"no safe supported order type for intent {intent.intent_id}")


def _select_tif(security_type: SecurityType, allowed: tuple[TimeInForce, ...], caps: VenueCapabilities, policy: RoutingPolicy) -> TimeInForce:
    intersection = tuple(tif for tif in allowed if tif in caps.supported_tifs)
    if security_type == SecurityType.OPTION:
        if TimeInForce.DAY not in intersection:
            raise CapabilityError("options require DAY in the champion venue profile")
        return TimeInForce.DAY
    if policy.default_tif in intersection:
        return policy.default_tif
    if TimeInForce.DAY in intersection:
        return TimeInForce.DAY
    raise CapabilityError("no supported time in force")


def _slices(quantity: Decimal, increment: Decimal, maximum: Decimal) -> tuple[Decimal, ...]:
    maximum = _floor_increment(maximum, increment)
    if maximum < increment:
        raise CapabilityError("participation capacity is below the quantity increment")
    result: list[Decimal] = []
    remaining = quantity
    while remaining > 0:
        part = _floor_increment(min(remaining, maximum), increment)
        if part <= 0:
            raise CapabilityError("quantity cannot be sliced to instrument increment")
        result.append(part)
        remaining -= part
    return tuple(result)




def _aggregate_risk_role(group: list[OrderIntent]) -> RiskRole:
    roles = {item.risk_role for item in group}
    if RiskRole.RISK_INCREASING in roles:
        return RiskRole.RISK_INCREASING
    if RiskRole.NEUTRAL in roles:
        return RiskRole.NEUTRAL
    if RiskRole.PROTECTIVE in roles:
        return RiskRole.PROTECTIVE
    return RiskRole.RISK_REDUCING

def _combo_strategy_quantity(group: list[OrderIntent]) -> Decimal:
    quantities: list[int] = []
    for item in group:
        if item.quantity != item.quantity.to_integral_value():
            raise CapabilityError("champion combo requires integral leg quantities")
        quantities.append(int(item.quantity))
    common = quantities[0]
    for quantity in quantities[1:]:
        common = gcd(common, quantity)
    if common <= 0:
        raise CapabilityError("combo strategy quantity must be positive")
    return Decimal(common)


def _block(structure: ExecutionStructurePlan, reason: str) -> RoutingBlock:
    return RoutingBlock(structure_id=structure.structure_id, reason_code=reason)


def _plan_combo(
    structure: ExecutionStructurePlan,
    group: list[OrderIntent],
    venue: str,
    caps: VenueCapabilities,
    state: _RoutingState,
) -> PlannedOrder | RoutingBlock:
    if not caps.supports_combo or not (caps.min_combo_legs <= len(group) <= caps.max_combo_legs):
        return _block(structure, "COMBO_CAPABILITY_UNAVAILABLE")
    if any((item.instrument_id, venue) not in state.quotes for item in group):
        return _block(structure, "COMBO_QUOTE_UNAVAILABLE")
    auths = [state.authorizations[item.authorization_id] for item in group]
    if any(OrderType.LIMIT not in auth.allowed_order_types for auth in auths):
        return _block(structure, "COMBO_LIMIT_NOT_AUTHORIZED")
    shared_tifs = tuple(
        tif for tif in auths[0].allowed_time_in_force
        if all(tif in auth.allowed_time_in_force for auth in auths[1:])
    )
    try:
        tif = _select_tif(SecurityType.OPTION, shared_tifs, caps, state.policy)
        strategy_qty = _combo_strategy_quantity(group)
    except CapabilityError as exc:
        return _block(structure, f"COMBO_POLICY_UNSUPPORTED:{exc}")
    legs, net_limit = _build_combo_legs(group, venue, strategy_qty, state)
    order_id = deterministic_id("order", structure.structure_id, 0, strategy_qty)
    submit_at = max(state.context.decision_time, state.market.as_of_time)
    return PlannedOrder(
        order_id=order_id,
        client_order_id=order_id,
        authorization_ids=tuple(item.authorization_id for item in group),
        structure_id=structure.structure_id,
        execution_group_id=structure.execution_group_id,
        order_class=OrderClass.MLEG,
        venue=venue,
        security_type=SecurityType.OPTION,
        risk_role=_aggregate_risk_role(group),
        order_type=OrderType.LIMIT,
        time_in_force=tif,
        quantity=strategy_qty,
        limit_price=net_limit,
        submit_at=submit_at,
        expire_at=min(state.bundle.valid_until, submit_at + state.policy.order_lifetime),
        slice_index=0,
        replace_allowed=caps.supports_replace,
        legs=legs,
    )


def _build_combo_legs(
    group: list[OrderIntent], venue: str, strategy_qty: Decimal, state: _RoutingState,
) -> tuple[tuple[PlannedOrderLeg, ...], Decimal]:
    legs: list[PlannedOrderLeg] = []
    net_limit = Decimal("0")
    for item in group:
        quote = state.quotes[(item.instrument_id, venue)]
        auth = state.authorizations[item.authorization_id]
        price = _protected_limit(item, quote, auth.price_protection_bps)
        ratio = item.quantity / strategy_qty
        net_limit += (price if item.side == Side.BUY else -price) * ratio
        legs.append(PlannedOrderLeg(
            intent_id=item.intent_id,
            instrument_id=item.instrument_id,
            side=item.side,
            position_intent=item.position_intent,
            ratio_quantity=ratio,
            quantity=item.quantity,
            virtual_allocations=item.virtual_allocations,
        ))
    return tuple(legs), net_limit


def _validate_simple_intent(
    item: OrderIntent, venue: str, caps: VenueCapabilities, state: _RoutingState,
) -> tuple[Quote, InstrumentSpec, ExecutionAuthorization, OrderType, TimeInForce] | str:
    quote = state.quotes.get((item.instrument_id, venue))
    if quote is None:
        return "QUOTE_UNAVAILABLE_FOR_VENUE"
    instrument = state.instruments[item.instrument_id]
    auth = state.authorizations[item.authorization_id]
    if item.security_type not in caps.supported_security_types:
        return "SECURITY_TYPE_UNSUPPORTED"
    if item.quantity < instrument.lot_size:
        return "QUANTITY_BELOW_LOT_SIZE"
    if not caps.supports_fractional and item.quantity != item.quantity.to_integral_value():
        return "FRACTIONAL_QUANTITY_UNSUPPORTED"
    try:
        order_type = _select_order_type(item, auth, state.policy)
        tif = _select_tif(item.security_type, auth.allowed_time_in_force, caps, state.policy)
    except CapabilityError as exc:
        return f"ROUTING_POLICY_UNSUPPORTED:{exc}"
    if order_type not in caps.supported_order_types:
        return "ORDER_TYPE_UNSUPPORTED_BY_VENUE"
    return quote, instrument, auth, order_type, tif


def _plan_intent_orders(
    structure: ExecutionStructurePlan,
    item: OrderIntent,
    sequence_index: int,
    venue: str,
    caps: VenueCapabilities,
    state: _RoutingState,
) -> list[PlannedOrder] | str:
    validated = _validate_simple_intent(item, venue, caps, state)
    if isinstance(validated, str):
        return validated
    quote, instrument, auth, order_type, tif = validated
    displayed = quote.ask_size if item.side == Side.BUY else quote.bid_size
    try:
        parts = _slices(item.quantity, instrument.quantity_increment, min(state.policy.max_slice_quantity, displayed * auth.max_participation_rate))
    except CapabilityError as exc:
        return f"SLICING_UNAVAILABLE:{exc}"
    return [
        _build_simple_order(structure, item, sequence_index, slice_index, quantity, venue, caps, quote, auth, order_type, tif, state)
        for slice_index, quantity in enumerate(parts)
    ]


def _build_simple_order(
    structure: ExecutionStructurePlan,
    item: OrderIntent,
    sequence_index: int,
    slice_index: int,
    quantity: Decimal,
    venue: str,
    caps: VenueCapabilities,
    quote: Quote,
    auth: ExecutionAuthorization,
    order_type: OrderType,
    tif: TimeInForce,
    state: _RoutingState,
) -> PlannedOrder:
    submit_at = max(state.context.decision_time, state.market.as_of_time) + state.policy.slice_interval * (sequence_index + slice_index)
    order_id = deterministic_id("order", structure.structure_id, item.intent_id, slice_index, quantity)
    ratio = quantity / item.quantity
    allocations = tuple(
        allocation.model_copy(update={"allocated_target_quantity": allocation.allocated_target_quantity * ratio})
        for allocation in item.virtual_allocations
    )
    leg = PlannedOrderLeg(
        intent_id=item.intent_id,
        instrument_id=item.instrument_id,
        side=item.side,
        position_intent=item.position_intent,
        ratio_quantity=Decimal("1"),
        quantity=quantity,
        virtual_allocations=allocations,
    )
    return PlannedOrder(
        order_id=order_id,
        client_order_id=order_id,
        authorization_ids=(item.authorization_id,),
        structure_id=structure.structure_id,
        execution_group_id=structure.execution_group_id,
        order_class=OrderClass.SIMPLE,
        venue=venue,
        security_type=item.security_type,
        risk_role=item.risk_role,
        order_type=order_type,
        time_in_force=tif,
        quantity=quantity,
        limit_price=None if order_type == OrderType.MARKET else _protected_limit(item, quote, auth.price_protection_bps),
        submit_at=submit_at,
        expire_at=min(state.bundle.valid_until, submit_at + state.policy.order_lifetime),
        slice_index=slice_index,
        replace_allowed=caps.supports_replace,
        legs=(leg,),
    )


def _plan_structure(
    structure: ExecutionStructurePlan,
    intent_by_id: dict[str, OrderIntent],
    state: _RoutingState,
) -> tuple[list[PlannedOrder], RoutingBlock | None]:
    if structure.structure_type == StructureType.BLOCKED:
        return [], _block(structure, structure.block_reason or "UPSTREAM_STRUCTURE_BLOCKED")
    venue = structure.venue or state.policy.default_venue
    caps = state.capabilities.get(venue)
    if caps is None:
        return [], _block(structure, "VENUE_CAPABILITY_UNAVAILABLE")
    if state.market.venue_states.get(venue) != VenueState.OPEN:
        return [], _block(structure, "VENUE_NOT_OPEN")
    group = [intent_by_id[item_id] for item_id in structure.sequence]
    if structure.structure_type == StructureType.COMBO:
        result = _plan_combo(structure, group, venue, caps, state)
        return ([], result) if isinstance(result, RoutingBlock) else ([result], None)
    orders: list[PlannedOrder] = []
    for index, item in enumerate(group):
        result = _plan_intent_orders(structure, item, index, venue, caps, state)
        if isinstance(result, str):
            return [], _block(structure, result)
        orders.extend(result)
    return orders, None


def execute(
    intents: OrderIntentBundle,
    structures: ExecutionStructureBundle,
    bundle: P8ExecutionAuthorizationBundle,
    market: MarketStateSnapshot,
    capabilities: tuple[VenueCapabilities, ...],
    context: ModuleExecutionContext,
    policy: RoutingPolicy,
) -> PlannedOrderBundle:
    state = _RoutingState(
        bundle=bundle,
        market=market,
        context=context,
        policy=policy,
        instruments={item.instrument_id: item for item in bundle.instruments},
        authorizations={item.authorization_id: item for item in bundle.authorizations},
        quotes={(item.instrument_id, item.venue): item for item in market.quotes},
        capabilities={item.venue: item for item in capabilities},
    )
    intent_by_id = {item.intent_id: item for item in intents.intents}
    orders: list[PlannedOrder] = []
    blocks: list[RoutingBlock] = []
    for structure in structures.structures:
        planned, blocked = _plan_structure(structure, intent_by_id, state)
        orders.extend(planned)
        if blocked is not None:
            blocks.append(blocked)
    payload = tuple(sorted(orders, key=lambda item: (item.submit_at, item.order_id)))
    routing_blocks = tuple(sorted(blocks, key=lambda item: (item.structure_id, item.reason_code)))
    return PlannedOrderBundle(
        orders=payload,
        blocked_structure_ids=tuple(item.structure_id for item in routing_blocks),
        routing_blocks=routing_blocks,
        content_sha256=content_sha256({"orders": payload, "routing_blocks": routing_blocks}),
    )
