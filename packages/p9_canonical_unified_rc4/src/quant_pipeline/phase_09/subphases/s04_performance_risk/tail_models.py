"""Tail-risk contracts for P9.S4.M03."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from .base_models import MinimumSamplePolicy, ModulePanelBase
from .common import FiniteFloat, NonEmptyStr, SemVer, StrictModel, UtcDateTime, content_sha256
from .return_models import ReturnSeriesPanel


class QuantileMethod(StrEnum):
    LINEAR = "linear"
    INVERTED_CDF = "inverted_cdf"
    MEDIAN_UNBIASED = "median_unbiased"


class ParametricTailModel(StrEnum):
    NONE = "NONE"
    NORMAL = "NORMAL"


class TailRiskPolicy(StrictModel):
    policy_id: NonEmptyStr
    policy_version: SemVer
    confidence_levels: tuple[FiniteFloat, ...] = (0.95, 0.99)
    quantile_method: QuantileMethod = QuantileMethod.LINEAR
    parametric_model: ParametricTailModel = ParametricTailModel.NORMAL
    minimum_samples: MinimumSamplePolicy

    @model_validator(mode="after")
    def validate_levels(self) -> Self:
        if any(level <= 0.5 or level >= 1.0 for level in self.confidence_levels):
            raise ValueError("tail confidence levels must be in (0.5, 1)")
        if len(set(self.confidence_levels)) != len(self.confidence_levels):
            raise ValueError("tail confidence levels must be unique")
        return self


class ScenarioPnlRecord(StrictModel):
    scenario_id: NonEmptyStr
    scenario_version: SemVer
    timestamp: UtcDateTime
    pnl_fraction: FiniteFloat
    evidence_class: NonEmptyStr


class ScenarioPnlPanel(StrictModel):
    panel_id: NonEmptyStr
    records: tuple[ScenarioPnlRecord, ...]


class TailEstimate(StrictModel):
    gross_net: NonEmptyStr
    method: NonEmptyStr
    confidence_level: FiniteFloat = Field(gt=0.5, lt=1)
    value_at_risk: FiniteFloat | None
    expected_shortfall: FiniteFloat | None
    breach_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    status: NonEmptyStr
    limitations: tuple[NonEmptyStr, ...] = ()


class TailRiskMetricPanel(ModulePanelBase):
    estimates: tuple[TailEstimate, ...]
    scenario_losses: tuple[ScenarioPnlRecord, ...] = ()

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("tail risk panel hash mismatch")
        return self


class VaRBreachRecord(StrictModel):
    timestamp: UtcDateTime
    gross_net: NonEmptyStr
    confidence_level: FiniteFloat
    method: NonEmptyStr
    loss: FiniteFloat
    value_at_risk: FiniteFloat


class VaRBreachPanel(ModulePanelBase):
    breaches: tuple[VaRBreachRecord, ...]

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("breach panel hash mismatch")
        return self


class TailMethodDiagnostics(ModulePanelBase):
    quantile_method: NonEmptyStr
    parametric_model: NonEmptyStr

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if content_sha256(self.hash_preimage()) != self.content_sha256:
            raise ValueError("tail diagnostics hash mismatch")
        return self


class TailRiskRequest(StrictModel):
    returns: ReturnSeriesPanel
    policy: TailRiskPolicy
    scenarios: ScenarioPnlPanel | None = None


class TailRiskResult(StrictModel):
    metrics: TailRiskMetricPanel
    breaches: VaRBreachPanel
    diagnostics: TailMethodDiagnostics
