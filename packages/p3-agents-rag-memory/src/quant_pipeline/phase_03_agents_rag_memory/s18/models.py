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
    """Strict immutable model used at every S18 boundary."""

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


ENDOGENOUS_ORIGINS = {
    StimulusOrigin.TOOL_DISCOVERY,
    StimulusOrigin.SOCIAL_DELIVERY,
    StimulusOrigin.MEMORY_TRIGGER,
    StimulusOrigin.ATTENTION_FOLLOWUP,
}


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


class QueueDecisionReason(StrEnum):
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"
    DUPLICATE_COLLAPSED = "DUPLICATE_COLLAPSED"


class PanelDecisionReason(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE_COLLAPSED = "DUPLICATE_COLLAPSED"
    DEFERRED_TOTAL_BUDGET = "DEFERRED_TOTAL_BUDGET"
    DEFERRED_ORIGIN_BUDGET = "DEFERRED_ORIGIN_BUDGET"
    DEFERRED_UNRESOLVED_BUDGET = "DEFERRED_UNRESOLVED_BUDGET"


class IdentifierHint(ContractModel):
    id_type: StrictStr = Field(min_length=1, max_length=64)
    id_value: StrictStr = Field(min_length=1, max_length=256)
    mic: StrictStr | None = Field(default=None, min_length=4, max_length=4)
    exchange_code: StrictStr | None = Field(default=None, min_length=1, max_length=32)
    currency: StrictStr | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("id_type")
    @classmethod
    def normalize_id_type(cls, value: str) -> str:
        return value.upper()

    @field_validator("mic", "currency")
    @classmethod
    def normalize_upper_optional(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class SalienceFeatures(ContractModel):
    source_quality: StrictFloat = Field(ge=0.0, le=1.0)
    novelty: StrictFloat = Field(ge=0.0, le=1.0)
    subject_relevance: StrictFloat = Field(ge=0.0, le=1.0)
    event_severity: StrictFloat = Field(ge=0.0, le=1.0)
    information_specificity: StrictFloat = Field(ge=0.0, le=1.0)


class UnderlyingCandidate(ContractModel):
    underlying_id: StrictStr = Field(pattern=ID_PATTERN)
    weight: StrictFloat = Field(gt=0.0, le=1.0)
    mic: StrictStr | None = Field(default=None, min_length=4, max_length=4)
    security_type: StrictStr | None = Field(default=None, min_length=1, max_length=128)
    identifiers: tuple[IdentifierHint, ...] = ()


class Phase3RunSnapshot(ContractModel):
    schema_version: StrictStr
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    snapshot_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    seed: StrictInt = Field(ge=0)
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)

    _as_of_utc = field_validator("as_of")(aware_utc)


class ResolvedExternalStimulusRecord(ContractModel):
    """Consumer-owned boundary model matching the S17 output contract."""

    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    origin_type: Literal[StimulusOrigin.EXTERNAL_PIT_CONTEXT]
    record_id: StrictStr = Field(pattern=ID_PATTERN)
    record_type: StrictStr
    source_event_id: StrictStr = Field(pattern=ID_PATTERN)
    causal_parent_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    created_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    event_time: datetime
    available_at: datetime
    subject: StrictStr = Field(min_length=1, max_length=4096)
    stimulus_type: StimulusType
    intensity: StrictFloat = Field(ge=0.0, le=1.0)
    salience: StrictFloat = Field(ge=0.0, le=1.0)
    salience_features: SalienceFeatures
    salience_formula_id: StrictStr = Field(pattern=ID_PATTERN)
    defaulted_components: tuple[StrictStr, ...] = ()
    entity_ids: tuple[StrictStr, ...] = ()
    identifier_hints: tuple[IdentifierHint, ...] = ()
    proposition_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    horizon: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    evidence_refs: tuple[StrictStr, ...] = Field(min_length=1)
    graph_evidence_refs: tuple[StrictStr, ...] = ()
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    resolution_status: ResolutionStatus
    mapping_version: StrictStr
    resolution_method: StrictStr = Field(min_length=1, max_length=128)
    underlying_candidates: tuple[UnderlyingCandidate, ...] = ()
    selected_underlying_id: StrictStr | None = Field(default=None, pattern=ID_PATTERN)
    proposition_status: PropositionStatus
    warnings: tuple[StrictStr, ...] = ()

    _event_time_utc = field_validator("event_time")(aware_utc)
    _available_at_utc = field_validator("available_at")(aware_utc)


class InputStreamMetrics(ContractModel):
    input_record_count: StrictInt = Field(ge=0)
    output_record_count: StrictInt = Field(ge=0)
    warning_count: StrictInt = Field(ge=0)
    defaulted_component_count: StrictInt = Field(default=0, ge=0)
    unresolved_count: StrictInt = Field(default=0, ge=0)
    ambiguous_count: StrictInt = Field(default=0, ge=0)


class ResolvedExternalStimulusStreamInput(ContractModel):
    schema_version: Literal["resolved_external_stimulus_stream.v2"]
    contract_version: Literal["p3.s17.v1"]
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    items: tuple[ResolvedExternalStimulusRecord, ...]
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus
    warnings: tuple[StrictStr, ...] = ()
    metrics: InputStreamMetrics

    _as_of_utc = field_validator("as_of")(aware_utc)


class EndogenousStimulusRecord(ContractModel):
    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    origin_type: StimulusOrigin
    source_event_id: StrictStr = Field(pattern=ID_PATTERN)
    causal_parent_id: StrictStr = Field(pattern=ID_PATTERN)
    created_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    event_time: datetime
    available_at: datetime
    expires_at: datetime
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
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    warnings: tuple[StrictStr, ...] = ()

    _event_time_utc = field_validator("event_time")(aware_utc)
    _available_at_utc = field_validator("available_at")(aware_utc)
    _expires_at_utc = field_validator("expires_at")(aware_utc)

    @model_validator(mode="after")
    def validate_endogenous_shape(self) -> Self:
        if self.origin_type not in ENDOGENOUS_ORIGINS:
            raise ValueError("endogenous queue cannot contain external stimuli")
        if self.event_time > self.available_at:
            raise ValueError("event_time cannot be after available_at")
        if self.expires_at < self.available_at:
            raise ValueError("expires_at cannot precede available_at")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        return self


class QueueInputMetrics(ContractModel):
    generated_count: StrictInt = Field(ge=0)
    warning_count: StrictInt = Field(default=0, ge=0)


class PriorCycleEndogenousStimulusQueue(ContractModel):
    schema_version: Literal["next_cycle_endogenous_stimulus_queue.v2"]
    contract_version: Literal["p3.s26.v1"]
    queue_id: StrictStr = Field(pattern=ID_PATTERN)
    source_run_id: StrictStr = Field(pattern=ID_PATTERN)
    source_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    created_at: datetime
    items: tuple[EndogenousStimulusRecord, ...]
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus
    warnings: tuple[StrictStr, ...] = ()
    metrics: QueueInputMetrics

    _created_at_utc = field_validator("created_at")(aware_utc)

    @model_validator(mode="after")
    def validate_status_shape(self) -> Self:
        if self.status is ExecutionStatus.READY_EMPTY and self.items:
            raise ValueError("READY_EMPTY queue cannot contain items")
        if self.metrics.generated_count != len(self.items):
            raise ValueError("generated_count must equal item count")
        return self


class AdmissionPolicy(ContractModel):
    max_total_stimuli_per_cycle: StrictInt = Field(ge=1, le=100_000)
    max_external_stimuli_per_cycle: StrictInt = Field(ge=0, le=100_000)
    max_endogenous_stimuli_per_cycle: StrictInt = Field(ge=0, le=100_000)
    max_unresolved_stimuli_per_cycle: StrictInt = Field(ge=0, le=100_000)
    preserve_deferred_decisions: Literal[True] = True

    @model_validator(mode="after")
    def capacities_are_consistent(self) -> Self:
        if self.max_external_stimuli_per_cycle > self.max_total_stimuli_per_cycle:
            raise ValueError("external cap cannot exceed total cap")
        if self.max_endogenous_stimuli_per_cycle > self.max_total_stimuli_per_cycle:
            raise ValueError("endogenous cap cannot exceed total cap")
        if self.max_unresolved_stimuli_per_cycle > self.max_total_stimuli_per_cycle:
            raise ValueError("unresolved cap cannot exceed total cap")
        return self


class StimulusBusConfig(ContractModel):
    schema_version: Literal["stimulus_event_bus_config.v2"]
    config_version: Literal["p3.s18.config.v1"]
    bus_id: StrictStr = Field(pattern=ID_PATTERN)
    same_cycle_policy: Literal["EXTERNAL_ONLY_CURRENT_ENDOGENOUS_NEXT"]
    dedup_key_version: Literal["stimulus_dedup_v1"]
    deduplication_fields: tuple[
        Literal["source_event_id", "subject", "available_at", "content_hash"], ...
    ] = Field(min_length=4, max_length=4)
    origin_precedence: dict[StimulusOrigin, StrictInt]
    admission_policy: AdmissionPolicy
    external_priority_formula: Literal["SALIENCE_PERCENT_V1"]
    expired_item_policy: Literal["DROP_WITH_AUDIT"]
    duplicate_policy: Literal["COLLAPSE_EXACT_FAIL_CONFLICT"]
    unresolved_policy: Literal["ALLOW_WITH_FLAG"]
    sort_policy: Literal[
        "PRIORITY_DESC_SALIENCE_DESC_AVAILABLE_ASC_ORIGIN_STIMULUS_ID"
    ]
    allow_same_cycle_endogenous: Literal[False] = False
    verify_input_content_hashes: StrictBool = True

    @model_validator(mode="after")
    def validate_config(self) -> Self:
        expected_fields = (
            "source_event_id",
            "subject",
            "available_at",
            "content_hash",
        )
        if self.deduplication_fields != expected_fields:
            raise ValueError("deduplication_fields order is part of stimulus_dedup_v1")
        missing = set(StimulusOrigin) - set(self.origin_precedence)
        if missing:
            raise ValueError(
                "origin_precedence must cover every origin: "
                + ",".join(sorted(item.value for item in missing))
            )
        if len(set(self.origin_precedence.values())) != len(self.origin_precedence):
            raise ValueError("origin precedence values must be unique")
        return self


class QueueAdmissionDecision(ContractModel):
    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    reason: QueueDecisionReason
    detail: StrictStr


class QueueConsumptionRecord(ContractModel):
    """Immutable audit record proving that a prior-cycle item was consumed once."""

    queue_id: StrictStr = Field(pattern=ID_PATTERN)
    stimulus_id: StrictStr = Field(pattern=ID_PATTERN)
    produced_in_cycle: StrictStr = Field(pattern=ID_PATTERN)
    available_from_cycle: StrictStr = Field(pattern=ID_PATTERN)
    consumed_in_cycle: StrictStr = Field(pattern=ID_PATTERN)
    consumer_run_id: StrictStr = Field(pattern=ID_PATTERN)
    decision: QueueDecisionReason
    consumption_id: StrictStr = Field(pattern=ID_PATTERN)


class QueueLoaderMetrics(ContractModel):
    input_record_count: StrictInt = Field(ge=0)
    output_record_count: StrictInt = Field(ge=0)
    expired_count: StrictInt = Field(ge=0)
    duplicate_collapsed_count: StrictInt = Field(ge=0)
    warning_count: StrictInt = Field(ge=0)


class EndogenousStimulusStream(ContractModel):
    schema_version: Literal["endogenous_stimulus_stream.v2"]
    contract_version: Literal["p3.s18.v1"]
    run_id: StrictStr = Field(pattern=ID_PATTERN)
    cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    target_cycle_id: StrictStr = Field(pattern=ID_PATTERN)
    as_of: datetime
    items: tuple[EndogenousStimulusRecord, ...]
    admission_decisions: tuple[QueueAdmissionDecision, ...]
    consumption_ledger: tuple[QueueConsumptionRecord, ...] = ()
    lineage_id: StrictStr = Field(pattern=ID_PATTERN)
    content_hash: StrictStr = Field(pattern=SHA256_PATTERN)
    status: ExecutionStatus
    warnings: tuple[StrictStr, ...] = ()
    metrics: QueueLoaderMetrics

    _as_of_utc = field_validator("as_of")(aware_utc)


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
    def optional_expires_utc(cls, value: datetime | None) -> datetime | None:
        return aware_utc(value) if value is not None else None


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


class StimulusPanel(ContractModel):
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


class SubphaseS18Result(ContractModel):
    endogenous_stimulus_stream: EndogenousStimulusStream
    stimulus_panel: StimulusPanel
