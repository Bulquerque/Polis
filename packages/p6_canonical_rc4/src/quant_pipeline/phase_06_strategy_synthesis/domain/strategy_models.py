"""Canonical strategy identity, leg, trace, and snapshot models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, JsonValue, field_validator, model_validator

from ..foundation.artifacts import FrozenModel
from ..foundation.hashing import utc
from .enums import (
    CandidateStatus,
    ExerciseStyle,
    InstrumentType,
    LegRole,
    ObjectiveFamily,
    OptionType,
    OriginMode,
    QuoteQuality,
    SettlementType,
    Side,
    TemplateId,
)

class StrategyLeg(FrozenModel):
    leg_id: str
    instrument_id: str
    instrument_type: InstrumentType
    side: Side
    quantity: Decimal = Field(gt=0)
    option_type: OptionType | None = None
    strike: Decimal | None = Field(default=None, gt=0)
    expiration: datetime | None = None
    exercise_style: ExerciseStyle | None = None
    settlement_type: SettlementType | None = None
    multiplier: Decimal = Field(gt=0)
    currency: str
    exchange: str
    entry_price_reference: Decimal
    price_selection_method: str
    leg_role: LegRole
    quote_quality: QuoteQuality | None = None
    source_quote_id: str | None = None

    @field_validator("expiration")
    @classmethod
    def normalize_expiration(cls, value: datetime | None) -> datetime | None:
        return None if value is None else utc(value)

    @model_validator(mode="after")
    def validate_option_fields(self) -> "StrategyLeg":
        if self.instrument_type is InstrumentType.OPTION:
            required = (
                self.option_type,
                self.strike,
                self.expiration,
                self.exercise_style,
                self.settlement_type,
            )
            if any(value is None for value in required):
                raise ValueError("option leg requires complete contract fields")
        return self


class CandidateGenerationTrace(FrozenModel):
    candidate_id: str
    origin: OriginMode
    origin_template_id: TemplateId
    parent_candidate_ids: tuple[str, ...] = ()
    operators: tuple[str, ...] = ()
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    solver_id: str | None = None
    solver_status: str | None = None
    generation_stage: str
    rejection_history: tuple[str, ...] = ()
    dedup_cluster: str | None = None


class StrategyCandidate(FrozenModel):
    candidate_id: str
    candidate_version: str
    underlying_id: str
    decision_time: datetime
    horizon_days: int = Field(gt=0)
    objective_family: ObjectiveFamily
    origin_mode: OriginMode
    origin_template_id: TemplateId
    parent_candidate_ids: tuple[str, ...] = ()
    mutation_trace: tuple[str, ...] = ()
    legs: tuple[StrategyLeg, ...] = Field(min_length=1)
    strategy_scale: Decimal = Field(gt=0)
    generation_run_id: str
    lineage_id: str
    status: CandidateStatus = CandidateStatus.GENERATED

    @field_validator("decision_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)


class StaticArbitrageViolation(FrozenModel):
    violation_id: str
    violation_type: str
    severity: str
    contract_ids: tuple[str, ...]
    details: dict[str, JsonValue]


class StrategyMarketSnapshot(FrozenModel):
    snapshot_id: str
    decision_time: datetime
    belief_artifact_id: str
    contract_artifact_id: str
    quote_artifact_id: str
    underlying_artifact_id: str
    rejection_report_artifact_id: str
    p5_compatibility_report_artifact_id: str | None = None
    p5_manifest_id: str | None = None
    p5_manifest_sha256: str | None = None
    p5_source_artifact_ids: tuple[str, ...] = ()
    p5_source_hashes: tuple[str, ...] = ()
    snapshot_sha256: str
    contract_count: int = Field(ge=0)
    quote_count: int = Field(ge=0)
    underlying_count: int = Field(ge=0)

    @field_validator("decision_time")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)


