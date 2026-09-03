"""Runtime and policy models."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from .base import FrozenModel, _aware


class RuntimeConfig(FrozenModel):
    trace_id: str
    run_id: str
    run_timestamp: datetime

    _timestamp_aware = field_validator("run_timestamp")(_aware)


class SimilarityComponent(FrozenModel):
    name: str
    weight: float = Field(gt=0)


class SimilarityPolicy(FrozenModel):
    policy_id: str
    stages: tuple[SimilarityComponent, ...]
    minimum_weight_coverage: float = Field(ge=0, le=1)
    top_k_neighbors: int = Field(ge=1)
    minimum_edge_similarity: float = Field(ge=0, le=1)
    max_group_size: int = Field(ge=2)

    @model_validator(mode="after")
    def stages_unique(self) -> "SimilarityPolicy":
        names = [item.name for item in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("similarity stage names must be unique")
        required = {"payoff_shape", "scenario_payoff", "greek_vector", "leg_jaccard", "origin_template", "expiration_overlap"}
        if set(names) != required:
            raise ValueError("similarity stage registry is incomplete")
        return self


class DiversityPolicy(FrozenModel):
    policy_id: str
    cluster_threshold: float = Field(ge=0, le=1)
    density_top_k: int = Field(ge=1)
    penalty_lambda: float = Field(ge=0)
    max_penalty_fraction: float = Field(ge=0, le=1)
    score_scale: float = Field(gt=0)


class SafetyPolicy(FrozenModel):
    policy_id: str
    max_execution_context_age_seconds: int = Field(ge=0)
    accepted_defined_risk_statuses: tuple[str, ...]
    accepted_model_promotion_statuses: tuple[str, ...]
    accepted_model_compatibility_statuses: tuple[str, ...]
    severe_ood_values: tuple[str, ...]


class AbstentionPolicy(FrozenModel):
    policy_id: str
    minimum_confidence: float = Field(ge=0, le=1)
    maximum_score_interval_width: float = Field(ge=0)
    maximum_model_disagreement: float = Field(ge=0)
    accepted_calibration_statuses: tuple[str, ...]
    moderate_ood_values: tuple[str, ...]
    minimum_group_rankable_count: int = Field(ge=1)
    minimum_group_rankable_fraction: float = Field(ge=0, le=1)


class S7Config(FrozenModel):
    runtime: RuntimeConfig
    similarity: SimilarityPolicy
    diversity: DiversityPolicy
    safety: SafetyPolicy
    abstention: AbstentionPolicy
    forbidden_fields: tuple[str, ...]
