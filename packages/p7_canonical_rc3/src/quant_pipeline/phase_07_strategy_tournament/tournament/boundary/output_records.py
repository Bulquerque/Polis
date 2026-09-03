from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .base import StrictModel
from .input_records import ArtifactReference
from .policy_records import PenaltyRule
from ..domain.enums import (
    ComponentType,
    HeadStatus,
    MetricSourcePreference,
    MissingHeadAction,
    MissingMetricAction,
    NormalizationMethod,
    ScoreStatus,
    SmallGroupAction,
    TransformationMethod,
)

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class ScoringHeadInputRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    policy_id: str
    policy_version: str
    rule_id: str
    head_id: str
    head_weight: NonNegativeFloat = Field(gt=0)
    missing_head_action: MissingHeadAction
    missing_head_penalty: Probability
    metric_id: str
    source_preference: MetricSourcePreference
    transformation: TransformationMethod
    normalization: NormalizationMethod
    metric_weight: NonNegativeFloat = Field(gt=0)
    clip_lower: FiniteFloat | None
    clip_upper: FiniteFloat | None
    absolute_lower: FiniteFloat | None
    absolute_upper: FiniteFloat | None
    robust_scale: NonNegativeFloat = Field(gt=0)
    min_group_size: int = Field(ge=1)
    small_group_action: SmallGroupAction
    missing_metric_action: MissingMetricAction
    missing_metric_penalty: Probability
    lineage_id: str


class CandidatePolicyResolution(StrictModel):
    candidate_id: str
    comparison_group_id: str
    rule_id: str
    head_ids: tuple[str, ...]
    penalty_rules: tuple[PenaltyRule, ...]
    confidence_head_id: str | None
    confidence_shrinkage_strength: Probability


class ScoringPolicyReceiptRecord(StrictModel):
    policy_id: str
    policy_version: str
    operational_mode: str
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_count: int = Field(ge=0)
    selected_candidate_count: int = Field(ge=0)
    excluded_candidate_count: int = Field(ge=0)
    binding_count: int = Field(ge=0)
    resolutions: tuple[CandidatePolicyResolution, ...]
    rule_counts: dict[str, int]
    forbidden_field_scan_passed: bool


class MetricScoreComponent(StrictModel):
    metric_id: str
    source_kind: Literal["COMPARABLE", "FACTOR_ADJUSTED", "MISSING_PENALTY"]
    raw_directed_value: FiniteFloat | None
    transformed_value: FiniteFloat | None
    normalized_value: Probability | None
    metric_weight: NonNegativeFloat = Field(gt=0)
    contribution: NonNegativeFloat
    status: Literal["AVAILABLE", "PENALIZED", "RENORMALIZED", "UNAVAILABLE", "BLOCKED"]
    reason_code: str | None


class ScoringHeadRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    policy_id: str
    policy_version: str
    rule_id: str
    head_id: str
    head_weight: NonNegativeFloat = Field(gt=0)
    missing_head_action: MissingHeadAction
    missing_head_penalty: Probability
    head_status: HeadStatus
    head_score: Probability | None
    effective_metric_weight: NonNegativeFloat
    expected_metric_count: int = Field(ge=1)
    available_metric_count: int = Field(ge=0)
    stages: tuple[MetricScoreComponent, ...]
    reason_code: str | None
    lineage_id: str


class HeadScoreContribution(StrictModel):
    head_id: str
    head_score: Probability
    head_weight: NonNegativeFloat = Field(gt=0)
    weighted_contribution: NonNegativeFloat
    source_status: HeadStatus


class AppliedPenalty(StrictModel):
    penalty_id: str
    head_id: str
    threshold: Probability
    coefficient: NonNegativeFloat
    head_score: Probability
    penalty_value: NonNegativeFloat


class InterpretableScoreRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    policy_id: str
    policy_version: str
    rule_id: str
    score_status: ScoreStatus
    base_score: Probability | None
    effective_head_weight: NonNegativeFloat
    head_contributions: tuple[HeadScoreContribution, ...]
    applied_penalties: tuple[AppliedPenalty, ...]
    penalty_total: NonNegativeFloat
    confidence_head_id: str | None
    confidence_score: Probability | None
    confidence_adjustment: FiniteFloat
    boundary_adjustment: FiniteFloat
    final_interpretable_score: Probability | None
    reason_code: str | None
    lineage_id: str


class ScoreDecompositionRecord(StrictModel):
    candidate_id: str
    comparison_group_id: str
    stage_type: ComponentType
    stage_id: str
    head_id: str | None
    metric_id: str | None
    raw_value: FiniteFloat | None
    transformed_value: FiniteFloat | None
    normalized_value: FiniteFloat | None
    local_weight: NonNegativeFloat | None
    global_weight: NonNegativeFloat | None
    score_contribution: FiniteFloat
    source_artifact_id: str | None
    policy_id: str
    policy_version: str
    lineage_id: str


class InterpretableTournamentAuditRecord(StrictModel):
    policy_id: str
    policy_version: str
    input_candidate_count: int = Field(ge=0)
    frontier_candidate_count: int = Field(ge=0)
    dominated_candidate_count: int = Field(ge=0)
    incomparable_candidate_count: int = Field(ge=0)
    scored_candidate_count: int = Field(ge=0)
    blocked_candidate_count: int = Field(ge=0)
    unavailable_candidate_count: int = Field(ge=0)
    decomposition_record_count: int = Field(ge=0)
    max_abs_reconciliation_error: NonNegativeFloat
    candidate_conservation_passed: bool
    forbidden_field_scan_passed: bool
    reason_counts: dict[str, int]


class TournamentHandoffManifestRecord(StrictModel):
    contract_id: str
    producer: Literal["P7.TOURNAMENT"]
    consumer: Literal["P7.LEARNING"]
    references: tuple[ArtifactReference, ...]
