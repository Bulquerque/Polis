from __future__ import annotations

from typing import Annotated

from pydantic import Field, field_validator, model_validator

from .base import StrictModel
from ..domain.enums import (
    MetricSourcePreference,
    MissingHeadAction,
    MissingMetricAction,
    NormalizationMethod,
    SmallGroupAction,
    TransformationMethod,
)

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class MetricBindingPolicy(StrictModel):
    metric_id: str
    source_preference: MetricSourcePreference
    transformation: TransformationMethod
    normalization: NormalizationMethod
    metric_weight: NonNegativeFloat = Field(gt=0)
    clip_lower: FiniteFloat | None = None
    clip_upper: FiniteFloat | None = None
    absolute_lower: FiniteFloat | None = None
    absolute_upper: FiniteFloat | None = None
    robust_scale: NonNegativeFloat = Field(default=1.0, gt=0)
    min_group_size: int = Field(default=2, ge=1)
    small_group_action: SmallGroupAction = SmallGroupAction.ABSOLUTE_FALLBACK
    missing_metric_action: MissingMetricAction = MissingMetricAction.BLOCK_HEAD
    missing_metric_penalty: Probability = 0.0

    @model_validator(mode="after")
    def validate_bounds(self) -> "MetricBindingPolicy":
        if (self.clip_lower is None) != (self.clip_upper is None):
            raise ValueError("clip bounds must be both present or both absent")
        if self.clip_lower is not None and self.clip_upper is not None and self.clip_upper < self.clip_lower:
            raise ValueError("clip_upper must be >= clip_lower")
        needs_absolute = self.normalization == NormalizationMethod.ABSOLUTE_RANGE
        fallback_absolute = self.small_group_action == SmallGroupAction.ABSOLUTE_FALLBACK
        if needs_absolute or fallback_absolute:
            if self.absolute_lower is None or self.absolute_upper is None:
                raise ValueError("absolute bounds are required")
            if self.absolute_upper <= self.absolute_lower:
                raise ValueError("absolute_upper must be greater than absolute_lower")
        return self


class HeadPolicy(StrictModel):
    head_id: str
    head_weight: NonNegativeFloat = Field(gt=0)
    missing_head_action: MissingHeadAction
    missing_head_penalty: Probability = 0.0
    metric_bindings: tuple[MetricBindingPolicy, ...]

    @model_validator(mode="after")
    def validate_bindings(self) -> "HeadPolicy":
        if not self.metric_bindings:
            raise ValueError("head requires at least one metric binding")
        metric_ids = [row.metric_id for row in self.metric_bindings]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("metric bindings must be unique within a head")
        return self


class PenaltyRule(StrictModel):
    penalty_id: str
    head_id: str
    threshold: Probability
    coefficient: NonNegativeFloat


class ScoringPolicyRule(StrictModel):
    rule_id: str
    operational_modes: tuple[str, ...]
    objective_families: tuple[str, ...] = ("*",)
    horizons: tuple[str, ...] = ("*",)
    max_frontier_layer: int = Field(default=0, ge=0)
    include_incomparable: bool = False
    heads: tuple[HeadPolicy, ...]
    penalty_rules: tuple[PenaltyRule, ...] = ()
    confidence_head_id: str | None = None
    confidence_shrinkage_strength: Probability = 0.0

    @field_validator("operational_modes", "objective_families", "horizons")
    @classmethod
    def require_unique_selectors(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) != len(set(value)):
            raise ValueError("selectors must be non-empty and unique")
        return value

    @model_validator(mode="after")
    def validate_heads_and_penalties(self) -> "ScoringPolicyRule":
        head_ids = [row.head_id for row in self.heads]
        if not head_ids or len(head_ids) != len(set(head_ids)):
            raise ValueError("head IDs must be non-empty and unique")
        known = set(head_ids)
        if self.confidence_head_id is not None and self.confidence_head_id not in known:
            raise ValueError("confidence head must be defined in heads")
        unknown = {row.head_id for row in self.penalty_rules} - known
        if unknown:
            raise ValueError(f"penalty heads are not defined: {sorted(unknown)}")
        penalty_ids = [row.penalty_id for row in self.penalty_rules]
        if len(penalty_ids) != len(set(penalty_ids)):
            raise ValueError("penalty IDs must be unique")
        return self


class ScoringPolicyContextRecord(StrictModel):
    policy_id: str
    policy_version: str
    operational_mode: str
    rules: tuple[ScoringPolicyRule, ...]
    forbidden_field_names: tuple[str, ...]

    @model_validator(mode="after")
    def validate_rules(self) -> "ScoringPolicyContextRecord":
        rule_ids = [row.rule_id for row in self.rules]
        if not rule_ids or len(rule_ids) != len(set(rule_ids)):
            raise ValueError("scoring policy rules must be non-empty and unique")
        if len(self.forbidden_field_names) != len(set(self.forbidden_field_names)):
            raise ValueError("forbidden fields must be unique")
        return self
