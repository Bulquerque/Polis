from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$"


def aware_utc(value: datetime) -> datetime:
    """Normalize a timezone-aware datetime to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class ContractModel(BaseModel):
    """Strict immutable model used at every S19 boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_default=True,
        populate_by_name=True,
    )


class ExecutionStatus(StrEnum):
    READY = "READY"
    READY_EMPTY = "READY_EMPTY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class StimulusOrigin(StrEnum):
    EXTERNAL_PIT_CONTEXT = "EXTERNAL_PIT_CONTEXT"
    TOOL_DISCOVERY = "TOOL_DISCOVERY"
    SOCIAL_DELIVERY = "SOCIAL_DELIVERY"
    MEMORY_TRIGGER = "MEMORY_TRIGGER"
    ATTENTION_FOLLOWUP = "ATTENTION_FOLLOWUP"


class StimulusType(StrEnum):
    NEWS_EVENT = "NEWS_EVENT"
    FILING_EVENT = "FILING_EVENT"
    MACRO_RELEASE = "MACRO_RELEASE"
    MARKET_EVENT = "MARKET_EVENT"
    RESEARCH_EVENT = "RESEARCH_EVENT"
    POLICY_EVENT = "POLICY_EVENT"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    TOOL_DISCOVERY_EVENT = "TOOL_DISCOVERY_EVENT"
    SOCIAL_MESSAGE_EVENT = "SOCIAL_MESSAGE_EVENT"
    MEMORY_TRIGGER_EVENT = "MEMORY_TRIGGER_EVENT"
    ATTENTION_FOLLOWUP_EVENT = "ATTENTION_FOLLOWUP_EVENT"
    OTHER = "OTHER"


class ResolutionStatus(StrEnum):
    RESOLVED_ONE = "RESOLVED_ONE"
    RESOLVED_MANY = "RESOLVED_MANY"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    INVALID = "INVALID"


class PropositionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    INVALID = "INVALID"


class TriggerType(StrEnum):
    STIMULUS = "STIMULUS"
    HEARTBEAT = "HEARTBEAT"


class ActivationReason(StrEnum):
    STIMULUS_THRESHOLD_MET = "STIMULUS_THRESHOLD_MET"
    MONTHLY_HEARTBEAT = "MONTHLY_HEARTBEAT"


class ActivationDecisionReason(StrEnum):
    ACCEPTED = "ACCEPTED"
    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    DEFERRED_PERSON_CAP = "DEFERRED_PERSON_CAP"
    DEFERRED_GLOBAL_CAP = "DEFERRED_GLOBAL_CAP"
    INACTIVE_PERSON = "INACTIVE_PERSON"
    NO_EXPOSURE = "NO_EXPOSURE"
    UNRESOLVED_NOT_ALLOWED = "UNRESOLVED_NOT_ALLOWED"


class CoverageReason(StrEnum):
    EVENT_ACTIVATION = "EVENT_ACTIVATION"
    PRIOR_CYCLE_IN_MONTH = "PRIOR_CYCLE_IN_MONTH"
    HEARTBEAT_SCHEDULED = "HEARTBEAT_SCHEDULED"
    PERSON_DISABLED = "PERSON_DISABLED"


class IdentifierHint(ContractModel):
    id_type: StrictStr = Field(min_length=1, max_length=64)
    id_value: StrictStr = Field(min_length=1, max_length=256)
    mic: StrictStr | None = Field(default=None, min_length=4, max_length=4)
    exchange_code: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    currency: StrictStr | None = Field(default=None, min_length=3, max_length=3)


class UnderlyingCandidate(ContractModel):
    underlying_id: StrictStr = Field(pattern=ID_PATTERN)
    weight: StrictFloat = Field(gt=0.0, le=1.0)
    mic: StrictStr | None = Field(default=None, min_length=4, max_length=4)
    security_type: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    identifiers: tuple[IdentifierHint, ...] = ()


