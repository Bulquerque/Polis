"""Output artifact contracts for P3.S28."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field

from .types_common import (
    ArtifactContext,
    AwareDateTime,
    IssueSeverityValue,
    MetricStatusValue,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    Probability,
    ProjectionStatusValue,
    QualityStatusValue,
    StrictModel,
    StringTuple,
    as_tuple,
)


class TagProjectionRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    as_of_time: AwareDateTime
    formula_version: NonEmptyStr
    category_id: NonEmptyStr
    tag_id: NonEmptyStr
    status: ProjectionStatusValue
    raw_person_count: NonNegativeInt
    population_size: NonNegativeInt
    population_coverage_ratio: Probability
    weight_coverage_ratio: Probability
    effective_n: NonNegativeFloat
    cohort_weight_sum: NonNegativeFloat
    cohort_confidence: Probability | None = None
    belief_mean: float | None = None
    belief_variance: NonNegativeFloat | None = None
    population_belief_mean: float | None = None
    shift_vs_population: NonNegativeFloat | None = None
    complement_belief_mean: float | None = None
    divergence_vs_complement: NonNegativeFloat | None = None
    input_lineage_ids: StringTuple


class TagProjectionSummaryRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    as_of_time: AwareDateTime
    formula_version: NonEmptyStr
    status: ProjectionStatusValue
    expert_nonexpert_divergence: NonNegativeFloat | None = None
    institutional_disagreement: NonNegativeFloat | None = None
    expert_nonexpert_applicability: Literal["APPLICABLE", "NOT_APPLICABLE_INSUFFICIENT_COHORTS"] = "APPLICABLE"
    institutional_applicability: Literal["APPLICABLE", "NOT_APPLICABLE_INSUFFICIENT_COHORTS"] = "APPLICABLE"
    top_tag_divergence: NonNegativeFloat | None = None
    top_tag_divergence_id: NonEmptyStr | None = None
    top_tag_conditioned_shift: NonNegativeFloat | None = None
    top_tag_conditioned_shift_id: NonEmptyStr | None = None
    active_tag_projection_count: NonNegativeInt
    suppressed_tag_projection_count: NonNegativeInt
    input_lineage_ids: StringTuple


class TagProjectionPanel(ArtifactContext):
    formula_version: NonEmptyStr
    records: Annotated[tuple[TagProjectionRecord, ...], BeforeValidator(as_tuple)]
    summaries: Annotated[tuple[TagProjectionSummaryRecord, ...], BeforeValidator(as_tuple)]


class FamilyStatus(StrictModel):
    family: NonEmptyStr
    status: MetricStatusValue
    reason_codes: StringTuple = ()


class MetricLineage(StrictModel):
    metric_path: NonEmptyStr
    source_artifact: NonEmptyStr
    input_lineage_ids: StringTuple


class BeliefFeatures(StrictModel):
    belief_mean: float | None
    belief_variance: NonNegativeFloat | None
    belief_entropy: Probability | None
    belief_polarization: Probability | None
    bullish_share: Probability | None
    bearish_share: Probability | None


class DynamicsFeatures(StrictModel):
    belief_update_velocity_per_day: NonNegativeFloat | None
    belief_reversal_rate: Probability | None
    applicability: Literal["APPLICABLE", "NOT_APPLICABLE_GENESIS"] = "APPLICABLE"


class AttentionFeatures(StrictModel):
    attention_intensity: Probability | None
    attention_concentration: Probability | None


class SocialFeatures(StrictModel):
    mean_cascade_size: NonNegativeFloat | None
    mean_cascade_depth: NonNegativeFloat | None
    social_contagion: Probability | None
    influence_concentration: Probability | None


class InformationFeatures(StrictModel):
    information_asymmetry: NonNegativeFloat | None
    expert_nonexpert_divergence: NonNegativeFloat | None
    institutional_disagreement: NonNegativeFloat | None
    expert_nonexpert_applicability: Literal["APPLICABLE", "NOT_APPLICABLE_INSUFFICIENT_COHORTS"] = "APPLICABLE"
    institutional_applicability: Literal["APPLICABLE", "NOT_APPLICABLE_INSUFFICIENT_COHORTS"] = "APPLICABLE"


class TagProjectionFeatures(StrictModel):
    top_tag_divergence: NonNegativeFloat | None
    top_tag_conditioned_shift: NonNegativeFloat | None
    active_tag_projection_count: NonNegativeInt
    suppressed_tag_projection_count: NonNegativeInt


class SocietyFeatures(StrictModel):
    belief: BeliefFeatures
    dynamics: DynamicsFeatures
    attention: AttentionFeatures
    social: SocialFeatures
    information: InformationFeatures
    tag_projection: TagProjectionFeatures


class SocietyCoverage(StrictModel):
    active_person_count: NonNegativeInt
    population_coverage_ratio: Probability
    belief_coverage_ratio: Probability
    attention_population_coverage_ratio: Probability | None
    effective_n: NonNegativeFloat
    causal_coverage_ratio: Probability | None
    tag_projection_count: NonNegativeInt


class SyntheticSocietyStateRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    as_of_time: AwareDateTime
    vector_version: NonEmptyStr
    formula_versions: dict[NonEmptyStr, NonEmptyStr]
    status: MetricStatusValue
    features: SocietyFeatures
    coverage: SocietyCoverage
    family_statuses: Annotated[tuple[FamilyStatus, ...], BeforeValidator(as_tuple)]
    metric_lineage: Annotated[tuple[MetricLineage, ...], BeforeValidator(as_tuple)]
    input_lineage_ids: StringTuple


class SyntheticSocietyStatePanel(ArtifactContext):
    vector_id: NonEmptyStr
    vector_version: NonEmptyStr
    records: Annotated[tuple[SyntheticSocietyStateRecord, ...], BeforeValidator(as_tuple)]


class QualityIssue(StrictModel):
    code: NonEmptyStr
    severity: IssueSeverityValue
    dimension: NonEmptyStr
    observed: float | int | str | None = None
    threshold: float | int | str | None = None
    message: NonEmptyStr


class QualityAssessment(StrictModel):
    status: QualityStatusValue
    quality_score: Probability | None
    metric_completeness: Probability
    source_quality_score: Probability | None
    coverage_score: Probability
    uncertainty_score: Probability | None
    issues: Annotated[tuple[QualityIssue, ...], BeforeValidator(as_tuple)]
    source_artifact_scores: dict[NonEmptyStr, Probability]


class ValidatedSocietyStateRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    as_of_time: AwareDateTime
    vector_version: NonEmptyStr
    formula_versions: dict[NonEmptyStr, NonEmptyStr]
    features: SocietyFeatures
    coverage: SocietyCoverage
    family_statuses: Annotated[tuple[FamilyStatus, ...], BeforeValidator(as_tuple)]
    metric_lineage: Annotated[tuple[MetricLineage, ...], BeforeValidator(as_tuple)]
    quality: QualityAssessment
    input_lineage_ids: StringTuple


class ValidatedSocietyStatePanel(ArtifactContext):
    vector_id: NonEmptyStr
    vector_version: NonEmptyStr
    snapshot_id: NonEmptyStr
    records: Annotated[tuple[ValidatedSocietyStateRecord, ...], BeforeValidator(as_tuple)]
