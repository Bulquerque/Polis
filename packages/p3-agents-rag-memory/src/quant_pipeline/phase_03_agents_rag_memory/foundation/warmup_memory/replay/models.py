from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

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

Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]
UnitFloat = Annotated[StrictFloat, Field(ge=0.0, le=1.0)]
SignedUnitFloat = Annotated[StrictFloat, Field(ge=-1.0, le=1.0)]


class FrozenContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


def parse_datetime(value: object) -> object:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return value
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return value


def aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value.astimezone(UTC)


class WarmupMode(StrEnum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    GENESIS_ONLY = "GENESIS_ONLY"


class ReplayInvocationMode(StrEnum):
    GENESIS_ONLY = "GENESIS_ONLY"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    RESUME_REPLAY = "RESUME_REPLAY"


class ArtifactStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ScheduleItemKind(StrEnum):
    EVENT_RELEASE = "EVENT_RELEASE"
    HEARTBEAT_OBLIGATION = "HEARTBEAT_OBLIGATION"


class CheckpointReason(StrEnum):
    MONTHLY_BOUNDARY = "MONTHLY_BOUNDARY"
    FINAL_REPLAY_BOUNDARY = "FINAL_REPLAY_BOUNDARY"
    GENESIS = "GENESIS"


class StateSource(StrEnum):
    GENESIS = "GENESIS"
    WARMUP_CHECKPOINT = "WARMUP_CHECKPOINT"
    PRIOR_CYCLE = "PRIOR_CYCLE"


class PersonDynamicStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class MemoryType(StrEnum):
    EPISODIC = "EPISODIC"
    SEMANTIC = "SEMANTIC"
    PROCEDURAL = "PROCEDURAL"
    SOCIAL = "SOCIAL"


class VisibilityScope(StrEnum):
    SELF = "SELF"
    SOCIAL_VISIBLE = "SOCIAL_VISIBLE"
    PUBLIC = "PUBLIC"
    AUDIT_ONLY = "AUDIT_ONLY"


class KernelExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class ArtifactRef(FrozenContractModel):
    artifact_id: NonEmptyStr
    artifact_type: NonEmptyStr
    content_hash: Sha256
    schema_id: NonEmptyStr | None = None
    schema_version: NonEmptyStr | None = None


class StateLineage(FrozenContractModel):
    lineage_id: NonEmptyStr
    source_artifact_ids: tuple[NonEmptyStr, ...]
    source_lineage_ids: tuple[NonEmptyStr, ...]
    parent_state_hash: Sha256 | None = None
    holdout_refs: tuple[NonEmptyStr, ...] = ()


class EventReference(FrozenContractModel):
    history_record_id: NonEmptyStr
    event_id: NonEmptyStr
    source_id: NonEmptyStr
    payload_ref: ArtifactRef
    underlyings: tuple[NonEmptyStr, ...] = ()
    propositions: tuple[NonEmptyStr, ...] = ()


class WarmupScheduleItem(FrozenContractModel):
    schedule_item_id: NonEmptyStr
    sequence_number: PositiveInt
    logical_time: datetime
    kind: ScheduleItemKind
    priority: NonNegativeInt
    deduplication_key: NonEmptyStr
    event_ref: EventReference | None = None
    person_id: NonEmptyStr | None = None
    heartbeat_period: NonEmptyStr | None = None
    source_lineage_ids: tuple[NonEmptyStr, ...]

    _parse_dt = field_validator("logical_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("logical_time")(aware_utc)

    @model_validator(mode="after")
    def validate_discriminator(self) -> "WarmupScheduleItem":
        if self.kind is ScheduleItemKind.EVENT_RELEASE:
            if self.event_ref is None or self.person_id is not None or self.heartbeat_period is not None:
                raise ValueError("EVENT_RELEASE requires event_ref only")
        else:
            if self.event_ref is not None or self.person_id is None or self.heartbeat_period is None:
                raise ValueError("HEARTBEAT_OBLIGATION requires person_id and heartbeat_period")
        return self


class WarmupEventScheduleView(FrozenContractModel):
    schema_id: Literal["warmup_event_schedule.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S10.M01"]
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: datetime
    evaluation_start: datetime
    mode: WarmupMode
    status: ArtifactStatus
    schedule_start: datetime | None
    schedule_end: datetime | None
    items: tuple[WarmupScheduleItem, ...]
    schedule_hash: Sha256
    activation_config_hash: Sha256
    heartbeat_config_hash: Sha256
    lineage: dict[str, object]
    summary: dict[str, object]
    issues: tuple[dict[str, object], ...] = ()

    _parse_dt = field_validator("as_of", "evaluation_start", "schedule_start", "schedule_end", mode="before")(parse_datetime)
    _utc_dt = field_validator("as_of", "evaluation_start", "schedule_start", "schedule_end")(aware_utc)


class PlannedCheckpoint(FrozenContractModel):
    checkpoint_id: NonEmptyStr
    sequence_number: PositiveInt
    after_schedule_sequence_number: NonNegativeInt
    logical_time: datetime
    reason: CheckpointReason
    previous_checkpoint_id: NonEmptyStr | None
    required_state_families: tuple[NonEmptyStr, ...]
    final: StrictBool

    _parse_dt = field_validator("logical_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("logical_time")(aware_utc)


class WarmupCheckpointPlanView(FrozenContractModel):
    schema_id: Literal["warmup_checkpoint_plan.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S10.M02"]
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: datetime
    evaluation_start: datetime
    mode: WarmupMode
    status: ArtifactStatus
    schedule_hash: Sha256
    checkpoint_config_hash: Sha256
    checkpoints: tuple[PlannedCheckpoint, ...]
    final_checkpoint_id: NonEmptyStr
    final_checkpoint_time: datetime
    resume_supported: StrictBool
    plan_hash: Sha256
    lineage: dict[str, object]
    issues: tuple[dict[str, object], ...] = ()

    _parse_dt = field_validator("as_of", "evaluation_start", "final_checkpoint_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("as_of", "evaluation_start", "final_checkpoint_time")(aware_utc)


class PersonSeed(FrozenContractModel):
    person_id: NonEmptyStr
    representation_weight: UnitFloat
    deterministic_seed: Annotated[StrictInt, Field(ge=0)]
    structural_profile_hash: Sha256


class PersonSeedPanelView(FrozenContractModel):
    schema_id: Literal["person_seed_panel.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    population_hash: Sha256
    persons: tuple[PersonSeed, ...]
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_people(self) -> "PersonSeedPanelView":
        ids = [item.person_id for item in self.persons]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("person_seed_panel requires unique, non-empty persons")
        if abs(sum(item.representation_weight for item in self.persons) - 1.0) > 1e-9:
            raise ValueError("representation weights must sum to 1")
        return self


class InitialSocialEdge(FrozenContractModel):
    """Initial edge projected from the population foundation without losing social semantics."""

    edge_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    trust: UnitFloat
    strength: UnitFloat
    influence: UnitFloat
    interaction_frequency: UnitFloat
    selection_probability: UnitFloat
    domain_trust: dict[NonEmptyStr, UnitFloat]
    origin: NonEmptyStr


class InitialSocialGraphView(FrozenContractModel):
    schema_id: Literal["validated_initial_social_graph.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    population_hash: Sha256
    graph_hash: Sha256
    records: tuple[InitialSocialEdge, ...]
    lineage_id: NonEmptyStr


class RetroPolicyPatchView(FrozenContractModel):
    schema_id: Literal["active_retro_policy_patch.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    status: Literal["NO_PATCH", "VALID_PATCH"]
    patch_hash: Sha256
    effective_from: datetime | None = None
    prompt_policy_ref: ArtifactRef | None = None
    retrieval_policy_ref: ArtifactRef | None = None
    tool_policy_ref: ArtifactRef | None = None
    lineage_id: NonEmptyStr

    _parse_dt = field_validator("effective_from", mode="before")(parse_datetime)
    _utc_dt = field_validator("effective_from")(aware_utc)

    @model_validator(mode="after")
    def validate_patch(self) -> "RetroPolicyPatchView":
        refs = (self.prompt_policy_ref, self.retrieval_policy_ref, self.tool_policy_ref)
        if self.status == "NO_PATCH" and any(ref is not None for ref in refs):
            raise ValueError("NO_PATCH must not contain policy refs")
        if self.status == "VALID_PATCH" and all(ref is None for ref in refs):
            raise ValueError("VALID_PATCH requires at least one policy ref")
        return self


class FoundationResourceManifest(FrozenContractModel):
    schema_id: Literal["p3_foundation_resource_manifest.v1"]
    schema_version: Literal["1.0.0"]
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    rag_index_ref: ArtifactRef
    graph_rag_ref: ArtifactRef
    memory_policy_ref: ArtifactRef
    tool_registry_ref: ArtifactRef
    entitlement_ref: ArtifactRef
    gateway_policy_ref: ArtifactRef
    prompt_bundle_ref: ArtifactRef
    model_registry_ref: ArtifactRef
    manifest_hash: Sha256
    status: Literal["READY", "DEGRADED"]
    degraded_capabilities: tuple[NonEmptyStr, ...] = ()


class CanonicalCyclePipelineConfig(FrozenContractModel):
    schema_id: Literal["canonical_cycle_pipeline_config.v2"]
    schema_version: Literal["2.0.0"]
    initialization_module_ranges: tuple[Literal["P3.S12-P3.S16"], ...]
    cycle_kernel_module_ranges: tuple[Literal["P3.S17-P3.S26"], ...]
    kernel_contract_version: NonEmptyStr
    accepted_kernel_versions: tuple[NonEmptyStr, ...]
    warmup_mode_overrides: tuple[NonEmptyStr, ...]
    required_trace_fields: tuple[NonEmptyStr, ...]
    foundation_resource_manifest: FoundationResourceManifest

    @model_validator(mode="after")
    def validate_pipeline(self) -> "CanonicalCyclePipelineConfig":
        required_overrides = {"disable_official_handoffs", "disable_p9_exports", "keep_pit_and_authority_rules"}
        if not required_overrides.issubset(set(self.warmup_mode_overrides)):
            raise ValueError("warmup_mode_overrides missing required protections")
        required_trace = {"cycle_id", "module_id", "input_hashes", "output_hashes", "as_of_time"}
        if not required_trace.issubset(set(self.required_trace_fields)):
            raise ValueError("required_trace_fields incomplete")
        return self


class WarmupReplayConfig(FrozenContractModel):
    schema_id: Literal["warmup_replay_config.v2"]
    schema_version: Literal["2.0.0"]
    direct_state_synthesis_forbidden: Literal[True]
    genesis_factory_allowed: Literal[True]
    record_module_trace: Literal[True]
    record_seeds: Literal[True]
    fail_on_noncanonical_module: Literal[True]
    checkpoint_write_mode: Literal["ATOMIC_JSON"]
    stop_on_kernel_degraded: StrictBool = False
    max_replay_items: Annotated[StrictInt, Field(gt=0, le=100000)] = 10000
    resume_checkpoint_id: NonEmptyStr | None = None
    base_seed: Annotated[StrictInt, Field(ge=0)] = 0


class PersonStateRecord(FrozenContractModel):
    person_id: NonEmptyStr
    structural_profile_hash: Sha256
    representation_weight: UnitFloat
    status: PersonDynamicStatus
    attention: UnitFloat
    fatigue: UnitFloat
    last_updated_at: datetime

    _parse_dt = field_validator("last_updated_at", mode="before")(parse_datetime)
    _utc_dt = field_validator("last_updated_at")(aware_utc)


class PersonStatePanel(FrozenContractModel):
    schema_id: Literal["person_state_panel.v2"] = "person_state_panel.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    records: tuple[PersonStateRecord, ...]
    content_hash: Sha256


class BeliefStateRecord(FrozenContractModel):
    belief_id: NonEmptyStr
    person_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    value: SignedUnitFloat
    confidence: UnitFloat
    available_at: datetime

    _parse_dt = field_validator("available_at", mode="before")(parse_datetime)
    _utc_dt = field_validator("available_at")(aware_utc)


class BeliefStatePanel(FrozenContractModel):
    schema_id: Literal["belief_state_panel.v2"] = "belief_state_panel.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    records: tuple[BeliefStateRecord, ...]
    content_hash: Sha256


class MemoryRecord(FrozenContractModel):
    memory_id: NonEmptyStr
    person_id: NonEmptyStr
    memory_type: MemoryType
    visibility_scope: VisibilityScope
    created_at: datetime
    available_at: datetime
    content_ref: ArtifactRef
    importance: UnitFloat
    repetition: UnitFloat
    significance: UnitFloat

    _parse_dt = field_validator("created_at", "available_at", mode="before")(parse_datetime)
    _utc_dt = field_validator("created_at", "available_at")(aware_utc)

    @model_validator(mode="after")
    def validate_times(self) -> "MemoryRecord":
        if self.available_at < self.created_at:
            raise ValueError("memory available_at must not precede created_at")
        return self


class MemoryState(FrozenContractModel):
    schema_id: Literal["memory_state.v2"] = "memory_state.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    records: tuple[MemoryRecord, ...]
    content_hash: Sha256


class SocialEdgeState(FrozenContractModel):
    """Replay-safe social edge state preserving the population prior."""

    edge_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    relationship_type: NonEmptyStr
    trust: UnitFloat
    strength: UnitFloat
    influence: UnitFloat
    interaction_frequency: UnitFloat
    selection_probability: UnitFloat
    domain_trust: dict[NonEmptyStr, UnitFloat]
    origin: NonEmptyStr
    valid_from: datetime
    available_at: datetime

    _parse_dt = field_validator("valid_from", "available_at", mode="before")(parse_datetime)
    _utc_dt = field_validator("valid_from", "available_at")(aware_utc)


class SocialGraphState(FrozenContractModel):
    schema_id: Literal["social_graph_state.v2"] = "social_graph_state.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    records: tuple[SocialEdgeState, ...]
    content_hash: Sha256


class PendingStimulus(FrozenContractModel):
    stimulus_id: NonEmptyStr
    available_from_cycle: PositiveInt
    content_ref: ArtifactRef


class BeliefCommitment(FrozenContractModel):
    commitment_id: NonEmptyStr
    person_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    committed_at: datetime
    content_hash: Sha256

    _parse_dt = field_validator("committed_at", mode="before")(parse_datetime)
    _utc_dt = field_validator("committed_at")(aware_utc)


class ReplayCursor(FrozenContractModel):
    last_completed_schedule_sequence: NonNegativeInt
    last_checkpoint_id: NonEmptyStr | None
    schedule_hash: Sha256
    checkpoint_plan_hash: Sha256


class ReplayState(FrozenContractModel):
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    replay_cycle_number: NonNegativeInt
    as_of_time: datetime
    population_hash: Sha256
    source: StateSource
    person_state: PersonStatePanel
    belief_state: BeliefStatePanel
    memory_state: MemoryState
    social_graph: SocialGraphState
    pending_stimuli: tuple[PendingStimulus, ...]
    belief_commitments: tuple[BeliefCommitment, ...]
    replay_cursor: ReplayCursor
    resource_manifest_ref: ArtifactRef
    policy_refs: tuple[ArtifactRef, ...]
    audit_refs: tuple[ArtifactRef, ...]
    state_hash: Sha256
    lineage: StateLineage

    _parse_dt = field_validator("as_of_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("as_of_time")(aware_utc)


class ModuleTraceEntry(FrozenContractModel):
    cycle_id: NonEmptyStr
    module_id: Annotated[StrictStr, Field(pattern=r"^P3\.S(?:1[7-9]|2[0-6])\.M\d{2}$")]
    input_hashes: tuple[Sha256, ...]
    output_hashes: tuple[Sha256, ...]
    as_of_time: datetime
    status: Literal["SUCCEEDED", "DEGRADED"]

    _parse_dt = field_validator("as_of_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("as_of_time")(aware_utc)


class ToolAuditEntry(FrozenContractModel):
    tool_call_id: NonEmptyStr
    tool_id: NonEmptyStr
    person_id: NonEmptyStr
    available_at: datetime
    status: Literal["SUCCEEDED", "FAILED", "REJECTED"]
    request_hash: Sha256
    result_hash: Sha256 | None = None

    _parse_dt = field_validator("available_at", mode="before")(parse_datetime)
    _utc_dt = field_validator("available_at")(aware_utc)


class CycleKernelRequest(FrozenContractModel):
    request_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    mode: Literal["WARMUP_REPLAY"]
    logical_time: datetime
    prior_state: ReplayState
    schedule_item: WarmupScheduleItem
    resource_manifest: FoundationResourceManifest
    retro_policy_patch: RetroPolicyPatchView
    seed: Annotated[StrictInt, Field(ge=0)]
    emit_p4_outputs: Literal[False] = False
    emit_p9_outputs: Literal[False] = False

    _parse_dt = field_validator("logical_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("logical_time")(aware_utc)


class CycleKernelResult(FrozenContractModel):
    request_id: NonEmptyStr
    status: KernelExecutionStatus
    next_state: ReplayState
    module_trace: tuple[ModuleTraceEntry, ...]
    tool_audits: tuple[ToolAuditEntry, ...] = ()
    emitted_p4_outputs: Literal[False] = False
    emitted_p9_outputs: Literal[False] = False
    issues: tuple[dict[str, object], ...] = ()


class CheckpointRecord(FrozenContractModel):
    checkpoint_id: NonEmptyStr
    checkpoint_ref: ArtifactRef
    after_schedule_sequence_number: NonNegativeInt
    logical_time: datetime
    state_hash: Sha256
    previous_checkpoint_id: NonEmptyStr | None
    final: StrictBool

    _parse_dt = field_validator("logical_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("logical_time")(aware_utc)


class ReplayItemAudit(FrozenContractModel):
    schedule_item_id: NonEmptyStr
    sequence_number: PositiveInt
    request_id: NonEmptyStr
    logical_time: datetime
    status: Literal["SUCCEEDED", "DEGRADED"]
    prior_state_hash: Sha256
    next_state_hash: Sha256
    module_trace: tuple[ModuleTraceEntry, ...]
    tool_audits: tuple[ToolAuditEntry, ...]

    _parse_dt = field_validator("logical_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("logical_time")(aware_utc)


class InitialCycleStateSnapshot(FrozenContractModel):
    schema_id: Literal["initial_cycle_state_snapshot.v2"] = "initial_cycle_state_snapshot.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S11.M01"] = "P3.S11.M01"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    evaluation_start: datetime
    available_from_cycle: Literal[1] = 1
    terminal_checkpoint_id: NonEmptyStr
    terminal_checkpoint_ref: ArtifactRef
    state: ReplayState
    content_hash: Sha256
    lineage: StateLineage

    _parse_dt = field_validator("evaluation_start", mode="before")(parse_datetime)
    _utc_dt = field_validator("evaluation_start")(aware_utc)


class WarmupReplayAudit(FrozenContractModel):
    schema_id: Literal["warmup_replay_audit.v2"] = "warmup_replay_audit.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S11.M01"] = "P3.S11.M01"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    invocation_mode: ReplayInvocationMode
    status: ArtifactStatus
    schedule_hash: Sha256
    checkpoint_plan_hash: Sha256
    kernel_contract_version: NonEmptyStr
    resource_manifest_hash: Sha256
    resume_source_checkpoint_id: NonEmptyStr | None
    item_audits: tuple[ReplayItemAudit, ...]
    checkpoints: tuple[CheckpointRecord, ...]
    terminal_checkpoint_id: NonEmptyStr
    terminal_state_hash: Sha256
    metrics: dict[str, object]
    issues: tuple[dict[str, object], ...]
    lineage_id: NonEmptyStr


class LeakageValidationReport(FrozenContractModel):
    status: Literal["PASS"]
    checked_at: datetime
    evaluation_start: datetime
    max_available_at: datetime
    canonical_module_count: NonNegativeInt
    tool_audit_count: NonNegativeInt
    person_count: PositiveInt
    belief_count: NonNegativeInt
    memory_count: NonNegativeInt
    social_edge_count: NonNegativeInt
    checks: tuple[NonEmptyStr, ...]

    _parse_dt = field_validator("checked_at", "evaluation_start", "max_available_at", mode="before")(parse_datetime)
    _utc_dt = field_validator("checked_at", "evaluation_start", "max_available_at")(aware_utc)


class ValidatedInitialCycleStateSnapshot(FrozenContractModel):
    schema_id: Literal["validated_initial_cycle_state_snapshot.v2"] = "validated_initial_cycle_state_snapshot.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S11.M02"] = "P3.S11.M02"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    source_snapshot: InitialCycleStateSnapshot
    validation_report: LeakageValidationReport
    content_hash: Sha256
    lineage: StateLineage


class PriorCycleStateSnapshot(FrozenContractModel):
    schema_id: Literal["prior_cycle_state_snapshot.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cycle_number: PositiveInt
    available_from_cycle: PositiveInt
    state: ReplayState
    content_hash: Sha256
    lineage: StateLineage

    @model_validator(mode="after")
    def validate_cycle(self) -> "PriorCycleStateSnapshot":
        if self.available_from_cycle != self.cycle_number + 1:
            raise ValueError("prior state must become available in the next cycle")
        return self


class CycleStateLoadRequest(FrozenContractModel):
    schema_id: Literal["cycle_state_load_request.v1"] = "cycle_state_load_request.v1"
    schema_version: Literal["1.0.0"] = "1.0.0"
    current_run_id: NonEmptyStr
    current_snapshot_id: NonEmptyStr
    current_cycle_id: NonEmptyStr
    current_cycle_number: PositiveInt
    current_as_of: datetime
    accepted_initial_schema_versions: tuple[NonEmptyStr, ...] = ("2.0.0",)
    accepted_prior_schema_versions: tuple[NonEmptyStr, ...] = ("2.0.0",)
    validated_initial_cycle_state_snapshot: ValidatedInitialCycleStateSnapshot | None = None
    prior_cycle_state_snapshot: PriorCycleStateSnapshot | None = None

    _parse_dt = field_validator("current_as_of", mode="before")(parse_datetime)
    _utc_dt = field_validator("current_as_of")(aware_utc)

    @model_validator(mode="after")
    def validate_one_source(self) -> "CycleStateLoadRequest":
        count = int(self.validated_initial_cycle_state_snapshot is not None) + int(self.prior_cycle_state_snapshot is not None)
        if count != 1:
            raise ValueError("exactly one state source must be supplied")
        return self


class CurrentPersonStatePanel(FrozenContractModel):
    schema_id: Literal["current_person_state_panel.v2"] = "current_person_state_panel.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S11.M03"] = "P3.S11.M03"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cycle_number: PositiveInt
    as_of_time: datetime
    source_state_hash: Sha256
    records: tuple[PersonStateRecord, ...]
    content_hash: Sha256
    lineage_id: NonEmptyStr

    _parse_dt = field_validator("as_of_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("as_of_time")(aware_utc)


class CurrentBeliefStatePanel(FrozenContractModel):
    schema_id: Literal["current_belief_state_panel.v2"] = "current_belief_state_panel.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S11.M03"] = "P3.S11.M03"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cycle_number: PositiveInt
    as_of_time: datetime
    source_state_hash: Sha256
    records: tuple[BeliefStateRecord, ...]
    content_hash: Sha256
    lineage_id: NonEmptyStr

    _parse_dt = field_validator("as_of_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("as_of_time")(aware_utc)


class CurrentMemoryState(FrozenContractModel):
    schema_id: Literal["current_memory_state.v2"] = "current_memory_state.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S11.M03"] = "P3.S11.M03"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cycle_number: PositiveInt
    as_of_time: datetime
    source_state_hash: Sha256
    records: tuple[MemoryRecord, ...]
    content_hash: Sha256
    lineage_id: NonEmptyStr

    _parse_dt = field_validator("as_of_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("as_of_time")(aware_utc)


class CurrentSocialGraph(FrozenContractModel):
    schema_id: Literal["current_social_graph.v2"] = "current_social_graph.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S11.M03"] = "P3.S11.M03"
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    cycle_id: NonEmptyStr
    cycle_number: PositiveInt
    as_of_time: datetime
    source_state_hash: Sha256
    records: tuple[SocialEdgeState, ...]
    content_hash: Sha256
    lineage_id: NonEmptyStr

    _parse_dt = field_validator("as_of_time", mode="before")(parse_datetime)
    _utc_dt = field_validator("as_of_time")(aware_utc)


class CycleStateLoadResult(FrozenContractModel):
    person_state: CurrentPersonStatePanel
    belief_state: CurrentBeliefStatePanel
    memory_state: CurrentMemoryState
    social_graph: CurrentSocialGraph
