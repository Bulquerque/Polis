"""Input artifact contracts for P3.S28."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from .types_common import (
    ArtifactContext,
    AwareDateTime,
    BeliefDelta,
    MetricStatusValue,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    Probability,
    SignedBelief,
    SourceQualityStatusValue,
    StrictModel,
    StringTuple,
    as_tuple,
)


class TagAssignment(StrictModel):
    category_id: NonEmptyStr
    tag_id: NonEmptyStr
    intensity: Probability
    confidence: Probability

    @property
    def effective_value(self) -> float:
        return self.intensity * self.confidence


class PersonSeedRecord(StrictModel):
    person_id: NonEmptyStr
    tags: Annotated[tuple[TagAssignment, ...], BeforeValidator(as_tuple)]
    role: NonEmptyStr | None = None
    institution_type: NonEmptyStr | None = None
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def unique_assignments(self) -> "PersonSeedRecord":
        ids = [item.tag_id for item in self.tags]
        if len(ids) != len(set(ids)):
            raise ValueError("person tag assignments must be unique")
        return self


class PersonSeedPanel(ArtifactContext):
    records: Annotated[tuple[PersonSeedRecord, ...], BeforeValidator(as_tuple)]

    @model_validator(mode="after")
    def unique_people(self) -> "PersonSeedPanel":
        ids = [item.person_id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("person_seed_panel person IDs must be unique")
        return self


class PopulationRecord(StrictModel):
    person_id: NonEmptyStr
    representation_weight: PositiveFloat
    role: NonEmptyStr | None = None
    institution_type: NonEmptyStr | None = None
    lineage_id: NonEmptyStr


class ValidatedPopulationManifest(ArtifactContext):
    records: Annotated[tuple[PopulationRecord, ...], BeforeValidator(as_tuple)]

    @model_validator(mode="after")
    def unique_people(self) -> "ValidatedPopulationManifest":
        ids = [item.person_id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("population person IDs must be unique")
        return self


class BeliefStateRecord(StrictModel):
    person_id: NonEmptyStr
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    prior_value: SignedBelief
    new_value: SignedBelief
    delta: BeliefDelta
    confidence: Probability
    uncertainty: Probability
    prior_updated_at: AwareDateTime | None = None
    changed_at: AwareDateTime
    commitment_id: NonEmptyStr
    evidence_refs: StringTuple
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_delta(self) -> "BeliefStateRecord":
        if abs((self.new_value - self.prior_value) - self.delta) > 1e-9:
            raise ValueError("belief delta must equal new_value - prior_value")
        if self.prior_updated_at is not None and self.prior_updated_at >= self.changed_at:
            raise ValueError("prior_updated_at must precede changed_at")
        return self


class NextBeliefStatePanel(ArtifactContext):
    records: Annotated[tuple[BeliefStateRecord, ...], BeforeValidator(as_tuple)]


class RelationshipObservationStub(StrictModel):
    observation_id: NonEmptyStr
    observer_person_id: NonEmptyStr
    counterparty_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    domain: NonEmptyStr
    signal: Annotated[float, Field(ge=-1.0, le=1.0)]
    reliability: Probability
    experience_type: NonEmptyStr
    source_message_id: NonEmptyStr | None = None
    observed_at: AwareDateTime
    effective_cycle: NonNegativeInt
    evidence_refs: StringTuple
    lineage_id: NonEmptyStr


class StateChangeSummaryStub(StrictModel):
    change_id: NonEmptyStr
    content_ref: NonEmptyStr
    change_magnitude: Probability
    source_event_ids: StringTuple
    evidence_refs: StringTuple
    changed_at: AwareDateTime
    lineage_id: NonEmptyStr


class PersonEmergenceState(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    attention_score: Probability
    information_access_score: Probability
    research_depth: Probability
    updated_at: AwareDateTime
    lineage_id: NonEmptyStr


class NextPersonStateRecord(StrictModel):
    person_id: NonEmptyStr
    relationship_observations: Annotated[tuple[RelationshipObservationStub, ...], BeforeValidator(as_tuple)] = ()
    state_change_summary: StateChangeSummaryStub | None = None
    emergence_states: Annotated[tuple[PersonEmergenceState, ...], BeforeValidator(as_tuple)] = ()


class ValidatedNextPersonStatePanel(ArtifactContext):
    records: Annotated[tuple[NextPersonStateRecord, ...], BeforeValidator(as_tuple)]


class BeliefDistributionRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    as_of_time: AwareDateTime
    formula_version: NonEmptyStr
    status: MetricStatusValue
    active_person_count: NonNegativeInt
    population_size: NonNegativeInt
    population_coverage_ratio: Probability
    weight_coverage_ratio: Probability
    effective_n: NonNegativeFloat
    belief_mean: float | None = None
    belief_variance: NonNegativeFloat | None = None
    belief_entropy: Probability | None = None
    belief_polarization: Probability | None = None
    bullish_share: Probability | None = None
    neutral_share: Probability | None = None
    bearish_share: Probability | None = None
    belief_update_velocity_per_day: NonNegativeFloat | None = None
    belief_reversal_rate: Probability | None = None
    dynamics_applicability: Literal["APPLICABLE", "NOT_APPLICABLE_GENESIS"] = "APPLICABLE"
    dynamics_coverage_ratio: Probability
    input_lineage_ids: StringTuple


class BeliefDistributionPanel(ArtifactContext):
    formula_version: NonEmptyStr
    records: Annotated[tuple[BeliefDistributionRecord, ...], BeforeValidator(as_tuple)]


class AttentionInformationRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    as_of_time: AwareDateTime
    formula_version: NonEmptyStr
    status: MetricStatusValue
    active_person_count: NonNegativeInt
    population_size: NonNegativeInt
    population_coverage_ratio: Probability
    effective_n: NonNegativeFloat
    attention_intensity: Probability | None = None
    attention_concentration: Probability | None = None
    mean_information_access_score: Probability | None = None
    information_asymmetry: NonNegativeFloat | None = None
    entitlement_coverage_ratio: Probability
    executed_tool_coverage_ratio: Probability
    validated_tool_call_count: NonNegativeInt
    input_lineage_ids: StringTuple


class AttentionInformationMetrics(ArtifactContext):
    formula_version: NonEmptyStr
    records: Annotated[tuple[AttentionInformationRecord, ...], BeforeValidator(as_tuple)]


class CascadeDetail(StrictModel):
    cascade_id: NonEmptyStr
    root_stimulus_id: NonEmptyStr
    size: NonNegativeInt
    depth: NonNegativeInt
    duration_seconds: NonNegativeFloat
    speed_events_per_second: NonNegativeFloat
    secondary_activation_count: NonNegativeInt
    exposed_person_count: NonNegativeInt
    social_contagion: Probability
    influence_concentration: Probability
    started_at: AwareDateTime
    ended_at: AwareDateTime
    node_ids: StringTuple


class CascadeMetricsRecord(StrictModel):
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    as_of_time: AwareDateTime
    formula_version: NonEmptyStr
    status: MetricStatusValue
    cascade_count: NonNegativeInt
    mean_cascade_size: NonNegativeFloat
    max_cascade_size: NonNegativeInt
    mean_cascade_depth: NonNegativeFloat
    max_cascade_depth: NonNegativeInt
    mean_cascade_speed: NonNegativeFloat
    mean_cascade_duration_seconds: NonNegativeFloat
    secondary_activation_rate: Probability
    social_contagion: Probability
    influence_concentration: Probability
    causal_coverage_ratio: Probability
    linked_event_count: NonNegativeInt
    unlinked_event_count: NonNegativeInt
    cascades: Annotated[tuple[CascadeDetail, ...], BeforeValidator(as_tuple)]
    input_lineage_ids: StringTuple


class CascadeMetricsPanel(ArtifactContext):
    formula_version: NonEmptyStr
    records: Annotated[tuple[CascadeMetricsRecord, ...], BeforeValidator(as_tuple)]


class SourceQualityRecord(StrictModel):
    artifact_id: NonEmptyStr
    quality_score: Probability
    completeness: Probability
    validity: Probability
    timeliness: Probability
    lineage_completeness: Probability
    status: SourceQualityStatusValue
    assessed_at: AwareDateTime
    lineage_id: NonEmptyStr


class SourceQualityPanel(ArtifactContext):
    records: Annotated[tuple[SourceQualityRecord, ...], BeforeValidator(as_tuple)]

    @model_validator(mode="after")
    def unique_artifacts(self) -> "SourceQualityPanel":
        ids = [item.artifact_id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("source quality artifact IDs must be unique")
        return self


class Phase3RunSnapshot(ArtifactContext):
    snapshot_id: NonEmptyStr
    config_hash: NonEmptyStr
    status: NonEmptyStr
