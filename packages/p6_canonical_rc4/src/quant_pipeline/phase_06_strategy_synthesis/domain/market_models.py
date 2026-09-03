"""Canonical point-in-time market and P5 belief models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from ..foundation.artifacts import FrozenModel
from ..foundation.hashing import utc
from .enums import (
    CapabilityStatus,
    ExerciseStyle,
    InstrumentType,
    OptionType,
    QuoteQuality,
    SettlementType,
)

class InstrumentReference(FrozenModel):
    instrument_id: str
    instrument_type: InstrumentType
    underlying_id: str
    currency: str
    exchange: str
    multiplier: Decimal = Field(gt=0)
    valid_from: datetime
    valid_until: datetime | None = None
    source_artifact_id: str
    source_record_id: str

    @field_validator("valid_from", "valid_until")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else utc(value)


class OptionContractReference(FrozenModel):
    contract_id: str
    underlying_id: str
    option_type: OptionType
    strike: Decimal = Field(gt=0)
    expiration: datetime
    exercise_style: ExerciseStyle
    settlement_type: SettlementType
    multiplier: Decimal = Field(gt=0)
    currency: str
    listing_exchange: str
    first_trade_date: datetime
    last_trade_date: datetime | None = None
    contract_status: str = "ACTIVE"
    source_artifact_id: str
    source_record_id: str

    @field_validator("expiration", "first_trade_date", "last_trade_date")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else utc(value)


class ExecutableQuote(FrozenModel):
    contract_id: str
    quote_time: datetime
    available_at: datetime
    bid: Decimal | None = Field(default=None, ge=0)
    ask: Decimal | None = Field(default=None, ge=0)
    bid_size: Decimal | None = Field(default=None, ge=0)
    ask_size: Decimal | None = Field(default=None, ge=0)
    last: Decimal | None = Field(default=None, ge=0)
    last_size: Decimal | None = Field(default=None, ge=0)
    volume: Decimal | None = Field(default=None, ge=0)
    open_interest: Decimal | None = Field(default=None, ge=0)
    implied_volatility: Decimal | None = Field(default=None, gt=0)
    quote_quality: QuoteQuality = QuoteQuality.UNAVAILABLE
    source_id: str

    @field_validator("quote_time", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return utc(value)


class UnderlyingObservation(FrozenModel):
    underlying_id: str
    quote_time: datetime
    available_at: datetime
    bid: Decimal | None = Field(default=None, ge=0)
    ask: Decimal | None = Field(default=None, ge=0)
    last: Decimal | None = Field(default=None, ge=0)
    currency: str
    exchange: str
    trading_status: str = "OPEN"
    source_artifact_id: str
    source_record_id: str

    @field_validator("quote_time", "available_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def require_price(self) -> "UnderlyingObservation":
        if self.bid is None and self.ask is None and self.last is None:
            raise ValueError("underlying observation requires bid, ask, or last")
        return self


class BeliefScenario(FrozenModel):
    scenario_id: str
    terminal_underlying_price: Decimal = Field(ge=0)
    probability: Decimal = Field(ge=0, le=1)
    path_prices: tuple[Decimal, ...] = ()


class MarketBeliefState(FrozenModel):
    belief_state_id: str
    underlying_id: str
    decision_time: datetime
    horizon_days: int = Field(gt=0)
    scenarios: tuple[BeliefScenario, ...]
    confidence: Decimal = Field(ge=0, le=1)
    regime_context: str
    ambiguity_set_id: str | None = None
    ambiguity_probabilities: tuple[tuple[Decimal, ...], ...] = ()
    scenario_capability: CapabilityStatus = CapabilityStatus.AVAILABLE
    ambiguity_capability: CapabilityStatus = CapabilityStatus.UNAVAILABLE
    surface_capability: CapabilityStatus = CapabilityStatus.UNAVAILABLE
    source_artifact_id: str
    source_record_id: str | None = None
    source_lineage_id: str | None = None
    source_manifest_id: str | None = None
    p5_contract_version: str | None = None
    scenario_source: str = "NATIVE_MARKET_BELIEF"
    scenario_mass_audit: dict[str, Decimal | int | str | bool | None] = Field(default_factory=dict)
    calibration_status: str = "UNAVAILABLE"
    abstained: bool | None = None
    ood_severity: str = "UNAVAILABLE"
    confidence_components: dict[str, Decimal | None] = Field(default_factory=dict)
    capability_reason_codes: tuple[str, ...] = ()
    ambiguity_distribution_ids: tuple[str, ...] = ()
    ambiguity_radius: Decimal | None = Field(default=None, ge=0)

    @field_validator("decision_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)

    @model_validator(mode="after")
    def validate_probability_mass(self) -> "MarketBeliefState":
        if self.scenario_capability is CapabilityStatus.AVAILABLE:
            if not self.scenarios:
                raise ValueError("available scenario capability requires scenarios")
            mass = sum((item.probability for item in self.scenarios), Decimal("0"))
            if abs(mass - Decimal("1")) > Decimal("0.00000001"):
                raise ValueError("scenario probabilities must sum to one")
        elif self.scenarios:
            raise ValueError("limited or unavailable scenario capability cannot carry synthetic scenarios")
        for probabilities in self.ambiguity_probabilities:
            if len(probabilities) != len(self.scenarios):
                raise ValueError("ambiguity probabilities must align with scenarios")
            mass = sum(probabilities, Decimal("0"))
            if abs(mass - Decimal("1")) > Decimal("0.00000001"):
                raise ValueError("ambiguity probabilities must sum to one")
        if self.ambiguity_probabilities and self.ambiguity_capability is not CapabilityStatus.AVAILABLE:
            raise ValueError("ambiguity alternatives require AVAILABLE capability")
        return self