class StimulusPanelRecord(ContractModel):
    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    origin_type: StimulusOrigin
    origin_types: tuple[StimulusOrigin, ...] = Field(min_length=1)
    merged_stimulus_ids: tuple[StrictStr, ...] = Field(min_length=1)
    source_event_id: StrictStr = Field(pattern=ID_PATTERN)
    causal_parent_ids: tuple[StrictStr, ...] = ()
    created_cycle_ids: tuple[StrictStr, ...] = Field(min_length=1)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    event_time: datetime
    available_at: datetime
    expires_at: datetime | None = None
    subject: StrictStr = Field(min_length=1, max_length=4096)
    stimulus_type: StimulusType
    intensity: StrictFloat = Field(ge=0.0, le=1.0)
    salience: StrictFloat = Field(ge=0.0, le=1.0)
    priority: StrictInt = Field(ge=0, le=100)
    resolution_status: ResolutionStatus
    underlying_candidates: tuple[UnderlyingCandidate, ...] = ()
    selected_underlying_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    proposition_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    horizon: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    proposition_status: PropositionStatus
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    evidence_refs: tuple[StrictStr, ...] = Field(min_length=1)
    lineage_ids: tuple[StrictStr, ...] = Field(min_length=1)
    dedup_key: StrictStr = Field(pattern=SHA256_PATTERN)
    warnings: tuple[StrictStr, ...] = ()

    _event_time_utc = field_validator("event_time")(aware_utc)
    _available_at_utc = field_validator("available_at")(aware_utc)

    @field_validator("expires_at")
    @classmethod
    def normalize_expires(cls, value: datetime | None) -> datetime | None:
        return aware_utc(value) if value is not None else None


class PanelDecisionReason(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE_COLLAPSED = "DUPLICATE_COLLAPSED"
    DEFERRED_TOTAL_BUDGET = "DEFERRED_TOTAL_BUDGET"
    DEFERRED_ORIGIN_BUDGET = "DEFERRED_ORIGIN_BUDGET"
    DEFERRED_UNRESOLVED_BUDGET = "DEFERRED_UNRESOLVED_BUDGET"


class PanelAdmissionDecision(ContractModel):
    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    reason: PanelDecisionReason
    detail: StrictStr
    dedup_key: StrictStr = Field(pattern=SHA256_PATTERN)


class EventBusMetrics(ContractModel):
    external_input_count: StrictInt = Field(ge=0)
    endogenous_input_count: StrictInt = Field(ge=0)
    accepted_count: StrictInt = Field(ge=0)
    duplicate_collapsed_count: StrictInt = Field(ge=0)
    deferred_total_budget_count: StrictInt = Field(ge=0)
    deferred_origin_budget_count: StrictInt = Field(ge=0)
    deferred_unresolved_budget_count: StrictInt = Field(ge=0)
    unresolved_accepted_count: StrictInt = Field(ge=0)
    warning_count: StrictInt = Field(ge=0)


class StimulusPanelInput(ContractModel):
    schema_version: Literal["stimulus_panel.v2"]
    contract_version: Literal["p3.s18.v1"]
    bus_id: StrictStr = Field(pattern=ID_PATTERN)
    dedup_key_version: Literal["stimulus_dedup_v1"]
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    records: tuple[StimulusPanelRecord, ...]
    admission_decisions: tuple[PanelAdmissionDecision, ...]
    source_lineage_ids: tuple[StrictStr, ...] = Field(min_length=2)
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus
    warnings: tuple[StrictStr, ...] = ()
    metrics: EventBusMetrics

    _as_of_utc = field_validator("as_of")(aware_utc)


class ScoreOverride(ContractModel):
    key: StrictStr = Field(pattern=ID_PATTERN)
    score: StrictFloat = Field(ge=0.0, le=1.0)


class StimulusTypeScore(ContractModel):
    stimulus_type: StimulusType
    score: StrictFloat = Field(ge=0.0, le=1.0)


class OriginScore(ContractModel):
    origin_type: StimulusOrigin
    score: StrictFloat = Field(ge=0.0, le=1.0)


class PersonActivationProfile(ContractModel):
    activation_threshold: StrictFloat = Field(ge=0.0, le=1.0)
    default_relevance: StrictFloat = Field(ge=0.0, le=1.0)
    underlying_relevance: tuple[ScoreOverride, ...] = ()
    proposition_relevance: tuple[ScoreOverride, ...] = ()
    horizon_relevance: tuple[ScoreOverride, ...] = ()
    default_tag_sensitivity: StrictFloat = Field(ge=0.0, le=1.0)
    stimulus_type_sensitivity: tuple[StimulusTypeScore, ...] = ()
    default_exposure: StrictFloat = Field(ge=0.0, le=1.0)
    origin_exposure: tuple[OriginScore, ...] = ()

    @model_validator(mode="after")
    def keys_are_unique(self) -> Self:
        collections = [
            ("underlying_relevance", [item.key for item in self.underlying_relevance]),
            ("proposition_relevance", [item.key for item in self.proposition_relevance]),
            ("horizon_relevance", [item.key for item in self.horizon_relevance]),
            (
                "stimulus_type_sensitivity",
                [item.stimulus_type for item in self.stimulus_type_sensitivity],
            ),
            ("origin_exposure", [item.origin_type for item in self.origin_exposure]),
        ]
        for name, keys in collections:
            if len(keys) != len(set(keys)):
                raise ValueError(f"{name} keys must be unique")
        return self


class PersonSeedRecord(ContractModel):
    person_id: StrictStr = Field(pattern=ID_PATTERN)
    person_seed: StrictInt = Field(ge=0)
    role_id: StrictStr = Field(pattern=ID_PATTERN)
    representation_weight: StrictFloat = Field(gt=0.0, le=1.0)
    activation_profile: PersonActivationProfile
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)


