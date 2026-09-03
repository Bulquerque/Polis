"""Risk-adjusted metric contracts for P9.S4.M05."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from .base_models import MetricApplicability, ModulePanelBase, PointInTimeSeries
from .common import FiniteFloat, NonEmptyStr, SemVer, StrictModel, content_sha256
from .distribution_models import DistributionEngineResult
from .drawdown_models import DrawdownMetricPanel
from .return_models import ReturnEngineResult


class RiskAdjustedMetricPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    mar_per_period: FiniteFloat = 0.0
    omega_threshold_per_period: FiniteFloat = 0.0
    probabilistic_sharpe_benchmark: FiniteFloat = 0.0
    psr_confidence_level: FiniteFloat = Field(default=0.95, gt=0.5, lt=1)
    autocorrelation_max_lag: int = Field(default=10, ge=0)
    minimum_observations: int = Field(default=20, ge=2)


class RiskAdjustedMetricPanel(ModulePanelBase):
    applicability: tuple[MetricApplicability, ...]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("risk-adjusted metric panel hash mismatch")
        return self


class SharpeDiagnosticPanel(ModulePanelBase):
    autocorrelation_adjustment_factor: FiniteFloat | None
    skewness: FiniteFloat | None
    pearson_kurtosis: FiniteFloat | None
    minimum_track_record_length: FiniteFloat | None

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("Sharpe diagnostic panel hash mismatch")
        return self


class RiskAdjustedRequest(StrictModel):
    returns: ReturnEngineResult
    distribution: DistributionEngineResult
    drawdown: DrawdownMetricPanel
    policy: RiskAdjustedMetricPolicy
    benchmark: PointInTimeSeries | None = None
    risk_free: PointInTimeSeries | None = None


class RiskAdjustedResult(StrictModel):
    metrics: RiskAdjustedMetricPanel
    sharpe_diagnostics: SharpeDiagnosticPanel
