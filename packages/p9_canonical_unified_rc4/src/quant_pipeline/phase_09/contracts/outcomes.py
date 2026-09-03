from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from .base import (
    EvidenceClass,
    FiniteDecimal,
    NonEmptyStr,
    ReasonCode,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)


class MarkSource(StrEnum):
    BID_ASK = "BID_ASK"
    LAST = "LAST"
    OFFICIAL_SETTLEMENT = "OFFICIAL_SETTLEMENT"
    MODEL = "MODEL"


class ExecutedOutcomeRecord(StrictModel):
    subject_id: NonEmptyStr
    realized_pnl: FiniteDecimal
    realized_return: FiniteDecimal | None = None
    closed_at: UtcDateTime
    settlement_at: UtcDateTime | None = None
    source_artifact_id: NonEmptyStr
    source_sha256: Sha256Hex


class MarketMark(StrictModel):
    mark_id: NonEmptyStr
    subject_id: NonEmptyStr
    instrument_id: NonEmptyStr
    contract_key: NonEmptyStr
    observed_at: UtcDateTime
    available_at: UtcDateTime
    source: MarkSource
    bid: FiniteDecimal | None = None
    ask: FiniteDecimal | None = None
    last: FiniteDecimal | None = None
    settlement: FiniteDecimal | None = None
    model_price: FiniteDecimal | None = None
    source_sha256: Sha256Hex
    corporate_action_adjusted: bool = False

    @model_validator(mode="after")
    def validate_mark(self) -> "MarketMark":
        if self.available_at < self.observed_at:
            raise ValueError("market mark available_at cannot precede observed_at")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        required_field = {
            MarkSource.BID_ASK: self.bid is not None and self.ask is not None,
            MarkSource.LAST: self.last is not None,
            MarkSource.OFFICIAL_SETTLEMENT: self.settlement is not None,
            MarkSource.MODEL: self.model_price is not None,
        }[self.source]
        if not required_field:
            raise ValueError(f"mark source {self.source} lacks required price field")
        return self


class ExecutedOutcomePanel(StrictModel):
    records: tuple[ExecutedOutcomeRecord, ...] = ()


class MarketMarkPanel(StrictModel):
    records: tuple[MarketMark, ...] = ()


class MarkingPolicy(StrictModel):
    policy_id: NonEmptyStr
    max_staleness_seconds: int = Field(ge=0)
    allow_model_marks: bool = False
    prefer_official_settlement: bool = True
    midpoint_for_bid_ask: bool = True
    require_contract_match: bool = True


class RealizedOutcomeRecord(StrictModel):
    subject_id: NonEmptyStr
    evidence_class: EvidenceClass
    outcome_value: FiniteDecimal | None
    outcome_return: FiniteDecimal | None
    mark_price: FiniteDecimal | None
    observed_at: UtcDateTime | None
    available_at: UtcDateTime | None
    source_id: NonEmptyStr | None
    source_sha256: Sha256Hex | None
    quality_flags: tuple[NonEmptyStr, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    @model_validator(mode="after")
    def validate_evidence(self) -> "RealizedOutcomeRecord":
        unavailable = self.evidence_class in {EvidenceClass.CENSORED, EvidenceClass.UNAVAILABLE}
        if unavailable and self.outcome_value is not None:
            raise ValueError("censored/unavailable outcomes cannot contain a value")
        if not unavailable and self.outcome_value is None:
            raise ValueError("observable outcome classes require outcome_value")
        if self.evidence_class is EvidenceClass.MODEL_BASED_COUNTERFACTUAL:
            if "MODEL_BASED" not in self.quality_flags:
                raise ValueError("model-based outcome requires MODEL_BASED quality flag")
        return self


class RealizedOutcomePanel(StrictModel):
    records: tuple[RealizedOutcomeRecord, ...]

    @model_validator(mode="after")
    def validate_unique(self) -> "RealizedOutcomePanel":
        ids = [record.subject_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("outcome panel subject IDs must be unique")
        return self


class CounterfactualMarkPanel(StrictModel):
    records: tuple[RealizedOutcomeRecord, ...]


class MarkQualityCount(StrictModel):
    evidence_class: EvidenceClass
    count: int = Field(ge=0)


class MarkQualityReport(StrictModel):
    counts: tuple[MarkQualityCount, ...]
    stale_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    model_based_count: int = Field(ge=0)


class OutcomeAssemblyReceipt(StrictModel):
    policy_id: NonEmptyStr
    subject_count: int = Field(ge=0)
    factual_count: int = Field(ge=0)
    counterfactual_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    output_sha256: Sha256Hex