class PersonSeedPanelInput(ContractModel):
    schema_version: Literal["person_seed_panel.s19.input.v1"]
    contract_version: Literal["p3.s7.v1"]
    population_id: StrictStr = Field(pattern=ID_PATTERN)
    records: tuple[PersonSeedRecord, ...] = Field(min_length=1)
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus

    @model_validator(mode="after")
    def people_are_unique(self) -> Self:
        ids = [item.person_id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("person_seed_panel person_id values must be unique")
        return self


class AttentionOverride(ContractModel):
    key: StrictStr = Field(pattern=ID_PATTERN)
    score: StrictFloat = Field(ge=0.0, le=1.0)


class PersonStateRecord(ContractModel):
    person_id: StrictStr = Field(pattern=ID_PATTERN)
    state_as_of: datetime
    is_active: StrictBool
    current_attention: StrictFloat = Field(ge=0.0, le=1.0)
    underlying_attention: tuple[AttentionOverride, ...] = ()
    proposition_attention: tuple[AttentionOverride, ...] = ()
    last_cognitive_cycle_at: datetime | None = None
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)

    _state_as_of_utc = field_validator("state_as_of")(aware_utc)

    @field_validator("last_cognitive_cycle_at")
    @classmethod
    def normalize_last_cycle(cls, value: datetime | None) -> datetime | None:
        return aware_utc(value) if value is not None else None

    @model_validator(mode="after")
    def attention_keys_are_unique(self) -> Self:
        for name, items in [
            ("underlying_attention", self.underlying_attention),
            ("proposition_attention", self.proposition_attention),
        ]:
            keys = [item.key for item in items]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{name} keys must be unique")
        return self


