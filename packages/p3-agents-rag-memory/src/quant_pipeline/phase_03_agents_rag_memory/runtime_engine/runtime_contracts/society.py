from __future__ import annotations

from typing import Annotated

from pydantic import Field, JsonValue, model_validator

from .base import (
    CanonicalArtifact,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    Probability,
    StrictModel,
)


class BeliefDistributionRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    negative_mass: Probability
    neutral_mass: Probability
    positive_mass: Probability
    belief_mean: Annotated[float, Field(ge=-1.0, le=1.0)]
    belief_variance: NonNegativeFloat
    normalized_entropy: Probability
    polarization: Probability
    effective_sample_size: NonNegativeFloat
    population_size: NonNegativeInt
    coverage_ratio: Probability
    source_quality_score: Probability
    formula_id: NonEmptyStr
    formula_version: NonEmptyStr
    lineage_ids: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def masses_sum_to_one(self) -> "BeliefDistributionRecord":
        if abs(self.negative_mass + self.neutral_mass + self.positive_mass - 1.0) > 1e-8:
            raise ValueError("direction masses must sum to one")
        return self


class BeliefDistributionPanel(CanonicalArtifact):
    records: tuple[BeliefDistributionRecord, ...]


class SocietyStateRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    confidence_dispersion: Probability
    evidence_diversity: Probability
    attention_concentration: Probability
    information_asymmetry: Probability
    coverage_ratio: Probability
    source_quality_score: Probability
    quality_status: NonEmptyStr
    quality_reasons: tuple[str, ...] = ()
    lineage_ids: tuple[NonEmptyStr, ...]
    feature_payload: dict[str, JsonValue] = Field(default_factory=dict)


class SocietyStatePanel(CanonicalArtifact):
    records: tuple[SocietyStateRecord, ...]


class MemoryFeatureRecord(StrictModel):
    person_id: NonEmptyStr
    active_memory_count: NonNegativeInt
    mean_importance: Probability
    mean_confidence: Probability
    mean_retrievability: Probability
    episodic_share: Probability
    semantic_share: Probability
    social_share: Probability
    audit_share: Probability
    lineage_ids: tuple[NonEmptyStr, ...]


class MemoryFeatureProjection(CanonicalArtifact):
    population_size: NonNegativeInt
    records: tuple[MemoryFeatureRecord, ...]
