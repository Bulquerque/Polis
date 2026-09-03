"""Distribution and serial-dependence contracts for P9.S4.M02."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from .base_models import MinimumSamplePolicy, ModulePanelBase
from .common import FiniteFloat, NonEmptyStr, SemVer, StrictModel, content_sha256
from .return_models import ReturnSeriesPanel


class DistributionPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    minimum_samples: MinimumSamplePolicy
    downside_threshold_per_period: FiniteFloat = 0.0
    autocorrelation_lags: tuple[int, ...] = (1, 5, 21)
    ljung_box_max_lag: int = Field(default=10, ge=1)
    rolling_windows: tuple[int, ...] = (20, 60, 252)

    @model_validator(mode="after")
    def validate_lags(self) -> Self:
        if any(lag <= 0 for lag in self.autocorrelation_lags):
            raise ValueError("autocorrelation lags must be positive")
        if len(set(self.autocorrelation_lags)) != len(self.autocorrelation_lags):
            raise ValueError("autocorrelation lags must be unique")
        if any(window < 2 for window in self.rolling_windows):
            raise ValueError("rolling windows must be at least two")
        return self


class SerialCorrelationRecord(StrictModel):
    lag: int = Field(ge=1)
    gross_autocorrelation: FiniteFloat | None
    net_autocorrelation: FiniteFloat | None


class RollingDistributionRecord(StrictModel):
    window: int = Field(ge=2)
    ending_index: int = Field(ge=0)
    net_volatility_annualized: FiniteFloat | None
    gross_volatility_annualized: FiniteFloat | None
    net_skewness: FiniteFloat | None
    net_excess_kurtosis: FiniteFloat | None


class VolatilityMetricPanel(ModulePanelBase):
    periods_per_year: FiniteFloat
    downside_threshold_per_period: FiniteFloat

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("volatility panel hash mismatch")
        return self


class DistributionDiagnosticPanel(ModulePanelBase):
    serial_correlations: tuple[SerialCorrelationRecord, ...]
    rolling: tuple[RollingDistributionRecord, ...]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("distribution panel hash mismatch")
        return self


class SerialDependenceReport(ModulePanelBase):
    ljung_box_lag: int | None = Field(default=None, ge=1)
    gross_ljung_box_statistic: FiniteFloat | None = None
    gross_ljung_box_pvalue: FiniteFloat | None = Field(default=None, ge=0, le=1)
    net_ljung_box_statistic: FiniteFloat | None = None
    net_ljung_box_pvalue: FiniteFloat | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("serial dependence report hash mismatch")
        return self


class DistributionEngineRequest(StrictModel):
    returns: ReturnSeriesPanel
    policy: DistributionPolicy


class DistributionEngineResult(StrictModel):
    volatility: VolatilityMetricPanel
    diagnostics: DistributionDiagnosticPanel
    serial_dependence: SerialDependenceReport
