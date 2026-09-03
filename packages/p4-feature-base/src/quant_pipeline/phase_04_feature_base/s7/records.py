from __future__ import annotations

import math
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class HorizonFeatureRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_time: AwareDatetime
    entity_id: str
    feature_id: str
    feature_value: float | None
    family_id: str
    perspective_id: str
    parameterization_id: str
    horizon_group: str
    available_at: AwareDatetime
    quality_state: str
    missingness_state: str
    lineage_id: str
    source_modalities: tuple[str, ...]
    implementation_tier: str
    is_primary_parameterization: bool
    compute_cost: float = Field(ge=0)

    @field_validator("feature_value")
    @classmethod
    def finite_value(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("feature_value must be finite or null")
        return value

    @model_validator(mode="after")
    def point_in_time(self) -> "HorizonFeatureRecord":
        if self.available_at > self.decision_time:
            raise ValueError("available_at is after decision_time")
        return self


TransformType = Literal[
    "identity", "signed_log1p", "standard_zscore", "robust_zscore",
    "winsorized_robust_zscore",
]


class TransformPolicyRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature_id: str
    horizon_group: str
    transform_type: TransformType
    window_type: Literal["expanding", "rolling"]
    lookback_timestamps: int | None = Field(default=None, ge=1)
    min_observations: int = Field(ge=2)
    refit_every_n_timestamps: int = Field(ge=1)
    lower_quantile: float = Field(ge=0, le=1)
    upper_quantile: float = Field(ge=0, le=1)
    epsilon: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_policy(self) -> "TransformPolicyRecord":
        if self.window_type == "rolling" and self.lookback_timestamps is None:
            raise ValueError("rolling policy requires lookback_timestamps")
        if self.lower_quantile >= self.upper_quantile:
            raise ValueError("lower_quantile must be below upper_quantile")
        return self


class ExposureRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_time: AwareDatetime
    entity_id: str
    available_at: AwareDatetime
    values: dict[str, float | None]
    lineage_id: str

    @model_validator(mode="after")
    def point_in_time(self) -> "ExposureRecord":
        if self.available_at > self.decision_time:
            raise ValueError("exposure available_at is after decision_time")
        for name, value in self.values.items():
            if value is not None and not math.isfinite(value):
                raise ValueError(f"exposure {name} must be finite or null")
        return self


class NormalizationPolicyRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    feature_id: str
    horizon_group: str
    normalization_type: Literal["none", "rank_percentile", "zscore", "robust_zscore"]
    neutralize_exposures: tuple[str, ...]
    ridge_alpha: float = Field(ge=0)
    min_entities: int = Field(ge=2)
    final_view: Literal["raw", "transformed", "normalized", "neutralized"]
    epsilon: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_final_view(self) -> "NormalizationPolicyRecord":
        if self.final_view == "neutralized" and not self.neutralize_exposures:
            raise ValueError("neutralized final_view requires exposures")
        return self


class StructuralSelectionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_coverage: float = Field(ge=0, le=1)
    max_missingness: float = Field(ge=0, le=1)
    min_variance: float = Field(ge=0)
    min_pair_overlap: int = Field(ge=3)
    duplicate_abs_pearson: float = Field(ge=0, le=1)
    duplicate_abs_spearman: float = Field(ge=0, le=1)
    nonlinear_dependence_threshold: float = Field(ge=0, le=1)
    max_pair_samples: int = Field(ge=10)
    mutual_info_neighbors: int = Field(ge=1)
    random_state: int
    min_selected_features: int = Field(ge=1)
    prefer_primary_parameterization: bool
