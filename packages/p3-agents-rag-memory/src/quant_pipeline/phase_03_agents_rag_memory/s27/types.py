"""Strict models and configurations for P3.S27."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

from .errors import S27ContractError

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
SignedBelief = Annotated[float, Field(ge=-1.0, le=1.0)]
BeliefDelta = Annotated[float, Field(ge=-2.0, le=2.0)]
PositiveFloat = Annotated[float, Field(gt=0.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]


def _tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    raise TypeError("expected a JSON array")


def _datetime(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise TypeError("expected ISO-8601 datetime")
    if value.tzinfo is None:
        raise ValueError("datetime must include timezone")
    return value.astimezone(UTC)


AwareDateTime = Annotated[datetime, BeforeValidator(_datetime), AfterValidator(lambda x: x.astimezone(UTC))]
StringTuple = Annotated[tuple[NonEmptyStr, ...], BeforeValidator(_tuple)]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, validate_default=True, use_enum_values=False)


class MetricStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    NO_COVERAGE = "NO_COVERAGE"
    BLOCKED = "BLOCKED"


class DeliveryStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    DELIVERED = "DELIVERED"
    SEEN = "SEEN"
    INTERPRETED = "INTERPRETED"
    USED = "USED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class ToolExecutionStatus(StrEnum):
    ENTITLED = "ENTITLED"
    REQUESTED = "REQUESTED"
    AUTHORIZED = "AUTHORIZED"
    EXECUTED = "EXECUTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    VALIDATED = "VALIDATED"


class EventType(StrEnum):
    STIMULUS = "STIMULUS"
    ACTIVATION = "ACTIVATION"
    SOCIAL_DELIVERY = "SOCIAL_DELIVERY"
    SOCIAL_TOOL = "SOCIAL_TOOL"


def _enum(enum_type: type[StrEnum]):
    def parse(value: Any) -> StrEnum:
        if isinstance(value, enum_type):
            return value
        if isinstance(value, str):
            return enum_type(value)
        raise TypeError(f"expected {enum_type.__name__}")

    return parse


MetricStatusValue = Annotated[MetricStatus, BeforeValidator(_enum(MetricStatus))]
DeliveryStatusValue = Annotated[DeliveryStatus, BeforeValidator(_enum(DeliveryStatus))]
ToolExecutionStatusValue = Annotated[ToolExecutionStatus, BeforeValidator(_enum(ToolExecutionStatus))]


class ArtifactContext(StrictModel):
    schema_version: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonNegativeInt
    as_of_time: AwareDateTime
    lineage_id: NonEmptyStr


class PopulationRecord(StrictModel):
    person_id: NonEmptyStr
    representation_weight: PositiveFloat
    role: NonEmptyStr | None = None
    institution_type: NonEmptyStr | None = None
    lineage_id: NonEmptyStr


class ValidatedPopulationManifest(ArtifactContext):
    records: Annotated[tuple[PopulationRecord, ...], BeforeValidator(_tuple)]

    @model_validator(mode="after")
    def unique_people(self) -> "ValidatedPopulationManifest":
        ids = [record.person_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("population person_id values must be unique")
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
    def delta_matches(self) -> "BeliefStateRecord":
        if abs((self.new_value - self.prior_value) - self.delta) > 1e-9:
            raise ValueError("belief delta must equal new_value - prior_value")
        if self.prior_updated_at is not None and self.prior_updated_at >= self.changed_at:
            raise ValueError("prior_updated_at must precede changed_at")
        return self


class NextBeliefStatePanel(ArtifactContext):
    records: Annotated[tuple[BeliefStateRecord, ...], BeforeValidator(_tuple)]


class StimulusRecord(StrictModel):
    stimulus_id: NonEmptyStr
    origin: NonEmptyStr
    source_event_id: NonEmptyStr
    causal_parent_id: NonEmptyStr | None = None
    target_person_id: NonEmptyStr | None = None
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    created_cycle: NonNegativeInt
    target_cycle: NonNegativeInt
    event_time: AwareDateTime
    available_at: AwareDateTime
    evidence_refs: StringTuple
    lineage_id: NonEmptyStr


class StimulusPanel(ArtifactContext):
    records: Annotated[tuple[StimulusRecord, ...], BeforeValidator(_tuple)]


class PropositionDefinition(StrictModel):
    proposition_id: NonEmptyStr
    description: NonEmptyStr
    allowed_horizons: StringTuple


class PropositionRegistryConfig(StrictModel):
    version: NonEmptyStr
    propositions: Annotated[tuple[PropositionDefinition, ...], BeforeValidator(_tuple)]

    @model_validator(mode="after")
    def unique_propositions(self) -> "PropositionRegistryConfig":
        ids = [item.proposition_id for item in self.propositions]
        if len(ids) != len(set(ids)):
            raise ValueError("proposition IDs must be unique")
        return self


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
    relationship_observations: Annotated[tuple[RelationshipObservationStub, ...], BeforeValidator(_tuple)] = ()
    state_change_summary: StateChangeSummaryStub | None = None
    emergence_states: Annotated[tuple[PersonEmergenceState, ...], BeforeValidator(_tuple)] = ()


class ValidatedNextPersonStatePanel(ArtifactContext):
    records: Annotated[tuple[NextPersonStateRecord, ...], BeforeValidator(_tuple)]


class ToolCallAuditRecord(StrictModel):
    call_id: NonEmptyStr
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    execution_status: ToolExecutionStatusValue
    result_validated: bool
    executed_at: AwareDateTime
    information_gain: Probability
    research_depth: Probability
    evidence_refs: StringTuple
    lineage_id: NonEmptyStr


class ToolCallAuditPanel(ArtifactContext):
    records: Annotated[tuple[ToolCallAuditRecord, ...], BeforeValidator(_tuple)]


class PersonToolEntitlementRecord(StrictModel):
    person_id: NonEmptyStr
    tool_id: NonEmptyStr
    entitled: bool
    underlying_id: NonEmptyStr | None = None
    proposition_id: NonEmptyStr | None = None
    horizon: NonEmptyStr | None = None
    lineage_id: NonEmptyStr


class PersonToolEntitlementPanel(ArtifactContext):
    records: Annotated[tuple[PersonToolEntitlementRecord, ...], BeforeValidator(_tuple)]


class ActivationRecord(StrictModel):
    activation_id: NonEmptyStr
    person_id: NonEmptyStr
    stimulus_id: NonEmptyStr
    activation_reason: NonEmptyStr
    activation_score: Probability
    threshold: Probability
    scheduled_at: AwareDateTime
    causal_parent_id: NonEmptyStr | None = None
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    lineage_id: NonEmptyStr


class ActivationPanel(ArtifactContext):
    records: Annotated[tuple[ActivationRecord, ...], BeforeValidator(_tuple)]


class SocialDeliveryRecord(StrictModel):
    message_id: NonEmptyStr
    sender_person_id: NonEmptyStr
    receiver_person_id: NonEmptyStr
    status: DeliveryStatusValue
    created_cycle: NonNegativeInt
    effective_cycle: NonNegativeInt
    created_at: AwareDateTime
    status_at: AwareDateTime
    causal_parent_id: NonEmptyStr | None = None
    underlying_id: NonEmptyStr | None = None
    proposition_id: NonEmptyStr | None = None
    horizon: NonEmptyStr | None = None
    evidence_refs: StringTuple = ()
    lineage_id: NonEmptyStr


class SocialDeliveryPanel(ArtifactContext):
    records: Annotated[tuple[SocialDeliveryRecord, ...], BeforeValidator(_tuple)]


class SocialToolAuditRecord(StrictModel):
    audit_id: NonEmptyStr
    person_id: NonEmptyStr
    message_id: NonEmptyStr
    tool_call_id: NonEmptyStr
    execution_status: ToolExecutionStatusValue
    result_validated: bool
    event_time: AwareDateTime
    causal_parent_id: NonEmptyStr | None = None
    evidence_refs: StringTuple = ()
    lineage_id: NonEmptyStr


class SocialToolAuditPanel(ArtifactContext):
    records: Annotated[tuple[SocialToolAuditRecord, ...], BeforeValidator(_tuple)]


class AggregationSemanticsConfig(StrictModel):
    version: NonEmptyStr
    formula_version: NonEmptyStr
    bearish_threshold: Annotated[float, Field(ge=-1.0, lt=0.0)]
    bullish_threshold: Annotated[float, Field(gt=0.0, le=1.0)]
    reversal_epsilon: Probability
    velocity_min_elapsed_seconds: PositiveFloat
    attention_formula: Literal["weighted_mean_and_one_minus_normalized_entropy"]
    information_formula: Literal["weighted_population_standard_deviation"]
    information_access_weight: Probability
    research_depth_weight: Probability
    validated_tool_weight: Probability
    validated_tool_gain_cap: Probability
    causal_delivery_statuses: Annotated[tuple[DeliveryStatusValue, ...], BeforeValidator(_tuple)]
    validated_tool_statuses: Annotated[tuple[ToolExecutionStatusValue, ...], BeforeValidator(_tuple)]
    secondary_activation_reasons: StringTuple
    influence_concentration_formula: Literal["HHI"]
    zero_coverage_policy: Literal["MATERIAL_RECORD"]
    reject_causal_cycles: Literal[True]

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "AggregationSemanticsConfig":
        total = self.information_access_weight + self.research_depth_weight + self.validated_tool_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError("information component weights must sum to one")
        if self.bearish_threshold >= self.bullish_threshold:
            raise ValueError("bearish threshold must be below bullish threshold")
        return self


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
    records: Annotated[tuple[BeliefDistributionRecord, ...], BeforeValidator(_tuple)]


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
    records: Annotated[tuple[AttentionInformationRecord, ...], BeforeValidator(_tuple)]


class CascadeDetail(StrictModel):
    cascade_id: NonEmptyStr
    root_stimulus_id: NonEmptyStr
    size: PositiveInt
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
    cascades: Annotated[tuple[CascadeDetail, ...], BeforeValidator(_tuple)]
    input_lineage_ids: StringTuple


class CascadeMetricsPanel(ArtifactContext):
    formula_version: NonEmptyStr
    records: Annotated[tuple[CascadeMetricsRecord, ...], BeforeValidator(_tuple)]


def validate_group(proposition_registry: PropositionRegistryConfig, proposition_id: str, horizon: str) -> None:
    definitions = {item.proposition_id: set(item.allowed_horizons) for item in proposition_registry.propositions}
    if proposition_id not in definitions:
        raise S27ContractError(f"unknown proposition_id: {proposition_id}")
    if horizon not in definitions[proposition_id]:
        raise S27ContractError(f"horizon {horizon!r} is not valid for {proposition_id!r}")
