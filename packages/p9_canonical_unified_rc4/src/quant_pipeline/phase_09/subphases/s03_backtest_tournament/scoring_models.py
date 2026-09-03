"""Contracts for competition score replication and aggregation."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from .common import FiniteDecimal, NonEmptyStr, SemVer, Sha256, StrictModel


class MissingComponentPolicy(StrEnum):
    ERROR = "ERROR"
    OMIT_AND_RENORMALIZE = "OMIT_AND_RENORMALIZE"


class ComponentTransform(StrEnum):
    IDENTITY = "IDENTITY"
    NEGATE = "NEGATE"
    CLIP = "CLIP"


class MetricComponentPolicy(StrictModel):
    component_id: NonEmptyStr
    weight: FiniteDecimal
    transform: ComponentTransform = ComponentTransform.IDENTITY
    clip_lower: FiniteDecimal | None = None
    clip_upper: FiniteDecimal | None = None

    @model_validator(mode="after")
    def validate_clip(self) -> Self:
        if self.transform is ComponentTransform.CLIP:
            if self.clip_lower is None or self.clip_upper is None:
                raise ValueError("CLIP transform requires lower and upper bounds")
            if self.clip_lower > self.clip_upper:
                raise ValueError("clip_lower cannot exceed clip_upper")
        elif self.clip_lower is not None or self.clip_upper is not None:
            raise ValueError("clip bounds are only valid for CLIP transform")
        return self


class CompetitionMetricPolicy(StrictModel):
    metric_id: NonEmptyStr
    metric_version: SemVer
    components: tuple[MetricComponentPolicy, ...]
    missing_policy: MissingComponentPolicy = MissingComponentPolicy.ERROR
    rounding_decimals: int = Field(default=8, ge=0, le=18)

    @model_validator(mode="after")
    def validate_components(self) -> Self:
        ids = [component.component_id for component in self.components]
        if not ids:
            raise ValueError("metric requires at least one component")
        if len(ids) != len(set(ids)):
            raise ValueError("component IDs must be unique")
        if all(component.weight == 0 for component in self.components):
            raise ValueError("at least one component weight must be non-zero")
        return self


class MetricInputRecord(StrictModel):
    trial_id: NonEmptyStr
    fold_id: NonEmptyStr
    configuration_id: NonEmptyStr
    qualification_sha256: Sha256
    components: tuple[tuple[NonEmptyStr, FiniteDecimal], ...]
    observation_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_unique_components(self) -> Self:
        ids = [item[0] for item in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("input component IDs must be unique")
        return self


class ScoreComponentRecord(StrictModel):
    component_id: NonEmptyStr
    raw_value: FiniteDecimal
    transformed_value: FiniteDecimal
    effective_weight: FiniteDecimal
    contribution: FiniteDecimal


class CompetitionScoreRecord(StrictModel):
    metric_id: NonEmptyStr
    metric_version: SemVer
    trial_id: NonEmptyStr
    fold_id: NonEmptyStr
    configuration_id: NonEmptyStr
    score: FiniteDecimal
    components: tuple[ScoreComponentRecord, ...]
    observation_count: int = Field(ge=0)
    policy_sha256: Sha256
    content_sha256: Sha256


class GoldenMetricExample(StrictModel):
    example_id: NonEmptyStr
    inputs: tuple[tuple[NonEmptyStr, FiniteDecimal], ...]
    expected_score: FiniteDecimal


class MetricParityCheck(StrictModel):
    example_id: NonEmptyStr
    passed: bool
    observed: FiniteDecimal
    expected: FiniteDecimal


class MetricParityReport(StrictModel):
    metric_id: NonEmptyStr
    metric_version: SemVer
    checks: tuple[MetricParityCheck, ...]
    passed: bool
    content_sha256: Sha256


class FoldWeightPolicy(StrEnum):
    EQUAL_FOLD = "EQUAL_FOLD"
    OBSERVATION_COUNT = "OBSERVATION_COUNT"


class ScoreAggregationPolicy(StrictModel):
    policy_id: NonEmptyStr
    weight_policy: FoldWeightPolicy = FoldWeightPolicy.EQUAL_FOLD
    minimum_fold_coverage: FiniteDecimal = Field(
        default=Decimal("1"),
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    loss_definition: NonEmptyStr = "NEGATIVE_SCORE"


class ScoreContext(StrictModel):
    score: CompetitionScoreRecord
    cohort_id: NonEmptyStr
    regime_id: NonEmptyStr | None = None
    underlying_id: NonEmptyStr | None = None
    liquidity_bucket: NonEmptyStr | None = None
    strategy_family: NonEmptyStr | None = None


class ConfigurationScoreAggregate(StrictModel):
    configuration_id: NonEmptyStr
    cohort_id: NonEmptyStr
    fold_count: int = Field(ge=1)
    expected_fold_count: int = Field(ge=1)
    coverage: FiniteDecimal = Field(ge=Decimal("0"), le=Decimal("1"))
    mean_score: FiniteDecimal
    median_score: FiniteDecimal
    worst_score: FiniteDecimal
    score_std: FiniteDecimal = Field(ge=Decimal("0"))
    weighted_mean_score: FiniteDecimal
    status: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...] = ()


class ComparisonLossRecord(StrictModel):
    configuration_id: NonEmptyStr
    cohort_id: NonEmptyStr
    unit_id: NonEmptyStr
    loss: FiniteDecimal


class ScoreAggregationResult(StrictModel):
    policy_id: NonEmptyStr
    aggregates: tuple[ConfigurationScoreAggregate, ...]
    loss_series: tuple[ComparisonLossRecord, ...]
    reason_codes: tuple[NonEmptyStr, ...]
    content_sha256: Sha256
