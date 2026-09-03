from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel

from .types import (
    AdjustmentPolicy,
    MarketMode,
    NonEmptyStr,
    NormalizationPolicy,
    OptionMode,
    OptionType,
    aware_utc,
)


class MarketToolCallContext(ContractModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    request_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    decision_time: datetime
    deterministic_seed: int = Field(ge=0)

    _decision = field_validator("decision_time")(aware_utc)


class GetSnapshotRequest(ContractModel):
    instrument_id: NonEmptyStr
    research_mode: MarketMode = MarketMode.OBSERVE
    max_staleness_seconds: float | None = Field(default=None, gt=0.0)


class GetHistoryRequest(ContractModel):
    instrument_id: NonEmptyStr
    start_date: date | None = None
    end_date: date | None = None
    research_mode: MarketMode = MarketMode.OBSERVE
    adjustment_policy: AdjustmentPolicy = AdjustmentPolicy.RAW
    max_records: int = Field(default=252, ge=1, le=5000)

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "GetHistoryRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class GetLiquidityRequest(ContractModel):
    instrument_id: NonEmptyStr
    lookback_days: int = Field(default=20, ge=1, le=756)
    research_mode: MarketMode = MarketMode.DIAGNOSTIC


class GetCorporateActionsRequest(ContractModel):
    instrument_id: NonEmptyStr
    start_date: date | None = None
    end_date: date | None = None
    research_mode: MarketMode = MarketMode.OBSERVE

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "GetCorporateActionsRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class CompareInstrumentsRequest(ContractModel):
    instrument_ids: tuple[NonEmptyStr, ...]
    start_date: date | None = None
    end_date: date | None = None
    normalization: NormalizationPolicy = NormalizationPolicy.BASE_100
    research_mode: MarketMode = MarketMode.STRUCTURAL
    max_records_per_instrument: int = Field(default=252, ge=2, le=5000)

    @model_validator(mode="after")
    def request_is_consistent(self) -> "CompareInstrumentsRequest":
        if len(self.instrument_ids) < 2 or len(self.instrument_ids) > 20:
            raise ValueError("instrument_ids must contain between 2 and 20 entries")
        if len(self.instrument_ids) != len(set(self.instrument_ids)):
            raise ValueError("instrument_ids must be unique")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class GetContractsRequest(ContractModel):
    underlying: NonEmptyStr
    expiration_from: date | None = None
    expiration_to: date | None = None
    option_type: OptionType | None = None
    research_mode: OptionMode = OptionMode.CONTRACT_LOOKUP
    include_expired: bool = False
    max_records: int = Field(default=500, ge=1, le=5000)

    @model_validator(mode="after")
    def expiration_range_is_ordered(self) -> "GetContractsRequest":
        if self.expiration_from and self.expiration_to:
            if self.expiration_from > self.expiration_to:
                raise ValueError("expiration_from must be <= expiration_to")
        return self


class GetChainSnapshotRequest(ContractModel):
    underlying: NonEmptyStr
    expiration_date: date | None = None
    option_type: OptionType | None = None
    research_mode: OptionMode = OptionMode.CHAIN_DIAGNOSTIC
    executable_only: bool = False
    max_records: int = Field(default=1000, ge=1, le=10000)


class GetQuoteHistoryRequest(ContractModel):
    contract_keys: tuple[NonEmptyStr, ...]
    start_date: date | None = None
    end_date: date | None = None
    research_mode: OptionMode = OptionMode.STRUCTURE_HISTORY
    max_records_per_contract: int = Field(default=252, ge=1, le=5000)

    @model_validator(mode="after")
    def request_is_consistent(self) -> "GetQuoteHistoryRequest":
        if not self.contract_keys or len(self.contract_keys) > 100:
            raise ValueError("contract_keys must contain between 1 and 100 entries")
        if len(self.contract_keys) != len(set(self.contract_keys)):
            raise ValueError("contract_keys must be unique")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class GetSurfaceDiagnosticsRequest(ContractModel):
    underlying: NonEmptyStr
    expiration_dates: tuple[date, ...] = ()
    option_type: OptionType | None = None
    research_mode: OptionMode = OptionMode.SURFACE_ANALYSIS
    minimum_strikes_per_expiry: int = Field(default=3, ge=3, le=100)
    executable_only: bool = True

    @model_validator(mode="after")
    def expirations_are_unique(self) -> "GetSurfaceDiagnosticsRequest":
        if len(self.expiration_dates) != len(set(self.expiration_dates)):
            raise ValueError("expiration_dates must be unique")
        return self
