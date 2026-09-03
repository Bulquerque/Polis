"""Forecast, validation and publication records."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .core import FrozenModel
from .distributions import ForecastDistribution, point_value


_HORIZON = re.compile(r"^[1-9]\d*[HDWM]$")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


class ForecastMemberRecord(FrozenModel):
    record_id: str = Field(min_length=1)
    as_of_time: datetime
    prediction_timestamp: datetime
    underlying: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    resolver_id: str = Field(min_length=1)
    resolver_family: str = Field(min_length=1)
    model_artifact_id: str = Field(min_length=1)
    feature_view_id: str = Field(min_length=1)
    training_cutoff: datetime
    lineage_id: str = Field(min_length=1)
    distribution: ForecastDistribution
    role: Literal["CORE", "CHALLENGER", "RESERVE", "SHADOW"] = "CHALLENGER"
    status: Literal["VALID", "DEGRADED"] = "VALID"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("horizon")
    @classmethod
    def valid_horizon(cls, value: str) -> str:
        normalized = value.upper()
        if _HORIZON.fullmatch(normalized) is None:
            raise ValueError("horizon must use a positive H/D/W/M duration")
        return normalized

    @field_validator("as_of_time", "prediction_timestamp", "training_cutoff")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_pit(self) -> "ForecastMemberRecord":
        if self.training_cutoff > self.as_of_time:
            raise ValueError("training_cutoff cannot exceed as_of_time")
        if self.as_of_time >= self.prediction_timestamp:
            raise ValueError("prediction_timestamp must follow as_of_time")
        return self

    @property
    def point_forecast(self) -> float:
        return point_value(self.distribution)


class ForecastMemberPanel(FrozenModel):
    records: tuple[ForecastMemberRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_records(self) -> "ForecastMemberPanel":
        identifiers = tuple(item.record_id for item in self.records)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("forecast record_id values must be unique")
        keys = tuple(
            (
                item.resolver_id,
                item.underlying,
                item.target_id,
                item.horizon,
                item.unit,
                item.as_of_time,
                item.prediction_timestamp,
            )
            for item in self.records
        )
        if len(keys) != len(set(keys)):
            raise ValueError("forecast economic keys must be unique per resolver")
        return self


class OOFValidationObservation(FrozenModel):
    observation_id: str = Field(min_length=1)
    resolver_id: str = Field(min_length=1)
    resolver_family: str = Field(min_length=1)
    underlying: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    unit: str = Field(default="decimal_return", min_length=1)
    prediction_timestamp: datetime
    prediction: float
    realized: float
    q05: float | None = None
    q95: float | None = None
    partition_id: Literal["VALIDATION", "CALIBRATION"]
    fold_id: str = Field(default="fold-000", min_length=1)
    regime_label: str | None = None
    lineage_id: str = Field(min_length=1)

    @field_validator("horizon")
    @classmethod
    def valid_horizon(cls, value: str) -> str:
        normalized = value.upper()
        if _HORIZON.fullmatch(normalized) is None:
            raise ValueError("horizon must use a positive H/D/W/M duration")
        return normalized

    @field_validator("prediction_timestamp")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_interval(self) -> "OOFValidationObservation":
        if (self.q05 is None) != (self.q95 is None):
            raise ValueError("q05 and q95 must be both present or absent")
        if self.q05 is not None and self.q05 > self.q95:
            raise ValueError("q05 cannot exceed q95")
        return self


class OOFValidationObservationPanel(FrozenModel):
    records: tuple[OOFValidationObservation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_observations(self) -> "OOFValidationObservationPanel":
        identifiers = tuple(item.observation_id for item in self.records)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("OOF observation_id values must be unique")
        keys = tuple((
            item.resolver_id, item.underlying, item.target_id, item.horizon, item.unit,
            item.prediction_timestamp, item.partition_id, item.fold_id,
        ) for item in self.records)
        if len(keys) != len(set(keys)):
            raise ValueError("OOF economic observation keys must be unique")
        return self


class EnsembleForecastRecord(FrozenModel):
    record_id: str = Field(min_length=1)
    as_of_time: datetime
    prediction_timestamp: datetime
    underlying: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    distribution: ForecastDistribution
    member_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
    weights: tuple[float, ...] = Field(min_length=1, max_length=3)
    epistemic_uncertainty: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool = False
    lineage_id: str = Field(min_length=1)

    @field_validator("horizon")
    @classmethod
    def valid_horizon(cls, value: str) -> str:
        normalized = value.upper()
        if _HORIZON.fullmatch(normalized) is None:
            raise ValueError("horizon must use a positive H/D/W/M duration")
        return normalized

    @field_validator("as_of_time", "prediction_timestamp")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_weights(self) -> "EnsembleForecastRecord":
        if self.as_of_time >= self.prediction_timestamp:
            raise ValueError("prediction_timestamp must follow as_of_time")
        if len(self.member_ids) != len(self.weights):
            raise ValueError("member_ids and weights must align")
        if len(self.member_ids) != len(set(self.member_ids)):
            raise ValueError("ensemble member_ids must be unique")
        if any(weight < 0.0 for weight in self.weights):
            raise ValueError("ensemble weights must be nonnegative")
        if abs(sum(self.weights) - 1.0) > 1e-8:
            raise ValueError("ensemble weights must sum to one")
        return self


class EnsembleForecastPanel(FrozenModel):
    records: tuple[EnsembleForecastRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_records(self) -> "EnsembleForecastPanel":
        identifiers = tuple(item.record_id for item in self.records)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("ensemble record_id values must be unique")
        keys = tuple((
            item.as_of_time, item.prediction_timestamp, item.underlying,
            item.target_id, item.horizon, item.unit,
        ) for item in self.records)
        if len(keys) != len(set(keys)):
            raise ValueError("ensemble economic forecast keys must be unique")
        return self


class UnderlyingForecastRecord(FrozenModel):
    as_of_time: datetime
    prediction_timestamp: datetime
    underlying: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    point_forecast: float
    q05: float
    q50: float
    q95: float
    confidence: float = Field(ge=0.0, le=1.0)
    abstained: bool
    lineage_id: str = Field(min_length=1)

    @field_validator("horizon")
    @classmethod
    def valid_horizon(cls, value: str) -> str:
        normalized = value.upper()
        if _HORIZON.fullmatch(normalized) is None:
            raise ValueError("horizon must use a positive H/D/W/M duration")
        return normalized

    @field_validator("as_of_time", "prediction_timestamp")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_quantiles(self) -> "UnderlyingForecastRecord":
        if self.as_of_time >= self.prediction_timestamp:
            raise ValueError("prediction_timestamp must follow as_of_time")
        if not self.q05 <= self.q50 <= self.q95:
            raise ValueError("published quantiles must be monotonic")
        return self


class UnderlyingForecastPanel(FrozenModel):
    records: tuple[UnderlyingForecastRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_records(self) -> "UnderlyingForecastPanel":
        keys = tuple((
            item.as_of_time, item.prediction_timestamp, item.underlying,
            item.target_id, item.horizon, item.unit,
        ) for item in self.records)
        if len(keys) != len(set(keys)):
            raise ValueError("published economic forecast keys must be unique")
        return self
