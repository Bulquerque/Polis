from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import Field

from quant_pipeline.phase_08_portfolio_control.foundation.enums import OrderStatus
from quant_pipeline.phase_08_portfolio_control.foundation.models import NonEmptyStr, StrictModel, TimeAwareModel
from quant_pipeline.phase_08_portfolio_control.subphases.s07_execution.models import FillEvent, OrderEvent
from .accounting_models import (
    CashLedgerEntry, CollateralLedgerEntry, CostLedgerEntry, JournalEntry, MarginLedgerEntry,
    PremiumLedgerEntry, RealizedPnLEntry,
)
from .base_models import SignedDecimal
from .enums import EvidenceStatus, PositionTransitionType, StatefulEventKind, StatefulPriority
from .management_models import ManagementDecisionBundle
from .valuation_models import ValuationBundle

PayloadT = TypeVar("PayloadT")


class StatefulEventEnvelope(TimeAwareModel, Generic[PayloadT]):
    event_key: NonEmptyStr
    event_time: datetime
    priority: StatefulPriority
    kind: StatefulEventKind
    payload: PayloadT
    source_sequence: int = Field(default=0, ge=0)


class OrderedEventQueue(StrictModel):
    events: tuple[StatefulEventEnvelope[object], ...]
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class OrderStateRecord(TimeAwareModel):
    order_id: NonEmptyStr
    as_of_time: datetime
    status: OrderStatus
    ordered_quantity: SignedDecimal
    cumulative_filled_quantity: SignedDecimal
    remaining_quantity: SignedDecimal
    last_sequence: int = Field(ge=0)


class TransitionAuditRecord(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    order_id: NonEmptyStr
    before_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    after_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotent_replay: bool


class ExecutionStateBundle(StrictModel):
    orders: tuple[OrderStateRecord, ...]
    order_events: tuple[OrderEvent, ...]
    fills: tuple[FillEvent, ...]
    transition_audit: tuple[TransitionAuditRecord, ...]
    order_ledger_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    fill_ledger_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PhysicalPositionState(TimeAwareModel):
    instrument_id: NonEmptyStr
    as_of_time: datetime
    quantity: SignedDecimal
    signed_cost_basis: SignedDecimal
    average_entry_price: Decimal | None
    opened_at: datetime | None
    realized_pnl: SignedDecimal


class VirtualPositionState(TimeAwareModel):
    candidate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    as_of_time: datetime
    quantity: SignedDecimal
    signed_cost_basis: SignedDecimal
    average_entry_price: Decimal | None
    opened_at: datetime | None
    realized_pnl: SignedDecimal


class PositionTransition(TimeAwareModel):
    transition_id: NonEmptyStr
    source_event_id: NonEmptyStr
    event_time: datetime
    instrument_id: NonEmptyStr
    candidate_id: str | None
    transition_type: PositionTransitionType
    quantity_before: SignedDecimal
    quantity_delta: SignedDecimal
    quantity_after: SignedDecimal
    signed_cost_basis_before: SignedDecimal
    signed_cost_basis_after: SignedDecimal
    realized_pnl_delta: SignedDecimal
    cash_trade_delta: SignedDecimal
    currency: NonEmptyStr


class SettlementRecord(TimeAwareModel):
    settlement_id: NonEmptyStr
    source_event_id: NonEmptyStr
    event_time: datetime
    currency: NonEmptyStr
    cash_delta: SignedDecimal
    underlying_instrument_id: str | None
    underlying_quantity_delta: SignedDecimal = Decimal("0")
    reason_code: NonEmptyStr


class LifecycleLedgerRecord(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    instrument_id: NonEmptyStr
    event_type: NonEmptyStr
    reason_code: NonEmptyStr


class PositionLifecycleBundle(StrictModel):
    physical_positions: tuple[PhysicalPositionState, ...]
    virtual_positions: tuple[VirtualPositionState, ...]
    transitions: tuple[PositionTransition, ...]
    lifecycle_ledger: tuple[LifecycleLedgerRecord, ...]
    settlements: tuple[SettlementRecord, ...]
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CurrencyAccountStateFinal(StrictModel):
    currency: NonEmptyStr
    cash_available: SignedDecimal
    collateral_restricted: SignedDecimal
    liabilities: SignedDecimal
    margin_used: SignedDecimal


class AccountingBundle(StrictModel):
    accounts: tuple[CurrencyAccountStateFinal, ...]
    journal_entries: tuple[JournalEntry, ...]
    cash_ledger: tuple[CashLedgerEntry, ...]
    premium_ledger: tuple[PremiumLedgerEntry, ...]
    cost_ledger: tuple[CostLedgerEntry, ...]
    margin_ledger: tuple[MarginLedgerEntry, ...]
    collateral_ledger: tuple[CollateralLedgerEntry, ...]
    realized_pnl_ledger: tuple[RealizedPnLEntry, ...]
    balanced: bool
    external_flow_delta: SignedDecimal
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class PortfolioStateCheckpoint(TimeAwareModel):
    checkpoint_id: NonEmptyStr
    as_of_time: datetime
    cycle_id: NonEmptyStr
    state_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    ordered_event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    module_version: NonEmptyStr
    event_offsets: dict[str, int]


class ReplayManifest(StrictModel):
    replay_id: NonEmptyStr
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    ordered_event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_state_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    module_version: NonEmptyStr


class StatefulEvidenceBundle(StrictModel):
    bundle_id: NonEmptyStr
    status: EvidenceStatus
    execution_state: ExecutionStateBundle
    positions: PositionLifecycleBundle
    accounting: AccountingBundle
    valuation: ValuationBundle
    management: ManagementDecisionBundle
    checkpoint: PortfolioStateCheckpoint
    replay_manifest: ReplayManifest
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
