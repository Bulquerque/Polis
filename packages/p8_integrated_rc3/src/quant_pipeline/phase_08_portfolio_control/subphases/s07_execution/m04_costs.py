from __future__ import annotations

from decimal import Decimal

from ...contracts.execution_authorization import P8ExecutionAuthorizationBundle
from ...foundation.enums import CostQuality, OrderClass, Side
from ...foundation.hashing import content_sha256
from .models import (
    CostComponents,
    MarketStateSnapshot,
    PlannedOrderBundle,
    PretradeCostBundle,
    PretradeCostEstimate,
)
from .policies import CostPolicy

MODULE_ID = "P8.S7.M04"
BPS = Decimal("10000")


def execute(
    orders: PlannedOrderBundle,
    market: MarketStateSnapshot,
    bundle: P8ExecutionAuthorizationBundle,
    policy: CostPolicy,
) -> PretradeCostBundle:
    quotes = {(item.instrument_id, item.venue): item for item in market.quotes}
    instruments = {item.instrument_id: item for item in bundle.instruments}
    estimates: list[PretradeCostEstimate] = []
    structure_counts: dict[str, int] = {}
    for item in orders.orders:
        structure_counts[item.structure_id] = structure_counts.get(item.structure_id, 0) + 1
    for order in orders.orders:
        notional = Decimal("0")
        spread = Decimal("0")
        missing_quote = False
        for leg in order.legs:
            quote = quotes.get((leg.instrument_id, order.venue))
            instrument = instruments[leg.instrument_id]
            if quote is None:
                missing_quote = True
                continue
            leg_notional = quote.mid * leg.quantity * instrument.contract_multiplier
            notional += leg_notional
            half_spread = (quote.ask_price - quote.bid_price) / Decimal("2")
            spread += half_spread * leg.quantity * instrument.contract_multiplier
        units = sum((leg.quantity for leg in order.legs), Decimal("0"))
        fees = max(policy.minimum_fee, policy.fee_per_unit * units)
        slippage = notional * policy.slippage_bps / BPS
        impact = notional * policy.impact_coefficient * policy.annualized_volatility
        delay = notional * policy.delay_bps / BPS
        opportunity = notional * policy.opportunity_bps / BPS
        legging = (
            notional * policy.legging_bps / BPS
            if order.order_class != OrderClass.MLEG and structure_counts.get(order.structure_id, 0) > 1
            else Decimal("0")
        )
        borrow = notional * policy.borrow_bps / BPS
        components = CostComponents(
            fees=fees,
            spread=spread,
            slippage=slippage,
            market_impact=impact,
            delay=delay,
            opportunity=opportunity,
            legging=legging,
            borrow=borrow,
        )
        estimates.append(PretradeCostEstimate(
            order_id=order.order_id,
            currency=policy.currency,
            quality=CostQuality.UNAVAILABLE if missing_quote else CostQuality.QUALIFIED,
            components=components,
            total_cost=components.total,
            assumptions=(
                "square_root_impact_proxy_without_randomness",
                "half_spread_crossing_for_aggressive_execution",
                "pretrade_estimate_not_realized_cost",
            ),
        ))
    payload = tuple(estimates)
    return PretradeCostBundle(estimates=payload, content_sha256=content_sha256(payload))
