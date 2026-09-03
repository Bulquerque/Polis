from __future__ import annotations

from datetime import datetime
from math import isfinite

from pydantic import Field, field_validator, model_validator

from .enums import MetricFamily, ReasonCode, ShiftState
from .models_common import RuntimeContext, StrictModel


class MetricObservation(StrictModel):
    metric_name: str = Field(min_length=1)
    family: MetricFamily
    value: float
    baseline_mean: float
    baseline_std: float = Field(gt=0.0)
    observed_at: datetime

    @field_validator("value", "baseline_mean", "baseline_std")
    @classmethod
    def finite_values(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("metric values must be finite")
        return value

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value


class MetricMonitorState(StrictModel):
    metric_name: str = Field(min_length=1)
    count: int = Field(ge=0)
    ewma_z: float = 0.0
    cusum_positive: float = Field(default=0.0, ge=0.0)
    cusum_negative: float = Field(default=0.0, ge=0.0)
    last_observed_at: datetime | None = None


class ShiftMonitorPolicy(StrictModel):
    alpha: float = Field(gt=0.0, le=1.0)
    drift_allowance: float = Field(ge=0.0)
    mild_threshold: float = Field(gt=0.0)
    material_threshold: float = Field(gt=0.0)
    critical_threshold: float = Field(gt=0.0)
    minimum_observations: int = Field(ge=1)
    maximum_observation_age_seconds: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered_thresholds(self) -> "ShiftMonitorPolicy":
        if not self.mild_threshold < self.material_threshold < self.critical_threshold:
            raise ValueError("thresholds must be strictly increasing")
        return self


class ShiftMonitorRequest(StrictModel):
    context: RuntimeContext
    observations: tuple[MetricObservation, ...] = Field(min_length=1)
    prior_states: tuple[MetricMonitorState, ...] = ()
    policy: ShiftMonitorPolicy


class MetricShiftResult(StrictModel):
    metric_name: str
    family: MetricFamily
    z_score: float
    ewma_z: float
    cusum_score: float
    state: ShiftState
    reason_codes: tuple[ReasonCode, ...] = ()


class ShiftMonitorResult(StrictModel):
    overall_state: ShiftState
    metric_results: tuple[MetricShiftResult, ...]
    next_states: tuple[MetricMonitorState, ...]
    generated_at: datetime
