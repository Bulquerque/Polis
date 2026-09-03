from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import StrictModel, TimeAwareModel
from ..domain.enums import AdjustmentStatus, ComparisonStatus, Direction, FrontierStatus

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class ComparisonGroupRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    underlying_id: str
    horizon: str
    objective_family: str
    capital_at_risk_bucket: str
    lineage_id: str


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
    missingness_status: str
    comparison_status: ComparisonStatus
    reason_code: str | None
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


class ParetoFrontierRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    frontier_layer: int | None = Field(default=None, ge=0)
    frontier_status: FrontierStatus
    dominated_by_count: int = Field(ge=0)
    metric_vector_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    policy_id: str
    lineage_id: str


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
    status: Literal["DOMINATED"]
    dominator_candidate_ids: tuple[str, ...]
    incoming_relation_count: int = Field(ge=1)
    lineage_id: str


class DominanceSurvivorRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    status: Literal["SURVIVOR", "INCOMPARABLE_MISSING_REQUIRED"]
    eligible_for_pareto: bool
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


class FactorAdjustmentAuditRecord(StrictModel):
    policy_id: str
    mode: str
    model_id: str | None
    model_status: str
    target_metric_id: str
    adjusted_candidate_count: int = Field(ge=0)
    bypassed_candidate_count: int = Field(ge=0)
    unavailable_candidate_count: int = Field(ge=0)
    blocked_candidate_count: int = Field(ge=0)
    conservation_max_abs_error: NonNegativeFloat
    reason_counts: dict[str, int]


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

    @model_validator(mode="after")
    def validate_unique_references(self) -> "HandoffManifestRecord":
        names = [row.artifact_name for row in self.references]
        if len(names) != len(set(names)):
            raise ValueError("manifest references must be unique by artifact_name")
        return self
