from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .base import StrictModel, TimeAwareModel
from ..domain.enums import (
    AdjustmentStatus,
    CandidateDominanceStatus,
    ComparisonStatus,
    Direction,
    FactorMode,
    FrontierStatus,
    MissingAction,
    MissingnessStatus,
    ModelQualificationStatus,
)

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class EligibleCandidateRecord(StrictModel):
    candidate_id: str
    underlying_id: str
    horizon: str
    objective_family: str
    capital_at_risk_bucket: str
    lineage_id: str
    factor_values: dict[str, FiniteFloat] = Field(default_factory=dict)


class ComparisonGroupRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    underlying_id: str
    horizon: str
    objective_family: str
    capital_at_risk_bucket: str
    lineage_id: str


class MetricSourceRecord(TimeAwareModel):
    _time_fields = ("available_at",)

    candidate_id: str
    metric_id: str
    raw_value: FiniteFloat | None
    units: str
    direction: Direction
    semantic_version: str
    source_artifact_id: str
    available_at: datetime
    missingness_status: MissingnessStatus
    lineage_id: str

    @model_validator(mode="after")
    def validate_value_status(self) -> "MetricSourceRecord":
        if self.missingness_status == MissingnessStatus.AVAILABLE and self.raw_value is None:
            raise ValueError("AVAILABLE metric requires raw_value")
        if self.missingness_status != MissingnessStatus.AVAILABLE and self.raw_value is not None:
            raise ValueError("missing metric status requires null raw_value")
        return self


class MetricPolicy(StrictModel):
    metric_id: str
    canonical_units: str
    direction: Direction
    semantic_version: str
    missing_action: MissingAction
    active_for_dominance: bool
    epsilon_absolute: NonNegativeFloat = 0.0
    epsilon_relative: NonNegativeFloat = 0.0
    factor_adjustment_target: bool = False


class UnitConversionPolicy(StrictModel):
    metric_id: str
    from_units: str
    to_units: str
    factor: FiniteFloat
    offset: FiniteFloat = 0.0


class FactorAdjustmentPolicy(StrictModel):
    mode: FactorMode
    target_metric_id: str
    factor_schema_version: str
    factor_ids: tuple[str, ...]
    static_coefficients: dict[str, FiniteFloat] = Field(default_factory=dict)
    static_intercept: FiniteFloat = 0.0
    missing_exposure_action: Literal["BYPASS_TARGET", "UNAVAILABLE", "BLOCK"] = "UNAVAILABLE"


class DominancePolicy(StrictModel):
    active_metric_ids: tuple[str, ...]
    missing_required_metric_action: Literal["INCOMPARABLE", "BLOCK_CANDIDATE"]
    exact_max_group_size: int = Field(ge=1, le=100_000)
    exact_max_pair_comparisons: int = Field(ge=1)

    @field_validator("active_metric_ids")
    @classmethod
    def unique_metric_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("active_metric_ids must be unique")
        return value


class RankingPolicyRecord(StrictModel):
    policy_id: str
    policy_version: str
    operational_mode: str
    metric_policies: tuple[MetricPolicy, ...]
    unit_conversions: tuple[UnitConversionPolicy, ...] = ()
    factor_adjustment: FactorAdjustmentPolicy
    dominance: DominancePolicy
    forbidden_field_names: tuple[str, ...]

    @model_validator(mode="after")
    def validate_policy_consistency(self) -> "RankingPolicyRecord":
        metric_ids = [row.metric_id for row in self.metric_policies]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("metric policies must be unique")
        known = set(metric_ids)
        missing = set(self.dominance.active_metric_ids) - known
        if missing:
            raise ValueError(f"dominance metrics absent from metric policies: {sorted(missing)}")
        if self.factor_adjustment.target_metric_id not in known:
            raise ValueError("factor target metric must exist in metric policies")
        return self


class OptionFactorModelRecord(TimeAwareModel):
    _time_fields = ("training_cutoff_at",)

    model_id: str
    model_version: str
    qualification_status: ModelQualificationStatus
    training_cutoff_at: datetime
    factor_schema_version: str
    target_metric_id: str
    intercept: FiniteFloat
    coefficients: dict[str, FiniteFloat]
    lineage_id: str


class FoundationAuditRecord(StrictModel):
    status: Literal["PASS", "PASS_WITH_WARNINGS"]
    candidate_count: int = Field(ge=0)
    comparison_group_count: int = Field(ge=0)
    comparison_groups_frozen: bool
    candidate_reconciliation_passed: bool
    forbidden_field_scan_passed: bool