class CurrentPersonStatePanelInput(ContractModel):
    schema_version: Literal["current_person_state_panel.s19.input.v1"]
    contract_version: Literal["p3.s11.v1"]
    population_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    records: tuple[PersonStateRecord, ...] = Field(min_length=1)
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus

    _as_of_utc = field_validator("as_of")(aware_utc)

    @model_validator(mode="after")
    def people_are_unique_and_pit_safe(self) -> Self:
        ids = [item.person_id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("current state person_id values must be unique")
        if any(item.state_as_of > self.as_of for item in self.records):
            raise ValueError("person state cannot be newer than panel as_of")
        return self


class PopulationMember(ContractModel):
    person_id: StrictStr = Field(pattern=ID_PATTERN)
    representation_weight: StrictFloat = Field(gt=0.0, le=1.0)
    enabled: StrictBool = True


class ValidatedPopulationManifestInput(ContractModel):
    schema_version: Literal["validated_population_manifest.s19.input.v1"]
    contract_version: Literal["p3.s7.v1"]
    population_id: StrictStr = Field(pattern=ID_PATTERN)
    people: tuple[PopulationMember, ...] = Field(min_length=1)
    artifact_hashes: dict[StrictStr, StrictStr]
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus

    @model_validator(mode="after")
    def population_is_consistent(self) -> Self:
        ids = [item.person_id for item in self.people]
        if len(ids) != len(set(ids)):
            raise ValueError("population person_id values must be unique")
        total = sum(item.representation_weight for item in self.people)
        if not 0.999999999 <= total <= 1.000000001:
            raise ValueError("representation weights must sum to one")
        return self


class GlobalActivationCap(ContractModel):
    population_fraction: StrictFloat = Field(gt=0.0, le=1.0)
    absolute_cap: StrictInt = Field(ge=1, le=100_000)
    minimum_if_candidates: StrictInt = Field(ge=1, le=100_000)

    @model_validator(mode="after")
    def minimum_does_not_exceed_absolute(self) -> Self:
        if self.minimum_if_candidates > self.absolute_cap:
            raise ValueError("minimum_if_candidates cannot exceed absolute_cap")
        return self


class ActivationConfig(ContractModel):
    schema_version: Literal["activation_config.v2"]
    config_version: Literal["p3.s19.activation.v1"]
    formula_id: Literal["multiplicative_activation_v1"]
    formula: Literal[
        "stimulus_intensity * relevance * tag_sensitivity * current_attention * exposure"
    ]
    threshold_comparison: Literal["GREATER_THAN_OR_EQUAL"]
    relevance_policy: Literal["MAX_MATCH_FALLBACK_DEFAULT"]
    attention_policy: Literal["MAX_MATCH_FALLBACK_CURRENT"]
    unresolved_stimulus_policy: Literal["ALLOW_WITH_PROFILE_DEFAULT", "SKIP_WITH_AUDIT"]
    max_extra_activations_per_person_per_cycle: StrictInt = Field(ge=1, le=10)
    global_cap: GlobalActivationCap
    candidate_sort_policy: Literal[
        "SCORE_DESC_PRIORITY_DESC_AVAILABLE_ASC_SEEDED_SHA256"
    ]
    tie_break_policy: Literal["SEEDED_SHA256_V1"]
    require_positive_exposure: Literal[True] = True
    verify_input_content_hashes: StrictBool = True


class HeartbeatConfig(ContractModel):
    schema_version: Literal["heartbeat_config.v2"]
    config_version: Literal["p3.s19.heartbeat.v1"]
    coverage_period: Literal["CALENDAR_MONTH_UTC"]
    minimum_cycles_per_person_per_calendar_month: Literal[1]
    event_activation_satisfies_heartbeat: Literal[True]
    schedule_policy: Literal[
        "EVENT_FIRST_PRIORITY_SCORE_SEEDED_SHA256_HEARTBEAT_PERSON"
    ]
    heartbeat_priority: StrictInt = Field(ge=0, le=100)
    heartbeat_seed_namespace: StrictStr = Field(pattern=ID_PATTERN)
    heartbeat_schedule_offset_seconds: Literal[0]
    include_disabled_people: Literal[False] = False
    verify_input_content_hashes: StrictBool = True


class ActivationComponents(ContractModel):
    stimulus_intensity: StrictFloat = Field(ge=0.0, le=1.0)
    relevance: StrictFloat = Field(ge=0.0, le=1.0)
    tag_sensitivity: StrictFloat = Field(ge=0.0, le=1.0)
    current_attention: StrictFloat = Field(ge=0.0, le=1.0)
    exposure: StrictFloat = Field(ge=0.0, le=1.0)


class ActivationRecord(ContractModel):
    activation_id: StrictStr = Field(pattern=ID_PATTERN)
    person_id: StrictStr = Field(pattern=ID_PATTERN)
    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    trigger_type: Literal[TriggerType.STIMULUS]
    activation_reason: Literal[ActivationReason.STIMULUS_THRESHOLD_MET]
    activation_score: StrictFloat = Field(ge=0.0, le=1.0)
    threshold: StrictFloat = Field(ge=0.0, le=1.0)
    components: ActivationComponents
    stimulus_priority: StrictInt = Field(ge=0, le=100)
    stimulus_available_at: datetime
    underlying_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    proposition_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    horizon: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    seed: StrictInt = Field(ge=0)
    tie_break_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    source_lineage_ids: tuple[StrictStr, ...] = Field(min_length=2)

    _available_at_utc = field_validator("stimulus_available_at")(aware_utc)


class ActivationDecision(ContractModel):
    person_id: StrictStr = Field(pattern=ID_PATTERN)
    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    activation_id: StrictStr = Field(pattern=ID_PATTERN)
    reason: ActivationDecisionReason
    detail: StrictStr
    activation_score: StrictFloat = Field(ge=0.0, le=1.0)
    threshold: StrictFloat = Field(ge=0.0, le=1.0)
    tie_break_hash: StrictStr = Field(pattern=SHA256_PATTERN)


class ActivationMetrics(ContractModel):
    stimulus_count: StrictInt = Field(ge=0)
    active_person_count: StrictInt = Field(ge=0)
    candidate_count: StrictInt = Field(ge=0)
    accepted_count: StrictInt = Field(ge=0)
    below_threshold_count: StrictInt = Field(ge=0)
    deferred_person_cap_count: StrictInt = Field(ge=0)
    deferred_global_cap_count: StrictInt = Field(ge=0)
    inactive_person_count: StrictInt = Field(ge=0)
    no_exposure_count: StrictInt = Field(ge=0)
    unresolved_skipped_count: StrictInt = Field(ge=0)
    global_cap_applied: StrictInt = Field(ge=0)
    warning_count: StrictInt = Field(ge=0)


class ActivationPanel(ContractModel):
    schema_version: Literal["activation_panel.v2"]
    contract_version: Literal["p3.s19.v1"]
    formula_id: Literal["multiplicative_activation_v1"]
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    population_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    records: tuple[ActivationRecord, ...]
    decisions: tuple[ActivationDecision, ...]
    source_lineage_ids: tuple[StrictStr, ...] = Field(min_length=3)
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus
    warnings: tuple[StrictStr, ...] = ()
    metrics: ActivationMetrics

    _as_of_utc = field_validator("as_of")(aware_utc)


class ScheduleStep(ContractModel):
    schedule_step_id: StrictStr = Field(pattern=ID_PATTERN)
    sequence_index: StrictInt = Field(ge=0)
    person_id: StrictStr = Field(pattern=ID_PATTERN)
    trigger_type: TriggerType
    activation_reason: ActivationReason
    activation_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    stimulus_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    heartbeat_period: StrictStr | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}$")
    priority: StrictInt = Field(ge=0, le=100)
    activation_score: StrictFloat | None = Field(default=None, ge=0.0, le=1.0)
    scheduled_at: datetime
    seed: StrictInt = Field(ge=0)
    tie_break_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    source_lineage_ids: tuple[StrictStr, ...] = Field(min_length=1)

    _scheduled_at_utc = field_validator("scheduled_at")(aware_utc)

    @model_validator(mode="after")
    def trigger_fields_are_consistent(self) -> Self:
        if self.trigger_type is TriggerType.STIMULUS:
            if self.activation_id is None or self.stimulus_id is None:
                raise ValueError("stimulus steps require activation_id and stimulus_id")
            if self.heartbeat_period is not None:
                raise ValueError("stimulus steps cannot have heartbeat_period")
        else:
            if self.activation_id is not None or self.stimulus_id is not None:
                raise ValueError("heartbeat steps cannot reference activation or stimulus")
            if self.heartbeat_period is None:
                raise ValueError("heartbeat steps require heartbeat_period")
        return self


