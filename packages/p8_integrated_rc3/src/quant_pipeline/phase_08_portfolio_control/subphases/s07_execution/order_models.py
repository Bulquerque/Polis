from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from ...contracts.execution_authorization import CandidateAllocation
from ...foundation.enums import CostQuality, OrderClass, OrderType, PositionIntent, RiskRole, SecurityType, Side, TimeInForce
from ...foundation.models import NonEmptyStr, NonNegativeDecimal, PositiveDecimal, StrictModel, TimeAwareModel


class PlannedOrderLeg(StrictModel):
    intent_id: NonEmptyStr
    instrument_id: NonEmptyStr
    side: Side
    position_intent: PositionIntent
    ratio_quantity: PositiveDecimal
    quantity: PositiveDecimal
    virtual_allocations: tuple[CandidateAllocation, ...]


class PlannedOrder(TimeAwareModel):
    order_id: NonEmptyStr
    client_order_id: NonEmptyStr
    authorization_ids: tuple[NonEmptyStr, ...]
    structure_id: NonEmptyStr
    execution_group_id: NonEmptyStr
    order_class: OrderClass
    venue: NonEmptyStr
    security_type: SecurityType
    risk_role: RiskRole
    order_type: OrderType
    time_in_force: TimeInForce
    quantity: PositiveDecimal
    limit_price: Decimal | None
    submit_at: datetime
    expire_at: datetime
    slice_index: int = Field(ge=0)
    replace_allowed: bool
    legs: tuple[PlannedOrderLeg, ...]

    @model_validator(mode="after")
    def validate_order(self):
        if self.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT} and self.limit_price is None:
            raise ValueError("limit order requires limit_price")
        if self.expire_at <= self.submit_at:
            raise ValueError("expire_at must be after submit_at")
        if self.order_class == OrderClass.MLEG and len(self.legs) < 2:
            raise ValueError("MLeg requires at least two legs")
        if self.order_class == OrderClass.SIMPLE and len(self.legs) != 1:
            raise ValueError("simple order requires exactly one leg")
        return self


class RoutingBlock(StrictModel):
    structure_id: NonEmptyStr
    reason_code: NonEmptyStr


class PlannedOrderBundle(StrictModel):
    orders: tuple[PlannedOrder, ...]
    blocked_structure_ids: tuple[NonEmptyStr, ...]
    routing_blocks: tuple[RoutingBlock, ...] = ()
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_blocks(self):
        expected = tuple(item.structure_id for item in self.routing_blocks)
        if expected != self.blocked_structure_ids:
            raise ValueError("blocked_structure_ids must match routing_blocks in order")
        return self


class CostComponents(StrictModel):
    fees: NonNegativeDecimal
    spread: NonNegativeDecimal
    slippage: NonNegativeDecimal
    market_impact: NonNegativeDecimal
    delay: NonNegativeDecimal
    opportunity: NonNegativeDecimal
    legging: NonNegativeDecimal
    borrow: NonNegativeDecimal

    @property
    def total(self) -> Decimal:
        return sum((
            self.fees, self.spread, self.slippage, self.market_impact,
            self.delay, self.opportunity, self.legging, self.borrow,
        ), Decimal("0"))


class PretradeCostEstimate(StrictModel):
    order_id: NonEmptyStr
    currency: NonEmptyStr
    quality: CostQuality
    components: CostComponents
    total_cost: NonNegativeDecimal
    assumptions: tuple[str, ...]

    @model_validator(mode="after")
    def validate_total(self):
        if self.total_cost != self.components.total:
            raise ValueError("total_cost must equal component sum")
        return self


class PretradeCostBundle(StrictModel):
    estimates: tuple[PretradeCostEstimate, ...]
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
