from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from ...foundation.enums import OrderClass, OrderStatus, ReceiptStatus, Side
from ...foundation.errors import ReconciliationError
from ...foundation.hashing import content_sha256, deterministic_id
from .models import CandidateExecutionAllocation, ExecutionReceipt, ExecutionResult, InstrumentPositionDelta, MarketStateSnapshot, OrderIntentBundle, OrderReconciliation, PlannedOrder, PlannedOrderBundle, PretradeCostBundle, RealizedExecutionCost

MODULE_ID = "P8.S7.M06"
TERMINAL = {OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED, OrderStatus.FILLED}


@dataclass(frozen=True, slots=True)
class _ReconciliationState:
    quote_by_key: dict
    pretrade_by_id: dict
    fills_by_order: dict


def _state(orders, execution, pretrade, market) -> _ReconciliationState:
    order_ids = {item.order_id for item in orders.orders}
    fills_by_order: dict[str, list] = defaultdict(list)
    for fill in execution.fill_events:
        if fill.order_id not in order_ids:
            raise ReconciliationError(f"orphan fill: {fill.fill_id}")
        fills_by_order[fill.order_id].append(fill)
    return _ReconciliationState(
        quote_by_key={(item.instrument_id, item.venue): item for item in market.quotes},
        pretrade_by_id={item.order_id: item for item in pretrade.estimates},
        fills_by_order=fills_by_order,
    )


def _filled_quantity(order: PlannedOrder, fills: list) -> Decimal:
    if order.order_class == OrderClass.MLEG:
        return order.quantity if fills else Decimal("0")
    return sum((fill.quantity for fill in fills), Decimal("0"))


def _reconcile_quantity(order, fills, final_status) -> OrderReconciliation:
    filled = _filled_quantity(order, fills)
    remainder = order.quantity - filled
    cancelled = remainder if final_status == OrderStatus.CANCELLED else Decimal("0")
    rejected = remainder if final_status == OrderStatus.REJECTED else Decimal("0")
    expired = remainder if final_status == OrderStatus.EXPIRED else Decimal("0")
    open_quantity = remainder if final_status not in TERMINAL else Decimal("0")
    conserved = order.quantity == filled + cancelled + rejected + expired + open_quantity
    if not conserved:
        raise ReconciliationError(f"quantity conservation failed: {order.order_id}")
    return OrderReconciliation(
        order_id=order.order_id, ordered_quantity=order.quantity, filled_quantity=filled,
        cancelled_quantity=cancelled, rejected_quantity=rejected, expired_quantity=expired,
        open_quantity=open_quantity, final_status=final_status, quantity_conserved=True,
    )


def _cost_and_deltas(order, fills, state, instrument_delta, candidate_delta):
    shortfall = fees = Decimal("0")
    for fill in fills:
        sign = Decimal("1") if fill.side == Side.BUY else Decimal("-1")
        instrument_delta[fill.instrument_id] += sign * fill.quantity
        quote = state.quote_by_key.get((fill.instrument_id, order.venue))
        if quote is None:
            raise ReconciliationError(f"missing arrival quote for fill: {fill.fill_id}")
        shortfall += sign * (fill.price - quote.mid) * fill.quantity * fill.contract_multiplier
        fees += fill.fee
        for allocation in fill.virtual_allocations:
            candidate_delta[(allocation.candidate_id, fill.instrument_id)] += allocation.allocated_target_quantity
    if not fills:
        return None
    estimate = state.pretrade_by_id.get(order.order_id)
    estimated = estimate.total_cost if estimate is not None else None
    total = shortfall + fees
    return RealizedExecutionCost(
        order_id=order.order_id,
        arrival_mid=state.quote_by_key[(fills[0].instrument_id, order.venue)].mid,
        implementation_shortfall=shortfall,
        fees=fees,
        total_realized_cost=total,
        pretrade_estimate=estimated,
        estimation_error=None if estimated is None else total - estimated,
    )


def _receipt_status(orders, intents, rows) -> ReceiptStatus:
    if not orders.orders and not intents.virtual_reallocations:
        return ReceiptStatus.NO_ACTION_VALID
    if not orders.orders or all(item.final_status == OrderStatus.FILLED for item in rows):
        return ReceiptStatus.PASS
    return ReceiptStatus.PARTIAL


def execute(
    intents: OrderIntentBundle,
    orders: PlannedOrderBundle,
    execution: ExecutionResult,
    pretrade: PretradeCostBundle,
    arrival_market: MarketStateSnapshot,
) -> ExecutionReceipt:
    state = _state(orders, execution, pretrade, arrival_market)
    reconciliations: list[OrderReconciliation] = []
    realized: list[RealizedExecutionCost] = []
    instrument_delta: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    candidate_delta: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    for order in orders.orders:
        fills = state.fills_by_order[order.order_id]
        row = _reconcile_quantity(order, fills, execution.final_status_by_order[order.order_id])
        reconciliations.append(row)
        cost = _cost_and_deltas(order, fills, state, instrument_delta, candidate_delta)
        if cost is not None:
            realized.append(cost)
    instrument_rows = tuple(InstrumentPositionDelta(instrument_id=key, signed_quantity_delta=value) for key, value in sorted(instrument_delta.items()))
    candidate_rows = tuple(CandidateExecutionAllocation(candidate_id=key[0], instrument_id=key[1], signed_quantity_delta=value) for key, value in sorted(candidate_delta.items()))
    order_hash, fill_hash = content_sha256(execution.order_events), content_sha256(execution.fill_events)
    payload = {
        "status": _receipt_status(orders, intents, reconciliations),
        "order_reconciliations": tuple(reconciliations),
        "instrument_position_deltas": instrument_rows,
        "candidate_allocations": candidate_rows,
        "virtual_reallocations": intents.virtual_reallocations,
        "realized_costs": tuple(realized),
        "order_event_ledger_hash": order_hash,
        "fill_event_ledger_hash": fill_hash,
    }
    return ExecutionReceipt(
        receipt_id=deterministic_id("execution-receipt", order_hash, fill_hash),
        **payload, content_sha256=content_sha256(payload),
    )
