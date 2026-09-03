from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field

from ...contracts.execution_authorization import CandidateAllocation
from ...foundation.enums import OrderEventType, OrderStatus, ReceiptStatus, RuntimeControlMode, Side
from ...foundation.models import NonEmptyStr, NonNegativeDecimal, PositiveDecimal, StrictModel, TimeAwareModel
from .intent_models import VirtualReallocation

SignedDecimal = Annotated[Decimal, Field(allow_inf_nan=False)]


class RuntimeControlCommand(TimeAwareModel):
    """Canonical S9→S7/S8 safety command.

    The original four fields remain required for backward compatibility. The
    metadata fields close idempotency, validity, source-state and feasibility
    semantics without granting S9 direct execution authority.
    """

    command_id: NonEmptyStr
    event_time: datetime
    mode: RuntimeControlMode
    reason_code: NonEmptyStr
    run_id: str | None = None
    cycle_id: str | None = None
    source_state_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    valid_until: datetime | None = None
    command_sequence: int = Field(default=0, ge=0)
    idempotency_key: str | None = None
    allowed_actions: tuple[str, ...] = ()
    feasibility_proven: bool = True
    reason_codes: tuple[str, ...] = ()


class CancelOrderCommand(TimeAwareModel):
    command_id: NonEmptyStr
    event_time: datetime
    order_id: NonEmptyStr
    reason_code: NonEmptyStr


class ReplaceOrderCommand(TimeAwareModel):
    command_id: NonEmptyStr
    event_time: datetime
    order_id: NonEmptyStr
    new_quantity: PositiveDecimal | None = None
    new_limit_price: Decimal | None = None
    reason_code: NonEmptyStr


ExecutionCommand = RuntimeControlCommand | CancelOrderCommand | ReplaceOrderCommand


class OrderEvent(TimeAwareModel):
    event_id: NonEmptyStr
    order_id: NonEmptyStr
    event_type: OrderEventType
    event_time: datetime
    status_before: OrderStatus | None
    status_after: OrderStatus
    cumulative_filled_quantity: NonNegativeDecimal
    remaining_quantity: NonNegativeDecimal
    reason_code: NonEmptyStr
    event_sequence: int = Field(ge=0)


class FillEvent(TimeAwareModel):
    fill_id: NonEmptyStr
    order_id: NonEmptyStr
    structure_id: NonEmptyStr
    execution_group_id: NonEmptyStr
    instrument_id: NonEmptyStr
    event_time: datetime
    side: Side
    quantity: PositiveDecimal
    price: PositiveDecimal
    contract_multiplier: PositiveDecimal
    fee: NonNegativeDecimal
    virtual_allocations: tuple[CandidateAllocation, ...]
    market_event_id: NonEmptyStr


class ExecutionResult(StrictModel):
    order_events: tuple[OrderEvent, ...]
    fill_events: tuple[FillEvent, ...]
    final_status_by_order: dict[str, OrderStatus]
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class OrderReconciliation(StrictModel):
    order_id: NonEmptyStr
    ordered_quantity: PositiveDecimal
    filled_quantity: NonNegativeDecimal
    cancelled_quantity: NonNegativeDecimal
    rejected_quantity: NonNegativeDecimal
    expired_quantity: NonNegativeDecimal
    open_quantity: NonNegativeDecimal
    final_status: OrderStatus
    quantity_conserved: bool


class InstrumentPositionDelta(StrictModel):
    instrument_id: NonEmptyStr
    signed_quantity_delta: SignedDecimal


class CandidateExecutionAllocation(StrictModel):
    candidate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    signed_quantity_delta: SignedDecimal


class RealizedExecutionCost(StrictModel):
    order_id: NonEmptyStr
    arrival_mid: PositiveDecimal
    implementation_shortfall: SignedDecimal
    fees: NonNegativeDecimal
    total_realized_cost: SignedDecimal
    pretrade_estimate: NonNegativeDecimal | None
    estimation_error: SignedDecimal | None


class ExecutionReceipt(StrictModel):
    receipt_id: NonEmptyStr
    status: ReceiptStatus
    order_reconciliations: tuple[OrderReconciliation, ...]
    instrument_position_deltas: tuple[InstrumentPositionDelta, ...]
    candidate_allocations: tuple[CandidateExecutionAllocation, ...]
    virtual_reallocations: tuple[VirtualReallocation, ...]
    realized_costs: tuple[RealizedExecutionCost, ...]
    order_event_ledger_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    fill_event_ledger_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