class CoverageRecord(ContractModel):
    person_id: StrictStr = Field(pattern=ID_PATTERN)
    period: StrictStr = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    covered: StrictBool
    reason: CoverageReason
    last_cognitive_cycle_at: datetime | None = None
    schedule_step_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)

    @field_validator("last_cognitive_cycle_at")
    @classmethod
    def normalize_last_cycle(cls, value: datetime | None) -> datetime | None:
        return aware_utc(value) if value is not None else None


class ScheduleMetrics(ContractModel):
    population_count: StrictInt = Field(ge=0)
    enabled_population_count: StrictInt = Field(ge=0)
    event_step_count: StrictInt = Field(ge=0)
    heartbeat_step_count: StrictInt = Field(ge=0)
    prior_month_covered_count: StrictInt = Field(ge=0)
    disabled_count: StrictInt = Field(ge=0)
    total_step_count: StrictInt = Field(ge=0)
    warning_count: StrictInt = Field(ge=0)


class CognitiveCycleSchedule(ContractModel):
    schema_version: Literal["cognitive_cycle_schedule.v2"]
    contract_version: Literal["p3.s19.v1"]
    schedule_policy: Literal[
        "EVENT_FIRST_PRIORITY_SCORE_SEEDED_SHA256_HEARTBEAT_PERSON"
    ]
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    population_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    coverage_period: StrictStr = Field(pattern=r"^[0-9]{4}-[0-9]{2}$")
    steps: tuple[ScheduleStep, ...]
    coverage: tuple[CoverageRecord, ...] = Field(min_length=1)
    source_lineage_ids: tuple[StrictStr, ...] = Field(min_length=3)
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus
    warnings: tuple[StrictStr, ...] = ()
    metrics: ScheduleMetrics

    _as_of_utc = field_validator("as_of")(aware_utc)


class SubphaseS19Result(ContractModel):
    activation_panel: ActivationPanel
    cognitive_cycle_schedule: CognitiveCycleSchedule
