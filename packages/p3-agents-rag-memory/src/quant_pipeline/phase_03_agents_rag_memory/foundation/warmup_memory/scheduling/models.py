from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
PositiveInt = Annotated[StrictInt, Field(gt=0)]


class FrozenContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


def _parse_datetime(value: object) -> object:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return value
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return value


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value.astimezone(UTC)


class WarmupMode(StrEnum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    GENESIS_ONLY = "GENESIS_ONLY"


class ArtifactStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"


class ScheduleItemKind(StrEnum):
    EVENT_RELEASE = "EVENT_RELEASE"
    HEARTBEAT_OBLIGATION = "HEARTBEAT_OBLIGATION"


class CheckpointReason(StrEnum):
    MONTHLY_BOUNDARY = "MONTHLY_BOUNDARY"
    FINAL_REPLAY_BOUNDARY = "FINAL_REPLAY_BOUNDARY"
    GENESIS = "GENESIS"


class ArtifactRef(FrozenContractModel):
    artifact_id: NonEmptyStr
    artifact_type: NonEmptyStr
    content_hash: Sha256
    schema_id: NonEmptyStr | None = None
    schema_version: NonEmptyStr | None = None


class RecordLineage(FrozenContractModel):
    lineage_id: NonEmptyStr
    source_artifact_ids: tuple[NonEmptyStr, ...] = ()
    parent_lineage_ids: tuple[NonEmptyStr, ...] = ()
    holdout_refs: tuple[NonEmptyStr, ...] = ()


class HistoryRecord(FrozenContractModel):
    history_record_id: NonEmptyStr
    event_id: NonEmptyStr
    source_id: NonEmptyStr
    partition: NonEmptyStr
    event_time: datetime
    effective_time: datetime | None = None
    available_at: datetime
    ingested_at: datetime
    payload_ref: ArtifactRef
    underlyings: tuple[NonEmptyStr, ...] = ()
    propositions: tuple[NonEmptyStr, ...] = ()
    lineage: RecordLineage

    _parse_dt = field_validator("event_time", "effective_time", "available_at", "ingested_at", mode="before")(_parse_datetime)
    _utc_dt = field_validator("event_time", "effective_time", "available_at", "ingested_at")(_aware_utc)


class ValidatedWarmupHistoryView(FrozenContractModel):
    schema_id: Literal["validated_warmup_history.v1"]
    schema_version: Literal["1.0.0"]
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S9.M01"]
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    as_of: datetime
    mode: WarmupMode
    status: ArtifactStatus
    evaluation_start: datetime
    warmup_start: datetime | None
    warmup_end: datetime | None
    records: tuple[HistoryRecord, ...]
    history_hash: Sha256
    lineage: dict[str, object]
    validation_summary: dict[str, object]
    issues: tuple[dict[str, object], ...] = ()

    _parse_dt = field_validator("as_of", "evaluation_start", "warmup_start", "warmup_end", mode="before")(_parse_datetime)
    _utc_dt = field_validator("as_of", "evaluation_start", "warmup_start", "warmup_end")(_aware_utc)

    @model_validator(mode="after")
    def validate_mode(self) -> "ValidatedWarmupHistoryView":
        if self.mode is WarmupMode.GENESIS_ONLY and self.records:
            raise ValueError("GENESIS_ONLY history must not contain records")
        if self.mode is WarmupMode.HISTORICAL_REPLAY and not self.records:
            raise ValueError("HISTORICAL_REPLAY history requires records")
        if self.warmup_end is not None and self.warmup_end >= self.evaluation_start:
            raise ValueError("warmup_end must be strictly before evaluation_start")
        return self


class PopulationPerson(FrozenContractModel):
    person_id: NonEmptyStr
    representation_weight: Annotated[float, Field(gt=0.0, le=1.0)]


class ValidatedPopulationManifestView(FrozenContractModel):
    schema_id: Literal["validated_population_manifest.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    population_hash: Sha256
    persons: tuple[PopulationPerson, ...]
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def validate_persons(self) -> "ValidatedPopulationManifestView":
        ids = [person.person_id for person in self.persons]
        if not ids:
            raise ValueError("population must contain at least one person")
        if len(ids) != len(set(ids)):
            raise ValueError("person_id values must be unique")
        total = sum(person.representation_weight for person in self.persons)
        if abs(total - 1.0) > 1e-9:
            raise ValueError("representation weights must sum to 1")
        return self


class SocialEdge(FrozenContractModel):
    edge_id: NonEmptyStr
    source_person_id: NonEmptyStr
    target_person_id: NonEmptyStr
    relationship_type: NonEmptyStr


class ValidatedInitialSocialGraphView(FrozenContractModel):
    schema_id: Literal["validated_initial_social_graph.v2"]
    schema_version: Literal["2.0.0"]
    artifact_id: NonEmptyStr
    run_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    population_hash: Sha256
    graph_hash: Sha256
    records: tuple[SocialEdge, ...]
    lineage_id: NonEmptyStr


class ActivationConfigView(FrozenContractModel):
    schema_id: Literal["activation_config.v2"]
    schema_version: Literal["2.0.0"]
    monthly_heartbeat: Literal[True]
    event_priority: Annotated[StrictInt, Field(ge=0, le=1000)] = 10
    heartbeat_priority: Annotated[StrictInt, Field(ge=0, le=1000)] = 20
    max_extra_activations: Annotated[StrictInt, Field(ge=0, le=1000)] = 10

    @model_validator(mode="after")
    def validate_priority(self) -> "ActivationConfigView":
        if self.event_priority >= self.heartbeat_priority:
            raise ValueError("event_priority must be lower than heartbeat_priority")
        return self


class HeartbeatConfig(FrozenContractModel):
    schema_id: Literal["heartbeat_config.v1"]
    schema_version: Literal["1.0.0"]
    enabled: Literal[True]
    frequency: Literal["MONTHLY"]
    due_day_policy: Literal["MONTH_END"]
    due_hour_utc: Annotated[StrictInt, Field(ge=0, le=23)] = 23
    due_minute_utc: Annotated[StrictInt, Field(ge=0, le=59)] = 59
    due_second_utc: Annotated[StrictInt, Field(ge=0, le=59)] = 59
    include_partial_months: StrictBool = True
    event_activation_may_satisfy_obligation: Literal[True] = True
    max_heartbeat_delay_days: Annotated[StrictInt, Field(ge=0, le=31)] = 7


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

    _parse_dt = field_validator("logical_time", mode="before")(_parse_datetime)
    _utc_dt = field_validator("logical_time")(_aware_utc)

    @model_validator(mode="after")
    def validate_discriminator(self) -> "WarmupScheduleItem":
        if self.kind is ScheduleItemKind.EVENT_RELEASE:
            if self.event_ref is None or self.person_id is not None or self.heartbeat_period is not None:
                raise ValueError("EVENT_RELEASE requires event_ref only")
        else:
            if self.event_ref is not None or self.person_id is None or self.heartbeat_period is None:
                raise ValueError("HEARTBEAT_OBLIGATION requires person_id and heartbeat_period")
        return self


class ScheduleLineage(FrozenContractModel):
    lineage_id: NonEmptyStr
    history_artifact_id: NonEmptyStr
    history_hash: Sha256
    population_artifact_id: NonEmptyStr
    population_hash: Sha256
    social_graph_artifact_id: NonEmptyStr
    graph_hash: Sha256
    source_lineage_ids: tuple[NonEmptyStr, ...]


class ScheduleSummary(FrozenContractModel):
    event_item_count: NonNegativeInt
    heartbeat_item_count: NonNegativeInt
    person_count: PositiveInt
    month_count: NonNegativeInt
    total_item_count: NonNegativeInt


class WarmupEventSchedule(FrozenContractModel):
    schema_id: Literal["warmup_event_schedule.v2"] = "warmup_event_schedule.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S10.M01"] = "P3.S10.M01"
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
    lineage: ScheduleLineage
    summary: ScheduleSummary
    issues: tuple[dict[str, object], ...] = ()

    _parse_dt = field_validator("as_of", "evaluation_start", "schedule_start", "schedule_end", mode="before")(_parse_datetime)
    _utc_dt = field_validator("as_of", "evaluation_start", "schedule_start", "schedule_end")(_aware_utc)

    @model_validator(mode="after")
    def validate_schedule(self) -> "WarmupEventSchedule":
        times = [item.logical_time for item in self.items]
        if times != sorted(times):
            raise ValueError("schedule items must be monotonic")
        if any(item.logical_time >= self.evaluation_start for item in self.items):
            raise ValueError("all schedule items must occur before evaluation_start")
        if [item.sequence_number for item in self.items] != list(range(1, len(self.items) + 1)):
            raise ValueError("sequence numbers must be contiguous")
        if len({item.deduplication_key for item in self.items}) != len(self.items):
            raise ValueError("deduplication keys must be unique")
        return self


class WarmupCheckpointConfig(FrozenContractModel):
    schema_id: Literal["warmup_checkpoint_config.v2"]
    schema_version: Literal["2.0.0"]
    checkpoint_frequency: Literal["MONTHLY"]
    final_checkpoint_required: Literal[True]
    resume_supported: StrictBool
    hash_all_state_families: Literal[True]
    required_state_families: tuple[NonEmptyStr, ...]
    max_checkpoint_count: Annotated[StrictInt, Field(gt=0, le=10000)] = 1000

    @model_validator(mode="after")
    def validate_families(self) -> "WarmupCheckpointConfig":
        required = {
            "person_state", "belief_state", "memory_state", "social_graph",
            "pending_stimuli", "belief_commitments", "replay_cursor",
            "resource_refs", "policy_refs", "audit_refs",
        }
        if not required.issubset(set(self.required_state_families)):
            missing = sorted(required - set(self.required_state_families))
            raise ValueError(f"required_state_families missing: {missing}")
        if len(self.required_state_families) != len(set(self.required_state_families)):
            raise ValueError("required_state_families must be unique")
        return self


class PlannedCheckpoint(FrozenContractModel):
    checkpoint_id: NonEmptyStr
    sequence_number: PositiveInt
    after_schedule_sequence_number: NonNegativeInt
    logical_time: datetime
    reason: CheckpointReason
    previous_checkpoint_id: NonEmptyStr | None
    required_state_families: tuple[NonEmptyStr, ...]
    final: StrictBool

    _parse_dt = field_validator("logical_time", mode="before")(_parse_datetime)
    _utc_dt = field_validator("logical_time")(_aware_utc)


class CheckpointPlanLineage(FrozenContractModel):
    lineage_id: NonEmptyStr
    schedule_artifact_id: NonEmptyStr
    schedule_hash: Sha256
    checkpoint_config_hash: Sha256
    source_lineage_ids: tuple[NonEmptyStr, ...]


class WarmupCheckpointPlan(FrozenContractModel):
    schema_id: Literal["warmup_checkpoint_plan.v2"] = "warmup_checkpoint_plan.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: NonEmptyStr
    module_id: Literal["P3.S10.M02"] = "P3.S10.M02"
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
    lineage: CheckpointPlanLineage
    issues: tuple[dict[str, object], ...] = ()

    _parse_dt = field_validator("as_of", "evaluation_start", "final_checkpoint_time", mode="before")(_parse_datetime)
    _utc_dt = field_validator("as_of", "evaluation_start", "final_checkpoint_time")(_aware_utc)

    @model_validator(mode="after")
    def validate_checkpoints(self) -> "WarmupCheckpointPlan":
        if not self.checkpoints:
            raise ValueError("checkpoint plan must contain at least one checkpoint")
        times = [checkpoint.logical_time for checkpoint in self.checkpoints]
        if times != sorted(times):
            raise ValueError("checkpoints must be monotonic")
        if any(value >= self.evaluation_start for value in times):
            raise ValueError("checkpoints must be strictly before evaluation_start")
        if [c.sequence_number for c in self.checkpoints] != list(range(1, len(self.checkpoints) + 1)):
            raise ValueError("checkpoint sequence numbers must be contiguous")
        finals = [checkpoint for checkpoint in self.checkpoints if checkpoint.final]
        if len(finals) != 1 or finals[0].checkpoint_id != self.final_checkpoint_id:
            raise ValueError("exactly one checkpoint must be final")
        if finals[0].logical_time != self.final_checkpoint_time:
            raise ValueError("final checkpoint time mismatch")
        for index, checkpoint in enumerate(self.checkpoints):
            expected = None if index == 0 else self.checkpoints[index - 1].checkpoint_id
            if checkpoint.previous_checkpoint_id != expected:
                raise ValueError("checkpoint chain is invalid")
        return self
