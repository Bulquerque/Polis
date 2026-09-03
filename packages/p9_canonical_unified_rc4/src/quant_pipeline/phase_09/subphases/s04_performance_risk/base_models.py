"""Cross-module S4 contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from .common import (
    DiagnosticRecord,
    FiniteFloat,
    FrequencyMode,
    GrossNet,
    MetricRecord,
    NonEmptyStr,
    SemVer,
    Sha256,
    StrictModel,
    UtcDateTime,
    content_sha256,
)


class SeriesPoint(StrictModel):
    timestamp: UtcDateTime
    value: FiniteFloat
    available_at: UtcDateTime

    @model_validator(mode="after")
    def validate_point(self) -> Self:
        if self.available_at > self.timestamp:
            raise ValueError("series value must be available by its evaluation timestamp")
        return self


class PointInTimeSeries(StrictModel):
    series_id: NonEmptyStr
    series_version: SemVer
    points: tuple[SeriesPoint, ...]
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_series(self) -> Self:
        timestamps = [point.timestamp for point in self.points]
        if timestamps != sorted(timestamps):
            raise ValueError("series points must be time ordered")
        if len(timestamps) != len(set(timestamps)):
            raise ValueError("series timestamps must be unique")
        expected = content_sha256(
            self.model_dump(mode="python", exclude={"content_sha256"})
        )
        if expected != self.content_sha256:
            raise ValueError("series content_sha256 mismatch")
        return self


class AnnualizationPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    mode: FrequencyMode
    periods_per_year: FiniteFloat | None = Field(default=None, gt=0)
    regularity_tolerance_fraction: FiniteFloat = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        if self.mode is FrequencyMode.EXPLICIT and self.periods_per_year is None:
            raise ValueError("EXPLICIT annualization requires periods_per_year")
        return self


class MinimumSamplePolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    minimum_return_observations: int = Field(default=20, ge=2)
    minimum_tail_observations: int = Field(default=50, ge=5)
    minimum_regression_observations: int = Field(default=30, ge=3)
    minimum_rolling_observations: int = Field(default=20, ge=2)


class QualifiedBacktestIdentity(StrictModel):
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    trial_id: NonEmptyStr
    fold_id: NonEmptyStr
    configuration_id: NonEmptyStr
    handoff_id: NonEmptyStr
    handoff_sha256: Sha256


class ModulePanelBase(StrictModel):
    panel_id: NonEmptyStr
    panel_version: SemVer
    identity: QualifiedBacktestIdentity
    metrics: tuple[MetricRecord, ...] = ()
    diagnostics: tuple[DiagnosticRecord, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    content_sha256: Sha256

    def hash_preimage(self) -> dict[str, object]:
        return self.model_dump(mode="python", exclude={"content_sha256"})


class ObservationAlignment(StrEnum):
    EXACT_TIMESTAMP = "EXACT_TIMESTAMP"
    PREVIOUS_AVAILABLE = "PREVIOUS_AVAILABLE"


class AlignmentPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    mode: ObservationAlignment = ObservationAlignment.EXACT_TIMESTAMP
    maximum_staleness_seconds: int = Field(default=0, ge=0)


class MetricApplicability(StrictModel):
    metric_id: NonEmptyStr
    status: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...] = ()
    observation_count: int = Field(ge=0)


def timestamps_are_strictly_ordered(values: tuple[datetime, ...]) -> bool:
    return all(left < right for left, right in zip(values, values[1:]))
