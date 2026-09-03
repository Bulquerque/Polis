"""Benchmark and factor-regression contracts for P9.S4.M06."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from .base_models import ModulePanelBase, PointInTimeSeries
from .common import FiniteFloat, NonEmptyStr, SemVer, Sha256, StrictModel, UtcDateTime, content_sha256
from .return_models import ReturnSeriesPanel


class RegressionCovariance(StrEnum):
    NONROBUST = "NONROBUST"
    HC3 = "HC3"
    HAC = "HAC"


class FactorValue(StrictModel):
    factor_id: NonEmptyStr
    value: FiniteFloat


class FactorObservation(StrictModel):
    timestamp: UtcDateTime
    available_at: UtcDateTime
    values: tuple[FactorValue, ...]

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.available_at > self.timestamp:
            raise ValueError("factor observation must be available by timestamp")
        factor_ids = [value.factor_id for value in self.values]
        if len(factor_ids) != len(set(factor_ids)):
            raise ValueError("duplicate factor IDs in observation")
        return self


class BenchmarkAndFactorPanel(StrictModel):
    panel_id: NonEmptyStr
    panel_version: SemVer
    observations: tuple[FactorObservation, ...]
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_panel(self) -> Self:
        timestamps = [observation.timestamp for observation in self.observations]
        if timestamps != sorted(timestamps):
            raise ValueError("factor observations must be time ordered")
        if len(timestamps) != len(set(timestamps)):
            raise ValueError("factor timestamps must be unique")
        expected = content_sha256(
            self.model_dump(mode="python", exclude={"content_sha256"})
        )
        if expected != self.content_sha256:
            raise ValueError("factor panel hash mismatch")
        return self


class FactorModelSpec(StrictModel):
    factor_model_id: NonEmptyStr
    factor_model_version: SemVer
    factor_ids: tuple[NonEmptyStr, ...]
    include_intercept: bool = True
    description: NonEmptyStr

    @model_validator(mode="after")
    def validate_factors(self) -> Self:
        if not self.factor_ids:
            raise ValueError("factor model requires at least one factor")
        if len(set(self.factor_ids)) != len(self.factor_ids):
            raise ValueError("factor model factor IDs must be unique")
        return self


class FactorModelRegistry(StrictModel):
    registry_id: NonEmptyStr
    registry_version: SemVer
    models: tuple[FactorModelSpec, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        keys = [(model.factor_model_id, model.factor_model_version) for model in self.models]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate factor model registry entries")
        return self

    def get(self, model_id: str, version: str) -> FactorModelSpec:
        for model in self.models:
            if model.factor_model_id == model_id and model.factor_model_version == version:
                return model
        raise KeyError(f"unknown factor model {model_id}@{version}")


class RegressionPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    factor_model_ids: tuple[tuple[NonEmptyStr, SemVer], ...]
    covariance: RegressionCovariance = RegressionCovariance.HAC
    hac_max_lags: int = Field(default=5, ge=0)
    minimum_observations: int = Field(default=30, ge=3)
    condition_number_limit: FiniteFloat = Field(default=1_000_000.0, gt=1)
    rolling_window: int | None = Field(default=None, ge=3)


class FactorCoefficient(StrictModel):
    name: NonEmptyStr
    estimate: FiniteFloat
    standard_error: FiniteFloat | None = Field(default=None, ge=0)
    t_statistic: FiniteFloat | None = None
    p_value: FiniteFloat | None = Field(default=None, ge=0, le=1)


class FactorRegressionRecord(StrictModel):
    factor_model_id: NonEmptyStr
    factor_model_version: SemVer
    gross_net: NonEmptyStr
    status: NonEmptyStr
    observation_count: int = Field(ge=0)
    coefficients: tuple[FactorCoefficient, ...]
    r_squared: FiniteFloat | None
    residual_volatility_annualized: FiniteFloat | None = Field(default=None, ge=0)
    condition_number: FiniteFloat | None = Field(default=None, ge=0)
    covariance_method: NonEmptyStr
    limitations: tuple[NonEmptyStr, ...] = ()


class RollingFactorRecord(StrictModel):
    factor_model_id: NonEmptyStr
    factor_model_version: SemVer
    gross_net: NonEmptyStr
    end_timestamp: UtcDateTime
    observation_count: int = Field(ge=0)
    coefficients: tuple[FactorCoefficient, ...]
    r_squared: FiniteFloat | None
    status: NonEmptyStr


class FactorExposurePanel(ModulePanelBase):
    regressions: tuple[FactorRegressionRecord, ...]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("factor exposure panel hash mismatch")
        return self


class RollingFactorPanel(ModulePanelBase):
    records: tuple[RollingFactorRecord, ...]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("rolling factor panel hash mismatch")
        return self


class RegressionDiagnosticReport(ModulePanelBase):
    registry_id: NonEmptyStr
    registry_version: SemVer

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("regression diagnostics hash mismatch")
        return self


class FactorRegressionRequest(StrictModel):
    returns: ReturnSeriesPanel
    factors: BenchmarkAndFactorPanel
    risk_free: PointInTimeSeries
    registry: FactorModelRegistry
    policy: RegressionPolicy


class FactorRegressionResult(StrictModel):
    exposures: FactorExposurePanel
    rolling: RollingFactorPanel
    diagnostics: RegressionDiagnosticReport
