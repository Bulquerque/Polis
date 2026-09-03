"""Scenario artifact, market-liquidity, account, borrow, and margin contracts."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import Field, model_validator

from .base import StrictModel
from .enums import MarginFidelity


class ScenarioArtifactBundle(StrictModel):
    root_path: str
    full_scenarios_file: str
    reduced_scenarios_file: str
    stress_scenarios_file: str
    full_scenarios_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reduced_scenarios_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    stress_scenarios_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class LiquidityQuote(StrictModel):
    instrument_id: str
    bid: float = Field(gt=0.0)
    ask: float = Field(gt=0.0)
    bid_size: float = Field(ge=0.0)
    ask_size: float = Field(ge=0.0)
    daily_volume: float | None = Field(default=None, ge=0.0)
    open_interest: float | None = Field(default=None, ge=0.0)
    quote_time: datetime
    available_at: datetime
    combo_group_id: str | None = None

    @model_validator(mode="after")
    def validate_quote(self) -> "LiquidityQuote":
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        if self.quote_time.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("quote times must be timezone-aware")
        if self.quote_time.astimezone(timezone.utc) > self.available_at.astimezone(timezone.utc):
            raise ValueError("quote_time must not be after available_at")
        return self


class MarketLiquiditySnapshot(StrictModel):
    decision_time: datetime
    quotes: tuple[LiquidityQuote, ...]

    @model_validator(mode="after")
    def validate_snapshot(self) -> "MarketLiquiditySnapshot":
        if self.decision_time.tzinfo is None:
            raise ValueError("decision_time must be timezone-aware")
        ids = [quote.instrument_id for quote in self.quotes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate quote instrument_id")
        if any(quote.quote_time > self.decision_time for quote in self.quotes):
            raise ValueError("liquidity snapshot contains future quote_time")
        if any(quote.available_at > self.decision_time for quote in self.quotes):
            raise ValueError("liquidity snapshot contains future-available quote")
        return self


class BorrowRecord(StrictModel):
    instrument_id: str
    available: bool
    quantity_available: float | None = Field(default=None, ge=0.0)
    annual_rate: float | None = Field(default=None, ge=0.0)


class AccountState(StrictModel):
    currency: str = Field(min_length=3, max_length=3)
    available_cash: float = Field(ge=0.0)
    eligible_collateral: float = Field(ge=0.0)
    current_margin_used: float = Field(ge=0.0)
    margin_limit: float = Field(ge=0.0)
    cash_buffer_required: float = Field(ge=0.0)
    max_new_risk_capital: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_margin(self) -> "AccountState":
        if self.current_margin_used > self.margin_limit:
            raise ValueError("current_margin_used exceeds margin_limit")
        return self


class MarginOffsetRule(StrictModel):
    group_id: str
    offset_fraction: float = Field(ge=0.0, le=1.0)


class MarginRules(StrictModel):
    fidelity: MarginFidelity
    exact_margin_per_candidate: dict[str, float] = Field(default_factory=dict)
    exact_portfolio_margin: float | None = Field(default=None, ge=0.0)
    base_margin_rate: float = Field(default=0.25, ge=0.0)
    short_option_margin_rate: float = Field(default=0.50, ge=0.0)
    concentration_threshold: float = Field(default=0.25, gt=0.0)
    concentration_addon_rate: float = Field(default=0.10, ge=0.0)
    recognized_offsets: tuple[MarginOffsetRule, ...] = ()

    @model_validator(mode="after")
    def validate_fidelity(self) -> "MarginRules":
        if self.fidelity == MarginFidelity.EXACT_BROKER_MODEL and not self.exact_margin_per_candidate:
            raise ValueError("exact fidelity requires exact_margin_per_candidate")
        return self
