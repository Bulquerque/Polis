"""P9.S8.M05 — implementation shortfall, costs, fill quality, and lifecycle."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from quant_pipeline.phase_09.subphases.s07_prospective_validation.contracts import (
    EvidenceClass,
    NonEmptyStr,
    StrictModel,
)

from .canonical import payload_sha256
from .contracts import AttributionQuality


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionRecord(StrictModel):
    order_id: NonEmptyStr
    side: OrderSide
    target_quantity: float = Field(ge=0.0)
    ordered_quantity: float = Field(ge=0.0)
    filled_quantity: float = Field(ge=0.0)
    decision_price: float = Field(gt=0.0)
    arrival_price: float = Field(gt=0.0)
    average_fill_price: float | None = Field(default=None, gt=0.0)
    evaluation_price: float = Field(gt=0.0)
    fees: float = Field(default=0.0, ge=0.0)
    borrow_cost: float = Field(default=0.0, ge=0.0)
    financing_cost: float = Field(default=0.0, ge=0.0)
    estimated_slippage_cost: float | None = Field(default=None, ge=0.0)
    combo_execution: bool = False
    legging_cost: float = Field(default=0.0, ge=0.0)
    evidence_class: EvidenceClass

    @model_validator(mode="after")
    def validate_execution(self) -> "ExecutionRecord":
        if self.filled_quantity > self.ordered_quantity:
            raise ValueError("filled_quantity cannot exceed ordered_quantity")
        if self.filled_quantity > 0.0 and self.average_fill_price is None:
            raise ValueError("filled quantity requires average_fill_price")
        if self.filled_quantity == 0.0 and self.average_fill_price is not None:
            raise ValueError("zero fill cannot have average_fill_price")
        if self.combo_execution and self.legging_cost != 0.0:
            raise ValueError("combo execution cannot carry legging cost")
        return self


class LifecycleEvent(StrictModel):
    position_id: NonEmptyStr
    planned_event: NonEmptyStr
    actual_event: NonEmptyStr
    planned_pnl: float
    actual_pnl: float
    evidence_class: EvidenceClass


class ExecutionAttributionPolicy(StrictModel):
    quantity_tolerance: float = Field(default=1e-12, ge=0.0)


class OrderShortfall(StrictModel):
    order_id: NonEmptyStr
    delay_cost: float
    trading_cost: float
    opportunity_cost: float
    explicit_cost: float
    legging_cost: float
    total_shortfall: float
    fill_rate: float = Field(ge=0.0, le=1.0)
    slippage_model_error: float | None
    evidence_class: EvidenceClass


class LifecycleAttribution(StrictModel):
    position_id: NonEmptyStr
    planned_event: NonEmptyStr
    actual_event: NonEmptyStr
    lifecycle_pnl_effect: float
    matched_plan: bool
    evidence_class: EvidenceClass


class ExecutionAttributionResult(StrictModel):
    orders: tuple[OrderShortfall, ...]
    lifecycle: tuple[LifecycleAttribution, ...]
    total_delay_cost: float
    total_trading_cost: float
    total_opportunity_cost: float
    total_explicit_cost: float
    total_legging_cost: float
    total_shortfall: float
    lifecycle_pnl_effect: float
    aggregate_pnl_effect: float
    quality: AttributionQuality
    reason_codes: tuple[NonEmptyStr, ...]
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def attribute_execution_and_lifecycle(
    executions: tuple[ExecutionRecord, ...],
    lifecycle_events: tuple[LifecycleEvent, ...],
    policy: ExecutionAttributionPolicy,
) -> ExecutionAttributionResult:
    """Compute Perold-style shortfall components and lifecycle deviations."""

    order_ids = [item.order_id for item in executions]
    if len(order_ids) != len(set(order_ids)):
        raise ValueError("duplicate order_id")
    orders = tuple(_order_shortfall(item, policy) for item in executions)
    lifecycle = tuple(
        LifecycleAttribution(
            position_id=item.position_id,
            planned_event=item.planned_event,
            actual_event=item.actual_event,
            lifecycle_pnl_effect=item.actual_pnl - item.planned_pnl,
            matched_plan=item.actual_event == item.planned_event,
            evidence_class=item.evidence_class,
        )
        for item in lifecycle_events
    )
    delay = sum(item.delay_cost for item in orders)
    trading = sum(item.trading_cost for item in orders)
    opportunity = sum(item.opportunity_cost for item in orders)
    explicit = sum(item.explicit_cost for item in orders)
    legging = sum(item.legging_cost for item in orders)
    shortfall = sum(item.total_shortfall for item in orders)
    lifecycle_effect = sum(item.lifecycle_pnl_effect for item in lifecycle)
    reasons: set[str] = set()
    if any(item.fill_rate == 0.0 and item.opportunity_cost == 0.0 for item in orders):
        reasons.add("P9_ATTRIBUTION_NO_FILL_UNVALUED")
    if any(not item.matched_plan for item in lifecycle):
        reasons.add("P9_ATTRIBUTION_LIFECYCLE_DEVIATION")
    quality = AttributionQuality.LIMITED if reasons else AttributionQuality.QUALIFIED
    aggregate = -shortfall + lifecycle_effect
    payload = {
        "orders": [item.model_dump(mode="json") for item in orders],
        "lifecycle": [item.model_dump(mode="json") for item in lifecycle],
        "aggregate_pnl_effect": aggregate,
        "quality": quality,
        "reason_codes": sorted(reasons),
    }
    return ExecutionAttributionResult(
        orders=orders,
        lifecycle=lifecycle,
        total_delay_cost=delay,
        total_trading_cost=trading,
        total_opportunity_cost=opportunity,
        total_explicit_cost=explicit,
        total_legging_cost=legging,
        total_shortfall=shortfall,
        lifecycle_pnl_effect=lifecycle_effect,
        aggregate_pnl_effect=aggregate,
        quality=quality,
        reason_codes=tuple(sorted(reasons)),
        result_sha256=payload_sha256(payload),
    )


def _order_shortfall(
    item: ExecutionRecord,
    policy: ExecutionAttributionPolicy,
) -> OrderShortfall:
    sign = 1.0 if item.side is OrderSide.BUY else -1.0
    filled = item.filled_quantity
    unfilled = max(0.0, item.ordered_quantity - filled)
    delay = sign * (item.arrival_price - item.decision_price) * filled
    trading = 0.0
    if item.average_fill_price is not None:
        trading = sign * (item.average_fill_price - item.arrival_price) * filled
    opportunity = sign * (item.evaluation_price - item.decision_price) * unfilled
    explicit = item.fees + item.borrow_cost + item.financing_cost
    total = delay + trading + opportunity + explicit + item.legging_cost
    fill_rate = (
        filled / item.ordered_quantity
        if item.ordered_quantity > policy.quantity_tolerance
        else 0.0
    )
    actual_slippage = max(0.0, delay + trading + opportunity)
    model_error = (
        actual_slippage - item.estimated_slippage_cost
        if item.estimated_slippage_cost is not None
        else None
    )
    return OrderShortfall(
        order_id=item.order_id,
        delay_cost=delay,
        trading_cost=trading,
        opportunity_cost=opportunity,
        explicit_cost=explicit,
        legging_cost=item.legging_cost,
        total_shortfall=total,
        fill_rate=fill_rate,
        slippage_model_error=model_error,
        evidence_class=item.evidence_class,
    )
