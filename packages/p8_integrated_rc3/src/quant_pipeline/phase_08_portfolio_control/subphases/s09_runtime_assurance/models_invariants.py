from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from .enums import AlertSeverity, ReasonCode
from .models_common import RuntimeContext, StrictModel


class RuntimeInvariantSnapshot(StrictModel):
    received_candidate_count: int = Field(ge=0)
    terminal_candidate_count: int = Field(ge=0)
    order_total_quantity: Decimal = Field(ge=0)
    filled_quantity: Decimal = Field(ge=0)
    cancelled_quantity: Decimal = Field(ge=0)
    rejected_quantity: Decimal = Field(ge=0)
    open_quantity: Decimal = Field(ge=0)
    virtual_exposure_total: Decimal
    physical_allocated_total: Decimal
    opening_cash: Decimal
    net_cash_flows: Decimal
    closing_cash: Decimal
    margin_used: Decimal = Field(ge=0)
    margin_limit: Decimal = Field(gt=0)
    maximum_loss: Decimal = Field(ge=0)
    maximum_loss_limit: Decimal = Field(gt=0)
    quote_age_seconds: int = Field(ge=0)
    maximum_quote_age_seconds: int = Field(gt=0)
    lifecycle_consistent: bool
    settlement_consistent: bool
    expected_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    actual_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class InvariantPolicy(StrictModel):
    quantity_tolerance: Decimal = Field(ge=0)
    money_tolerance: Decimal = Field(ge=0)
    exposure_tolerance: Decimal = Field(ge=0)
    minimum_margin_headroom_ratio: Decimal = Field(ge=0, lt=1)


class InvariantMonitorRequest(StrictModel):
    context: RuntimeContext
    snapshot: RuntimeInvariantSnapshot
    policy: InvariantPolicy


class InvariantViolation(StrictModel):
    invariant_id: str = Field(min_length=1)
    severity: AlertSeverity
    reason_code: ReasonCode
    expected: str
    actual: str


class InvariantMonitorResult(StrictModel):
    healthy: bool
    highest_severity: AlertSeverity
    violations: tuple[InvariantViolation, ...]