class ArtifactReference(StrictModel):
    artifact_name: str
    artifact_id: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str
    record_count: int = Field(ge=0)


class HandoffManifestRecord(StrictModel):
    contract_id: str
    producer: str
    consumer: str
    references: tuple[ArtifactReference, ...]


class ComparableMetricRecord(TimeAwareModel):
    _time_fields = ("source_available_at",)

    candidate_id: str
    comparison_group_id: str
    metric_id: str
    raw_value: FiniteFloat | None
    canonical_value: FiniteFloat | None
    directed_value: FiniteFloat | None
    canonical_units: str
    direction: Direction
    semantic_version: str
    source_artifact_id: str
    source_available_at: datetime
    missingness_status: MissingnessStatus
    comparison_status: ComparisonStatus
    reason_code: str | None
    lineage_id: str


class MetricSemanticsAuditRecord(StrictModel):
    policy_id: str
    candidate_count: int = Field(ge=0)
    source_metric_count: int = Field(ge=0)
    output_metric_count: int = Field(ge=0)
    converted_metric_count: int = Field(ge=0)
    blocked_metric_count: int = Field(ge=0)
    unavailable_metric_count: int = Field(ge=0)
    forbidden_field_scan_passed: bool
    duplicate_grain_count: int = Field(ge=0)
    reason_counts: dict[str, int]


class FactorExposureRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    factor_id: str
    exposure_value: FiniteFloat
    coefficient: FiniteFloat
    contribution: FiniteFloat
    model_id: str
    factor_schema_version: str
    lineage_id: str


class FactorAdjustedMetricRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    metric_id: str
    raw_value: FiniteFloat | None
    directed_value: FiniteFloat | None
    adjusted_raw_value: FiniteFloat | None
    adjusted_directed_value: FiniteFloat | None
    adjustment_status: AdjustmentStatus
    adjustment_model_id: str | None
    total_factor_contribution: FiniteFloat | None
    intercept: FiniteFloat | None
    reason_code: str | None
    lineage_id: str


class FactorAdjustmentAuditRecord(StrictModel):
    policy_id: str
    mode: FactorMode
    model_id: str | None
    model_status: str
    target_metric_id: str
    adjusted_candidate_count: int = Field(ge=0)
    bypassed_candidate_count: int = Field(ge=0)
    unavailable_candidate_count: int = Field(ge=0)
    blocked_candidate_count: int = Field(ge=0)
    conservation_max_abs_error: NonNegativeFloat
    reason_counts: dict[str, int]


class DominanceEvidence(StrictModel):
    metric_id: str
    dominator_value: FiniteFloat
    dominated_value: FiniteFloat
    tolerance: NonNegativeFloat
    materially_better: bool


class DominanceRelationRecord(StrictModel):
    comparison_group_id: str
    dominator_candidate_id: str
    dominated_candidate_id: str
    evidence: tuple[DominanceEvidence, ...]
    policy_id: str
    relation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class DominatedCandidateRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    status: Literal[CandidateDominanceStatus.DOMINATED]
    dominator_candidate_ids: tuple[str, ...]
    incoming_relation_count: int = Field(ge=1)
    lineage_id: str


class DominanceSurvivorRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    status: Literal[
        CandidateDominanceStatus.SURVIVOR,
        CandidateDominanceStatus.INCOMPARABLE_MISSING_REQUIRED,
    ]
    eligible_for_pareto: bool
    reason_code: str | None
    lineage_id: str


class ParetoFrontierRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    frontier_layer: int | None = Field(default=None, ge=0)
    frontier_status: FrontierStatus
    dominated_by_count: int = Field(ge=0)
    metric_vector_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    policy_id: str
    lineage_id: str


class ParetoGroupDiagnostic(StrictModel):
    comparison_group_id: str
    candidate_count: int = Field(ge=0)
    comparable_candidate_count: int = Field(ge=0)
    incomparable_candidate_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    layer_count: int = Field(ge=0)
    pair_comparisons: int = Field(ge=0)


class ParetoFrontierAuditRecord(StrictModel):
    policy_id: str
    exact_algorithm: bool
    group_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    frontier_count: int = Field(ge=0)
    incomparable_count: int = Field(ge=0)
    diagnostics: tuple[ParetoGroupDiagnostic, ...]
    permutation_invariant_serialization: bool
