from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from pydantic import Field, model_validator
from .enums import CandidateTerminalState, LedgerCategory, MarkQuality, OrderSide, PnLQuality
from .models_common import ArtifactRef, AuditContext, DecimalTolerance, StrictModel

class CandidateStateRecord(StrictModel):
    candidate_id: str = Field(min_length=1)
    terminal_state: CandidateTerminalState

class OrderRecord(StrictModel):
    order_id: str = Field(min_length=1)
    source_order_id: str | None = None
    instrument_id: str = Field(min_length=1)
    side: OrderSide
    total_quantity: Decimal = Field(gt=0)
    filled_quantity: Decimal = Field(ge=0)
    cancelled_quantity: Decimal = Field(ge=0)
    rejected_quantity: Decimal = Field(ge=0)
    open_quantity: Decimal = Field(ge=0)

class FillRecord(StrictModel):
    fill_id: str = Field(min_length=1)
    source_fill_id: str | None = None
    order_id: str = Field(min_length=1)
    source_order_id: str | None = None
    instrument_id: str = Field(min_length=1)
    side: OrderSide
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fees: Decimal = Field(ge=0)

class PositionRecord(StrictModel):
    instrument_id: str = Field(min_length=1)
    quantity: Decimal

class VirtualAllocation(StrictModel):
    candidate_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    quantity: Decimal

class LedgerEntry(StrictModel):
    entry_id: str = Field(min_length=1)
    category: LedgerCategory
    currency: str = Field(default="FUNCTIONAL", min_length=1)
    amount: Decimal
    event_time: datetime
    @model_validator(mode="after")
    def category_sign(self) -> "LedgerEntry":
        if self.category == LedgerCategory.COST and self.amount > 0:
            raise ValueError("COST amount must be non-positive")
        if self.category in {LedgerCategory.MARGIN, LedgerCategory.COLLATERAL, LedgerCategory.LIABILITY} and self.amount < 0:
            raise ValueError(f"{self.category} amount must be non-negative")
        return self

class CurrencyAccountSnapshot(StrictModel):
    currency: str = Field(min_length=1)
    functional_fx_rate: Decimal = Field(default=Decimal("1"), gt=0)
    initial_cash: Decimal
    final_cash: Decimal
    margin_used: Decimal = Field(ge=0)
    collateral_value: Decimal = Field(ge=0)
    liabilities: Decimal = Field(ge=0)


class AccountSnapshot(StrictModel):
    functional_currency: str = Field(default="USD", min_length=1)
    initial_cash: Decimal
    final_cash: Decimal
    margin_used: Decimal = Field(ge=0)
    collateral_value: Decimal = Field(ge=0)
    liabilities: Decimal = Field(ge=0)
    initial_nav: Decimal
    external_cashflows: Decimal = Decimal("0")
    currency_accounts: tuple[CurrencyAccountSnapshot, ...] = ()

    @model_validator(mode="after")
    def unique_currency_accounts(self) -> "AccountSnapshot":
        currencies = [item.currency for item in self.currency_accounts]
        if len(currencies) != len(set(currencies)):
            raise ValueError("currency account snapshots must be unique by currency")
        return self

class ValuationRecord(StrictModel):
    instrument_id: str = Field(min_length=1)
    currency: str = Field(default="FUNCTIONAL", min_length=1)
    functional_fx_rate: Decimal | None = Field(default=Decimal("1"), gt=0)
    quantity: Decimal
    mark_price: Decimal | None
    market_value: Decimal | None
    functional_market_value: Decimal | None = None
    mark_quality: MarkQuality


    @model_validator(mode="after")
    def unavailable_consistency(self) -> "ValuationRecord":
        unavailable = self.mark_quality == MarkQuality.UNAVAILABLE
        if unavailable and any(
            item is not None
            for item in (self.mark_price, self.market_value, self.functional_market_value)
        ):
            raise ValueError("unavailable mark cannot contain price or market value")
        if not unavailable and (self.mark_price is None or self.market_value is None):
            raise ValueError("available mark requires local valuation")
        if self.market_value is not None:
            if self.functional_fx_rate is None:
                raise ValueError("available mark requires functional FX rate")
            expected = self.market_value * self.functional_fx_rate
            if (
                self.functional_market_value is not None
                and self.functional_market_value != expected
            ):
                raise ValueError("functional market value does not match FX conversion")
        return self

class PnLSnapshot(StrictModel):
    quality: PnLQuality = PnLQuality.COMPLETE
    realized_pnl: Decimal | None
    unrealized_pnl: Decimal | None
    costs: Decimal | None
    total_pnl: Decimal | None

    @model_validator(mode="after")
    def availability_consistency(self) -> "PnLSnapshot":
        values = (self.realized_pnl, self.unrealized_pnl, self.costs, self.total_pnl)
        if self.quality == PnLQuality.COMPLETE and any(item is None for item in values):
            raise ValueError("complete PnL snapshot requires every component")
        if self.quality == PnLQuality.UNAVAILABLE and any(item is not None for item in values):
            raise ValueError("unavailable PnL snapshot cannot contain numeric components")
        return self

class ReplayEvent(StrictModel):
    sequence: int = Field(ge=0)
    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    instrument_id: str | None = None
    candidate_id: str | None = None
    quantity_delta: Decimal = Decimal("0")
    cash_delta: Decimal = Decimal("0")

class ReplayCheckpoint(StrictModel):
    expected_state_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

class StatefulEvidenceBundle(StrictModel):
    bundle_id: str = Field(min_length=1)
    context: AuditContext
    expected_candidate_ids: tuple[str, ...]
    candidate_states: tuple[CandidateStateRecord, ...]
    initial_positions: tuple[PositionRecord, ...]
    orders: tuple[OrderRecord, ...]
    fills: tuple[FillRecord, ...]
    final_positions: tuple[PositionRecord, ...]
    virtual_allocations: tuple[VirtualAllocation, ...]
    ledger_entries: tuple[LedgerEntry, ...]
    account_snapshot: AccountSnapshot
    valuations: tuple[ValuationRecord, ...]
    pnl_snapshot: PnLSnapshot
    replay_events: tuple[ReplayEvent, ...]
    replay_checkpoint: ReplayCheckpoint
    source_artifacts: tuple[ArtifactRef, ...]
    tolerance: DecimalTolerance = DecimalTolerance()
