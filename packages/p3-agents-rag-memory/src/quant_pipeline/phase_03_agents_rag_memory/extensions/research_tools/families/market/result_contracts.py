from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel

from .types import (
    NonEmptyStr,
    OptionType,
    OutcomeStatus,
    Probability,
    Sha256,
    SurfaceDiagnosticStatus,
    aware_utc,
)


class MarketObservation(ContractModel):
    instrument_id: NonEmptyStr
    observation_date: date
    available_at: datetime
    open: float | None = Field(default=None, ge=0.0)
    high: float | None = Field(default=None, ge=0.0)
    low: float | None = Field(default=None, ge=0.0)
    raw_close: float = Field(ge=0.0)
    close: float = Field(ge=0.0)
    adjustment_policy: NonEmptyStr = "RAW"
    volume: float | None = Field(default=None, ge=0.0)
    financial_volume: float | None = Field(default=None, ge=0.0)
    adjustment_factor: float | None = Field(default=None, gt=0.0)
    is_trading_day: bool | None = None
    source_id: NonEmptyStr
    lineage_id: NonEmptyStr
    quality_flag: NonEmptyStr
    staleness_seconds: float = Field(ge=0.0)

    _available = field_validator("available_at")(aware_utc)

    @model_validator(mode="after")
    def ohlc_is_consistent(self) -> "MarketObservation":
        observed = [value for value in (self.open, self.close, self.low) if value is not None]
        if self.high is not None and observed and self.high < max(observed):
            raise ValueError("high cannot be below observed prices")
        observed_high = [value for value in (self.open, self.close, self.high) if value is not None]
        if self.low is not None and observed_high and self.low > min(observed_high):
            raise ValueError("low cannot be above observed prices")
        return self


class LiquidityDiagnostic(ContractModel):
    instrument_id: NonEmptyStr
    window_start: date
    window_end: date
    observations: int = Field(ge=0)
    average_volume: float | None = Field(default=None, ge=0.0)
    median_volume: float | None = Field(default=None, ge=0.0)
    average_financial_volume: float | None = Field(default=None, ge=0.0)
    average_relative_spread: float | None = Field(default=None, ge=0.0)
    latest_liquidity_score: float | None = Field(default=None, ge=0.0)
    tradable_fraction: Probability | None = None
    missing_volume_fraction: Probability
    missing_spread_fraction: Probability
    source_ids: tuple[NonEmptyStr, ...]


class CorporateActionObservation(ContractModel):
    instrument_id: NonEmptyStr
    action_type: NonEmptyStr
    available_at: datetime
    effective_date: date | None = None
    ex_date: date | None = None
    record_date: date | None = None
    payment_date: date | None = None
    adjustment_factor: float | None = Field(default=None, gt=0.0)
    cash_amount: float | None = Field(default=None, ge=0.0)
    ratio: float | None = Field(default=None, gt=0.0)
    source_id: NonEmptyStr
    lineage_id: NonEmptyStr

    _available = field_validator("available_at")(aware_utc)


class InstrumentComparisonObservation(ContractModel):
    instrument_id: NonEmptyStr
    start_date: date
    end_date: date
    observation_count: int = Field(ge=1)
    first_close: float = Field(gt=0.0)
    last_close: float = Field(ge=0.0)
    cumulative_return: float
    normalized_last_value: float
    missing_trading_day_fraction: Probability
    source_ids: tuple[NonEmptyStr, ...]


class OptionContractObservation(ContractModel):
    contract_key: NonEmptyStr
    option_id: NonEmptyStr
    underlying: NonEmptyStr
    option_type: OptionType
    strike: float = Field(gt=0.0)
    expiration_date: date
    contract_size: float | None = Field(default=None, gt=0.0)
    first_seen_date: date
    last_seen_date: date | None = None
    source_id: NonEmptyStr
    lineage_id: NonEmptyStr
    quality_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def seen_dates_are_ordered(self) -> "OptionContractObservation":
        if self.last_seen_date and self.last_seen_date < self.first_seen_date:
            raise ValueError("last_seen_date must be >= first_seen_date")
        return self


class OptionQuoteObservation(ContractModel):
    contract_key: NonEmptyStr
    underlying: NonEmptyStr
    option_type: OptionType
    strike: float = Field(gt=0.0)
    expiration_date: date
    observation_date: date
    available_at: datetime
    bid: float | None = Field(default=None, ge=0.0)
    ask: float | None = Field(default=None, ge=0.0)
    last_price: float | None = Field(default=None, ge=0.0)
    mid: float | None = Field(default=None, ge=0.0)
    volume: float | None = Field(default=None, ge=0.0)
    financial_volume: float | None = Field(default=None, ge=0.0)
    open_interest: float | None = Field(default=None, ge=0.0)
    implied_volatility: float | None = Field(default=None, ge=0.0)
    execution_status: NonEmptyStr
    source_id: NonEmptyStr
    lineage_id: NonEmptyStr
    quality_flag: NonEmptyStr

    _available = field_validator("available_at")(aware_utc)

    @model_validator(mode="after")
    def quote_is_consistent(self) -> "OptionQuoteObservation":
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        if self.mid is not None and self.bid is not None and self.mid < self.bid:
            raise ValueError("mid cannot be below bid")
        if self.mid is not None and self.ask is not None and self.mid > self.ask:
            raise ValueError("mid cannot be above ask")
        return self


