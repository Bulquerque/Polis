from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from pydantic import Field

from ...foundation.enums import OrderType, TimeInForce
from ...foundation.models import Fraction, NonNegativeDecimal, PositiveDecimal, StrictModel


class IntentPolicy(StrictModel):
    zero_tolerance: NonNegativeDecimal = Decimal("0")


class StructurePolicy(StrictModel):
    prefer_combo: bool = True
    require_unwind_for_legging: bool = True


class RoutingPolicy(StrictModel):
    default_order_type: OrderType = OrderType.LIMIT
    default_tif: TimeInForce = TimeInForce.DAY
    default_venue: str
    max_slice_quantity: PositiveDecimal
    slice_interval_seconds: int = Field(default=1, ge=0)
    order_lifetime_seconds: int = Field(default=300, gt=0)
    use_market_for_critical: bool = False

    @property
    def slice_interval(self) -> timedelta:
        return timedelta(seconds=self.slice_interval_seconds)

    @property
    def order_lifetime(self) -> timedelta:
        return timedelta(seconds=self.order_lifetime_seconds)


class CostPolicy(StrictModel):
    currency: str = "USD"
    fee_per_unit: NonNegativeDecimal
    minimum_fee: NonNegativeDecimal
    slippage_bps: NonNegativeDecimal
    impact_coefficient: NonNegativeDecimal
    annualized_volatility: NonNegativeDecimal
    delay_bps: NonNegativeDecimal
    opportunity_bps: NonNegativeDecimal
    legging_bps: NonNegativeDecimal
    borrow_bps: NonNegativeDecimal


class ExecutionModelPolicy(StrictModel):
    latency_milliseconds: int = Field(default=0, ge=0)
    aggressive_slippage_bps: NonNegativeDecimal = Decimal("0")
    passive_fill_fraction: Fraction = Decimal("1")
    queue_ahead_quantity: NonNegativeDecimal = Decimal("0")
    fee_per_unit: NonNegativeDecimal = Decimal("0")


class S7PolicyBundle(StrictModel):
    intent: IntentPolicy
    structure: StructurePolicy
    routing: RoutingPolicy
    cost: CostPolicy
    execution: ExecutionModelPolicy
