"""Temporary P7 V1 projection models kept outside the canonical domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import field_validator

from ..foundation.artifacts import FrozenModel
from ..foundation.hashing import utc

class LegacyCandidateFeatureRecord(FrozenModel):
    date: str
    as_of_date: str
    available_at: datetime
    candidate_id: str
    underlying: str
    instrument_type: str = "strategy"
    action_type: str
    capital_reference: Decimal
    reference_price_t: Decimal
    source_id: str
    lineage_id: str
    pipeline_version: str
    expected_return_d: Decimal
    expected_return_w: Decimal
    expected_return_m: Decimal
    volatility_forecast: Decimal
    risk_score: Decimal
    tail_risk_score: Decimal
    forecast_confidence: Decimal
    regime_context: str
    data_quality_score: Decimal | None = None
    ood_score: Decimal | None = None

    @field_validator("available_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)


class LegacyCandidateUniverseRecord(FrozenModel):
    candidate_id: str
    underlying: str
    action_type: str
    leg_count: int


class LegacyOptionFeatureRecord(FrozenModel):
    candidate_id: str
    option_leg_count: int
    delta: Decimal | None
    gamma: Decimal | None
    vega: Decimal | None
    theta: Decimal | None


class LegacyQualityRecord(FrozenModel):
    candidate_id: str
    contract_exists: bool
    quality_status: str
    reason_codes: tuple[str, ...] = ()


class LegacyGenerationLogRecord(FrozenModel):
    candidate_id: str
    origin_template: str
    generation_run_id: str
    qualification_status: str


class LegacyHandoffManifest(FrozenModel):
    handoff_id: str
    candidate_id: str
    created_at: datetime
    target_phase: str
    candidate_count: int
    artifact_ids: tuple[str, ...]
    lineage_id: str
    pipeline_version: str

    @field_validator("created_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return utc(value)