class SurfaceSliceDiagnostic(ContractModel):
    expiration_date: date
    option_type: OptionType | None
    quote_count: int = Field(ge=0)
    strike_count: int = Field(ge=0)
    executable_quote_fraction: Probability
    two_sided_quote_fraction: Probability
    observed_iv_fraction: Probability
    minimum_strike: float | None = Field(default=None, gt=0.0)
    maximum_strike: float | None = Field(default=None, gt=0.0)
    median_iv: float | None = Field(default=None, ge=0.0)
    atm_iv: float | None = Field(default=None, ge=0.0)
    skew_slope: float | None = None
    price_monotonicity_violations: int = Field(default=0, ge=0)
    convexity_violations: int = Field(default=0, ge=0)
    diagnostic_status: SurfaceDiagnosticStatus
    warnings: tuple[str, ...] = ()


class SurfaceDiagnosticSummary(ContractModel):
    underlying: NonEmptyStr
    decision_time: datetime
    underlying_spot: float | None = Field(default=None, ge=0.0)
    slices: tuple[SurfaceSliceDiagnostic, ...]
    calendar_variance_violations: int = Field(default=0, ge=0)
    interpolation_performed: Literal[False] = False
    implied_volatility_solved: Literal[False] = False
    warnings: tuple[str, ...] = ()

    _decision = field_validator("decision_time")(aware_utc)


class MarketEvidenceRef(ContractModel):
    evidence_id: NonEmptyStr
    view_name: NonEmptyStr
    record_key: NonEmptyStr
    source_id: NonEmptyStr
    lineage_id: NonEmptyStr
    available_at: datetime
    record_hash: Sha256

    _available = field_validator("available_at")(aware_utc)


class CoverageReport(ContractModel):
    records_scanned: int = Field(ge=0)
    records_visible: int = Field(ge=0)
    records_returned: int = Field(ge=0)
    records_rejected_future: int = Field(ge=0)
    records_rejected_missing_time: int = Field(ge=0)
    records_rejected_filter: int = Field(ge=0)
    unique_sources: int = Field(ge=0)
    score: Probability
    missing_dimensions: tuple[str, ...] = ()
    truncated: bool = False

    @model_validator(mode="after")
    def counts_are_consistent(self) -> "CoverageReport":
        if self.records_visible > self.records_scanned:
            raise ValueError("records_visible cannot exceed records_scanned")
        if self.records_returned < 0:
            raise ValueError("records_returned cannot be negative")
        return self


class PitQueryProof(ContractModel):
    decision_time: datetime
    records_scanned: int = Field(ge=0)
    records_visible: int = Field(ge=0)
    records_rejected_future: int = Field(ge=0)
    records_rejected_missing_time: int = Field(ge=0)
    records_rejected_filter: int = Field(ge=0)
    earliest_available_at: datetime | None = None
    latest_available_at: datetime | None = None
    snapshot_id: NonEmptyStr
    input_hashes: tuple[Sha256, ...]
    proof_hash: Sha256

    _decision = field_validator("decision_time")(aware_utc)
    _times = field_validator("earliest_available_at", "latest_available_at")(aware_utc)

    @model_validator(mode="after")
    def proof_is_consistent(self) -> "PitQueryProof":
        if self.latest_available_at and self.latest_available_at > self.decision_time:
            raise ValueError("PIT proof contains evidence after decision_time")
        if self.earliest_available_at and self.latest_available_at:
            if self.earliest_available_at > self.latest_available_at:
                raise ValueError("earliest_available_at cannot exceed latest_available_at")
        if len(self.input_hashes) != len(set(self.input_hashes)):
            raise ValueError("input_hashes must be unique")
        return self


class ExecutionReport(ContractModel):
    handler_id: NonEmptyStr
    handler_version: Literal["1.0.0"] = "1.0.0"
    requested_mode: NonEmptyStr
    executed_mode: NonEmptyStr
    internal_work_units: int = Field(ge=0)
    deterministic: Literal[True] = True
    seed: int = Field(ge=0)
    warnings: tuple[str, ...] = ()


class MarketDerivativesToolResultEnvelope(ContractModel):
    envelope_version: Literal["1.0.0"] = "1.0.0"
    tool_id: Literal["market.observation.v1", "options.observation.v1"]
    operation_id: NonEmptyStr
    request_id: NonEmptyStr
    outcome_status: OutcomeStatus
    requested_mode: NonEmptyStr
    executed_mode: NonEmptyStr
    downgrade_reason: str | None = None
    records: tuple[dict[str, JsonValue], ...]
    evidence_refs: tuple[MarketEvidenceRef, ...]
    coverage: CoverageReport
    pit_proof: PitQueryProof
    execution: ExecutionReport
    result_hash: Sha256

    @model_validator(mode="after")
    def envelope_is_consistent(self) -> "MarketDerivativesToolResultEnvelope":
        if self.executed_mode != self.requested_mode and self.downgrade_reason is None:
            raise ValueError("mode downgrade requires downgrade_reason")
        if self.executed_mode == self.requested_mode and self.downgrade_reason is not None:
            raise ValueError("downgrade_reason requires an executed mode change")
        if self.outcome_status is OutcomeStatus.EMPTY_VALID and self.records:
            raise ValueError("EMPTY_VALID cannot contain records")
        if self.coverage.records_returned != len(self.records):
            raise ValueError("coverage records_returned must match records")
        if self.execution.requested_mode != self.requested_mode:
            raise ValueError("execution requested_mode mismatch")
        if self.execution.executed_mode != self.executed_mode:
            raise ValueError("execution executed_mode mismatch")
        return self
