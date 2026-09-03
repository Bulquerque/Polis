"""Strong V2 contracts for feature, marginal distribution and path-risk artifacts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator, model_validator

from .core import FrozenModel
from .distributions import ForecastDistribution, QuantilePoint
from .v2_base import CalibrationStatus, CapabilityStatus, V2ArtifactIdentity, ValidityStatus


class MarketFeatureRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    decision_time: datetime
    available_at: datetime
    feature_view_id: str = Field(min_length=1)
    view_type: str = Field(min_length=1)
    feature_schema_version: str = Field(min_length=1)
    feature_values: dict[str, float | None] = Field(min_length=1)
    feature_metadata: dict[str, dict[str, Any]] = Field(default_factory=dict)
    feature_masks: dict[str, bool] = Field(default_factory=dict)
    quality_state: str = Field(min_length=1)
    horizon_group: str = Field(min_length=1)
    representation_type: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    lineage_id: str = Field(min_length=1)

    @field_validator("decision_time", "available_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("feature clocks must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_availability(self) -> "MarketFeatureRecord":
        if self.available_at > self.decision_time:
            raise ValueError("feature available_at cannot exceed decision_time")
        if set(self.feature_masks) - set(self.feature_values):
            raise ValueError("feature masks reference unknown feature values")
        return self


class MarketFeatureBundle(V2ArtifactIdentity):
    records: tuple[MarketFeatureRecord, ...] = Field(min_length=1)


class ReturnDistributionRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    decision_time: datetime
    horizon: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    distribution_version: str = Field(min_length=1)
    mean: float
    median: float
    mode: float | None = None
    mode_method: str = Field(default="LEGACY_UNSPECIFIED", min_length=1)
    quantiles: tuple[QuantilePoint, ...] = Field(min_length=3)
    probability_positive: float = Field(ge=0.0, le=1.0)
    probability_negative: float = Field(ge=0.0, le=1.0)
    tail_probabilities: dict[str, float] = Field(default_factory=dict)
    tail_probability_semantics: str = Field(default="LEGACY_UNSPECIFIED", min_length=1)
    distribution_family: str = Field(min_length=1)
    support: tuple[float | None, float | None]
    units: str = Field(min_length=1)
    model_member_ids: tuple[str, ...] = Field(min_length=1)
    calibration_status: CalibrationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    distribution: ForecastDistribution
    lineage_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_probabilities(self) -> "ReturnDistributionRecord":
        if abs(self.probability_positive + self.probability_negative - 1.0) > 1e-6:
            raise ValueError("positive and negative probabilities must sum to one")
        if any(not 0.0 <= value <= 1.0 for value in self.tail_probabilities.values()):
            raise ValueError("tail probabilities must be in [0, 1]")
        return self


class ReturnDistributionPanel(V2ArtifactIdentity):
    records: tuple[ReturnDistributionRecord, ...] = Field(min_length=1)


class VolatilityDistributionRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    decision_time: datetime
    forecast_horizon: str = Field(min_length=1)
    realized_volatility_distribution: ForecastDistribution | None = None
    conditional_volatility_distribution: ForecastDistribution | None = None
    implied_volatility_state: ForecastDistribution | None = None
    volatility_of_volatility: ForecastDistribution | None = None
    jump_variation: ForecastDistribution | None = None
    continuous_variation: ForecastDistribution | None = None
    units: str = "annualized_volatility"
    capability_status: CapabilityStatus
    model_member_ids: tuple[str, ...] = Field(min_length=1)
    calibration_status: CalibrationStatus
    lineage_id: str = Field(min_length=1)


    @model_validator(mode="after")
    def require_observed_volatility_component(self) -> "VolatilityDistributionRecord":
        if self.realized_volatility_distribution is None and self.conditional_volatility_distribution is None:
            raise ValueError("volatility record requires realized or conditional distribution")
        return self


class VolatilityDistributionPanel(V2ArtifactIdentity):
    records: tuple[VolatilityDistributionRecord, ...] = Field(min_length=1)


class PathRiskForecastRecord(FrozenModel):
    underlying: str = Field(min_length=1)
    decision_time: datetime
    horizon: str = Field(min_length=1)
    path_minimum_distribution: ForecastDistribution
    path_maximum_distribution: ForecastDistribution
    maximum_drawdown_distribution: ForecastDistribution
    jump_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    gap_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    liquidity_stress_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    intraperiod_volatility_distribution: ForecastDistribution
    liquidity_capability: CapabilityStatus
    validity_status: ValidityStatus
    lineage_id: str = Field(min_length=1)


class PathRiskForecastPanel(V2ArtifactIdentity):
    records: tuple[PathRiskForecastRecord, ...] = Field(min_length=1)
