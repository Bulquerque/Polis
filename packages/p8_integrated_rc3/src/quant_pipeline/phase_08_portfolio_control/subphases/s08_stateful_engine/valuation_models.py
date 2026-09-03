from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import Field, model_validator

from quant_pipeline.phase_08_portfolio_control.foundation.models import NonEmptyStr, PositiveDecimal, StrictModel, TimeAwareModel
from .base_models import EquityPoint, FxRate, SignedDecimal
from .enums import MarkType, ValuationStatus


class MarkRecord(TimeAwareModel):
    mark_id: NonEmptyStr
    instrument_id: NonEmptyStr
    mark_type: MarkType
    price: Decimal | None
    event_time: datetime
    available_at: datetime
    model_ref: str | None = None

    @model_validator(mode="after")
    def validate_mark(self):
        if self.available_at < self.event_time:
            raise ValueError("available_at cannot precede event_time")
        if self.mark_type == MarkType.UNAVAILABLE:
            if self.price is not None:
                raise ValueError("UNAVAILABLE mark cannot have price")
        elif self.price is None or self.price <= 0:
            raise ValueError("available marks require positive price")
        if self.mark_type == MarkType.MODEL and not self.model_ref:
            raise ValueError("MODEL mark requires model_ref")
        return self


class MarkSnapshot(TimeAwareModel):
    snapshot_id: NonEmptyStr
    valuation_time: datetime
    marks: tuple[MarkRecord, ...]
    fx_rates: tuple[FxRate, ...]


class MarkSelectionPolicy(StrictModel):
    preferred_types: tuple[MarkType, ...] = (
        MarkType.MID, MarkType.LAST, MarkType.SETTLEMENT, MarkType.MODEL, MarkType.BID, MarkType.ASK,
    )
    stale_after_seconds: int = Field(default=300, ge=0)
    allow_stale: bool = False
    allow_model: bool = True


class PositionValuation(TimeAwareModel):
    instrument_id: NonEmptyStr
    as_of_time: datetime
    currency: NonEmptyStr
    quantity: SignedDecimal
    mark_type: MarkType
    mark_price: Decimal | None
    market_value: Decimal | None
    signed_cost_basis: SignedDecimal
    unrealized_pnl: Decimal | None
    mark_age_seconds: int | None


class CandidateValuation(TimeAwareModel):
    candidate_id: NonEmptyStr
    instrument_id: NonEmptyStr
    as_of_time: datetime
    currency: NonEmptyStr
    quantity: SignedDecimal
    market_value: Decimal | None
    signed_cost_basis: SignedDecimal
    unrealized_pnl: Decimal | None


class NAVRecord(TimeAwareModel):
    as_of_time: datetime
    functional_currency: NonEmptyStr
    status: ValuationStatus
    total_nav: Decimal | None
    known_nav_component: SignedDecimal
    unpriced_instruments: tuple[NonEmptyStr, ...]
    net_external_flow: SignedDecimal
    period_pnl: Decimal | None


class DrawdownRecord(TimeAwareModel):
    as_of_time: datetime
    peak_nav: SignedDecimal
    current_nav: SignedDecimal
    drawdown_amount: SignedDecimal
    drawdown_fraction: Decimal


class ValuationBundle(StrictModel):
    positions: tuple[PositionValuation, ...]
    candidates: tuple[CandidateValuation, ...]
    nav: NAVRecord
    equity_curve: tuple[EquityPoint, ...]
    drawdown: DrawdownRecord | None
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
