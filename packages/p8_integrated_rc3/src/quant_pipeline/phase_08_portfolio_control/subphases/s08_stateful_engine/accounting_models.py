from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from quant_pipeline.phase_08_portfolio_control.foundation.models import NonEmptyStr, NonNegativeDecimal, TimeAwareModel
from .base_models import SignedDecimal
from .enums import AccountCode, CashAdjustmentType, JournalSide, StatefulEventKind


class MarginChangeEvent(TimeAwareModel):
    event_type: Literal[StatefulEventKind.MARGIN_CHANGE] = StatefulEventKind.MARGIN_CHANGE
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    currency: NonEmptyStr
    new_margin_used: NonNegativeDecimal
    reason_code: NonEmptyStr


class CollateralTransferEvent(TimeAwareModel):
    event_type: Literal[StatefulEventKind.COLLATERAL_TRANSFER] = StatefulEventKind.COLLATERAL_TRANSFER
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    currency: NonEmptyStr
    amount_to_restricted: SignedDecimal
    reason_code: NonEmptyStr


class CashAdjustmentEvent(TimeAwareModel):
    event_type: Literal[StatefulEventKind.CASH_ADJUSTMENT] = StatefulEventKind.CASH_ADJUSTMENT
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    currency: NonEmptyStr
    amount: SignedDecimal
    adjustment_type: CashAdjustmentType
    reason_code: NonEmptyStr


class FeeEvent(TimeAwareModel):
    event_type: Literal[StatefulEventKind.FEE] = StatefulEventKind.FEE
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    currency: NonEmptyStr
    amount: NonNegativeDecimal
    fee_type: NonEmptyStr
    reason_code: NonEmptyStr


class BorrowFeeEvent(TimeAwareModel):
    event_type: Literal[StatefulEventKind.BORROW_FEE] = StatefulEventKind.BORROW_FEE
    event_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    currency: NonEmptyStr
    amount: NonNegativeDecimal
    reason_code: NonEmptyStr


AccountEvent = Annotated[
    Union[MarginChangeEvent, CollateralTransferEvent, CashAdjustmentEvent, FeeEvent, BorrowFeeEvent],
    Field(discriminator="event_type"),
]


class JournalPosting(TimeAwareModel):
    posting_id: NonEmptyStr
    entry_id: NonEmptyStr
    event_time: datetime
    currency: NonEmptyStr
    account_code: AccountCode
    side: JournalSide
    amount: NonNegativeDecimal
    instrument_id: str | None = None
    candidate_id: str | None = None


class JournalEntry(TimeAwareModel):
    entry_id: NonEmptyStr
    source_event_id: NonEmptyStr
    event_time: datetime
    description: NonEmptyStr
    postings: tuple[JournalPosting, ...]

    @model_validator(mode="after")
    def validate_balanced(self):
        by_currency: dict[str, Decimal] = {}
        for p in self.postings:
            signed = p.amount if p.side == JournalSide.DEBIT else -p.amount
            by_currency[p.currency] = by_currency.get(p.currency, Decimal("0")) + signed
        if any(v != 0 for v in by_currency.values()):
            raise ValueError(f"journal entry is not balanced: {by_currency}")
        return self


class CashLedgerEntry(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    currency: NonEmptyStr
    delta: SignedDecimal
    balance_after: SignedDecimal
    category: NonEmptyStr


class PremiumLedgerEntry(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    instrument_id: NonEmptyStr
    currency: NonEmptyStr
    premium_cash_delta: SignedDecimal


class CostLedgerEntry(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    currency: NonEmptyStr
    cost_type: NonEmptyStr
    amount: NonNegativeDecimal


class MarginLedgerEntry(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    currency: NonEmptyStr
    margin_used_after: NonNegativeDecimal
    reason_code: NonEmptyStr


class CollateralLedgerEntry(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    currency: NonEmptyStr
    available_cash_delta: SignedDecimal
    restricted_collateral_delta: SignedDecimal
    restricted_balance_after: SignedDecimal


class RealizedPnLEntry(TimeAwareModel):
    event_id: NonEmptyStr
    event_time: datetime
    instrument_id: NonEmptyStr
    currency: NonEmptyStr
    amount: SignedDecimal
