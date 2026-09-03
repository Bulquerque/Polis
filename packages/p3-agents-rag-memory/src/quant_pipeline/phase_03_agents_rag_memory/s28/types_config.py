"""Configuration contracts for P3.S28."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from .types_common import NonEmptyStr, PositiveFloat, PositiveInt, Probability, StrictModel, StringTuple, as_tuple


class TagDefinition(StrictModel):
    tag_id: NonEmptyStr
    description: NonEmptyStr


class TagCategory(StrictModel):
    category_id: NonEmptyStr
    tags: Annotated[tuple[TagDefinition, ...], BeforeValidator(as_tuple)]


class PersonalityTagRegistry(StrictModel):
    registry_id: NonEmptyStr
    policy: Literal["fixed_registry_no_free_tag_creation"]
    assignment_fields: StringTuple
    categories: Annotated[tuple[TagCategory, ...], BeforeValidator(as_tuple)]
    schema_version: NonEmptyStr | None = None
    lineage_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def unique_tags(self) -> "PersonalityTagRegistry":
        pairs = [(category.category_id, tag.tag_id) for category in self.categories for tag in category.tags]
        tag_ids = [tag_id for _, tag_id in pairs]
        if len(pairs) != len(set(pairs)) or len(tag_ids) != len(set(tag_ids)):
            raise ValueError("tag registry must contain globally unique tag IDs")
        if set(self.assignment_fields) != {"intensity", "confidence"}:
            raise ValueError("tag assignments require intensity and confidence")
        return self

    def tag_categories(self) -> dict[str, str]:
        return {tag.tag_id: category.category_id for category in self.categories for tag in category.tags}


class PropositionDefinition(StrictModel):
    proposition_id: NonEmptyStr
    description: NonEmptyStr
    allowed_horizons: StringTuple


class PropositionRegistryConfig(StrictModel):
    version: NonEmptyStr
    propositions: Annotated[tuple[PropositionDefinition, ...], BeforeValidator(as_tuple)]

    @model_validator(mode="after")
    def unique_propositions(self) -> "PropositionRegistryConfig":
        ids = [item.proposition_id for item in self.propositions]
        if len(ids) != len(set(ids)):
            raise ValueError("proposition IDs must be unique")
        return self

    def validate_grain(self, proposition_id: str, horizon: str) -> None:
        definitions = {item.proposition_id: set(item.allowed_horizons) for item in self.propositions}
        if proposition_id not in definitions:
            raise ValueError(f"unknown proposition_id: {proposition_id}")
        if horizon not in definitions[proposition_id]:
            raise ValueError(f"horizon {horizon!r} is invalid for {proposition_id!r}")


class S28AggregationSemanticsConfig(StrictModel):
    version: NonEmptyStr
    formula_version: NonEmptyStr
    tag_projection_min_effective_n: PositiveFloat
    tag_projection_min_raw_person_count: PositiveInt
    tag_weight_formula: Literal["representation_x_belief_confidence_x_tag_intensity_x_tag_confidence"]
    population_weight_formula: Literal["representation_x_belief_confidence"]
    suppression_policy: Literal["MATERIAL_SUPPRESSED_RECORD"]
    complement_policy: Literal["PEOPLE_WITHOUT_TAG"]
    divergence_formula: Literal["ABSOLUTE_WEIGHTED_MEAN_DIFFERENCE"]
    institutional_disagreement_formula: Literal["WEIGHTED_STD_OF_INSTITUTION_MEANS"]
    expert_tag_ids: StringTuple
    expert_min_assignment_value: Probability
    institutional_min_effective_n: PositiveFloat
    max_active_tag_projections_per_grain: PositiveInt
    zero_coverage_policy: Literal["MATERIAL_RECORD"]


class QualityThresholds(StrictModel):
    min_active_person_count_pass: PositiveInt
    min_active_person_count_degraded: PositiveInt
    min_effective_n_pass: PositiveFloat
    min_effective_n_degraded: PositiveFloat
    min_population_coverage_pass: Probability
    min_population_coverage_degraded: Probability
    min_belief_coverage_pass: Probability
    min_belief_coverage_degraded: Probability
    min_causal_coverage_pass: Probability
    min_causal_coverage_degraded: Probability
    min_source_quality_pass: Probability
    min_source_quality_degraded: Probability
    min_metric_completeness_pass: Probability
    min_metric_completeness_degraded: Probability
    max_uncertainty_pass: Probability
    max_uncertainty_degraded: Probability

    @model_validator(mode="after")
    def ordered_thresholds(self) -> "QualityThresholds":
        pairs = [
            (self.min_active_person_count_pass, self.min_active_person_count_degraded),
            (self.min_effective_n_pass, self.min_effective_n_degraded),
            (self.min_population_coverage_pass, self.min_population_coverage_degraded),
            (self.min_belief_coverage_pass, self.min_belief_coverage_degraded),
            (self.min_causal_coverage_pass, self.min_causal_coverage_degraded),
            (self.min_source_quality_pass, self.min_source_quality_degraded),
            (self.min_metric_completeness_pass, self.min_metric_completeness_degraded),
        ]
        if any(pass_value < degraded for pass_value, degraded in pairs):
            raise ValueError("pass thresholds must be at least degraded thresholds")
        if self.max_uncertainty_pass > self.max_uncertainty_degraded:
            raise ValueError("pass uncertainty threshold must not exceed degraded threshold")
        return self


class QualityWeights(StrictModel):
    completeness: Probability
    source_quality: Probability
    coverage: Probability
    uncertainty_complement: Probability

    @model_validator(mode="after")
    def sum_to_one(self) -> "QualityWeights":
        total = self.completeness + self.source_quality + self.coverage + self.uncertainty_complement
        if abs(total - 1.0) > 1e-9:
            raise ValueError("quality weights must sum to one")
        return self


class EmergenceVectorConfig(StrictModel):
    vector_id: NonEmptyStr
    vector_version: NonEmptyStr
    formula_version: NonEmptyStr
    grain: StringTuple
    missing_grain_policy: Literal["MATERIAL_MISSING"]
    required_metric_paths: StringTuple
    required_source_artifacts: StringTuple
    max_feature_count: PositiveInt
    source_quality_aggregation: Literal["MINIMUM"]
    uncertainty_formula: Literal["MAX_BELIEF_STD_INFORMATION_ASYMMETRY_COVERAGE_GAPS"]
    quality_score_formula: Literal["WEIGHTED_DIMENSION_SCORE"]
    quality_weights: QualityWeights
    thresholds: QualityThresholds
    forbidden_direct_targets: StringTuple

    @model_validator(mode="after")
    def canonical_grain(self) -> "EmergenceVectorConfig":
        expected = ("underlying_id", "proposition_id", "horizon", "as_of_time")
        if tuple(self.grain) != expected:
            raise ValueError(f"vector grain must be {expected}")
        if len(self.required_metric_paths) > self.max_feature_count:
            raise ValueError("required metric count exceeds max_feature_count")
        return self
