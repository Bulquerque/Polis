"""Shared scalar types, enums and configurations for P3.S26."""
from __future__ import annotations
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator
from .errors import S26PolicyError

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
SignedBelief = Annotated[float, Field(ge=-1.0, le=1.0)]
BeliefDelta = Annotated[float, Field(ge=-2.0, le=2.0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]

def _tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple): return value
    if isinstance(value, list): return tuple(value)
    raise TypeError("expected a JSON array")

def _datetime(value: Any) -> datetime:
    if isinstance(value, str): value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime): raise TypeError("expected ISO-8601 datetime")
    if value.tzinfo is None: raise ValueError("datetime must include timezone")
    return value.astimezone(UTC)

AwareDateTime = Annotated[datetime, BeforeValidator(_datetime), AfterValidator(lambda x: x.astimezone(UTC))]
StringTuple = Annotated[tuple[NonEmptyStr, ...], BeforeValidator(_tuple)]

class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, validate_default=True, use_enum_values=False)

class MemoryType(StrEnum):
    EPISODIC="EPISODIC"; SEMANTIC="SEMANTIC"; SOCIAL="SOCIAL"; TOOL_EXPERIENCE="TOOL_EXPERIENCE"; BELIEF_FEEDBACK="BELIEF_FEEDBACK"; AUDIT="AUDIT"
class MemoryStatus(StrEnum): ACTIVE="ACTIVE"; SUPERSEDED="SUPERSEDED"; EXPIRED="EXPIRED"
class ExperienceType(StrEnum): GENERAL="GENERAL"; TOOL_DISCOVERY="TOOL_DISCOVERY"; SOCIAL_INTERACTION="SOCIAL_INTERACTION"; BELIEF_UPDATE="BELIEF_UPDATE"
class DeliveryStatus(StrEnum): CREATED="CREATED"; QUEUED="QUEUED"; DELIVERED="DELIVERED"; SEEN="SEEN"; INTERPRETED="INTERPRETED"; USED="USED"; EXPIRED="EXPIRED"; FAILED="FAILED"
class FeedbackStatus(StrEnum): MATURED="MATURED"; NOT_MATURED="NOT_MATURED"; REJECTED="REJECTED"
class RetroPatchStatus(StrEnum): NO_PATCH="NO_PATCH"; ACTIVE="ACTIVE"
class TriggerReason(StrEnum): NEW_MEMORY="NEW_MEMORY"; REINFORCED_MEMORY="REINFORCED_MEMORY"; PROMOTED_MEMORY="PROMOTED_MEMORY"
class StimulusOrigin(StrEnum): TOOL_DISCOVERY="TOOL_DISCOVERY"; SOCIAL_DELIVERY="SOCIAL_DELIVERY"; MEMORY_TRIGGER="MEMORY_TRIGGER"; ATTENTION_FOLLOWUP="ATTENTION_FOLLOWUP"
class ExecutionMode(StrEnum): WARMUP_REPLAY="WARMUP_REPLAY"; LIVE="LIVE"; REPLAY="REPLAY"; DRY_RUN="DRY_RUN"
class ArtifactStatus(StrEnum): READY="READY"; DEGRADED="DEGRADED"; BLOCKED="BLOCKED"
class CommitmentStatus(StrEnum): PENDING="PENDING"; MATURED="MATURED"; INVALIDATED="INVALIDATED"

def _enum(enum_type: type[StrEnum]):
    def parse(value: Any) -> StrEnum:
        if isinstance(value, enum_type): return value
        if isinstance(value, str): return enum_type(value)
        raise TypeError(f"expected {enum_type.__name__}")
    return parse

MemoryTypeValue=Annotated[MemoryType,BeforeValidator(_enum(MemoryType))]
MemoryStatusValue=Annotated[MemoryStatus,BeforeValidator(_enum(MemoryStatus))]
ExperienceTypeValue=Annotated[ExperienceType,BeforeValidator(_enum(ExperienceType))]
DeliveryStatusValue=Annotated[DeliveryStatus,BeforeValidator(_enum(DeliveryStatus))]
FeedbackStatusValue=Annotated[FeedbackStatus,BeforeValidator(_enum(FeedbackStatus))]
RetroPatchStatusValue=Annotated[RetroPatchStatus,BeforeValidator(_enum(RetroPatchStatus))]
TriggerReasonValue=Annotated[TriggerReason,BeforeValidator(_enum(TriggerReason))]
StimulusOriginValue=Annotated[StimulusOrigin,BeforeValidator(_enum(StimulusOrigin))]
ExecutionModeValue=Annotated[ExecutionMode,BeforeValidator(_enum(ExecutionMode))]
ArtifactStatusValue=Annotated[ArtifactStatus,BeforeValidator(_enum(ArtifactStatus))]
CommitmentStatusValue=Annotated[CommitmentStatus,BeforeValidator(_enum(CommitmentStatus))]

class ArtifactContext(StrictModel):
    schema_version: NonEmptyStr; run_id: NonEmptyStr; cycle_id: NonNegativeInt; as_of_time: AwareDateTime; lineage_id: NonEmptyStr

class MemoryConsolidationConfig(StrictModel):
    version: NonEmptyStr; formula_version: NonEmptyStr; episodic_to_semantic_min_repetitions: PositiveInt
    feedback_requires_commit_hash: Literal[True]; audit_memory_append_only: Literal[True]; retro_experiment_memory_forbidden: Literal[True]
    memory_trigger_threshold: Probability; belief_delta_memory_threshold: Probability
    social_delivery_statuses: Annotated[tuple[DeliveryStatusValue,...],BeforeValidator(_tuple)]
    initial_retrievability: Probability; max_retrievability_delta: Probability; reinforcement_learning_rate: Probability
    decay_per_cycle: Probability; expiration_cycles: PositiveInt; expiration_retrievability_threshold: Probability
    allowed_patch_parameters: StringTuple

class StimulusBusConfig(StrictModel):
    version: NonEmptyStr; bus_id: NonEmptyStr
    allowed_sources: Annotated[tuple[StimulusOriginValue,...],BeforeValidator(_tuple)]
    allowed_social_statuses: Annotated[tuple[DeliveryStatusValue,...],BeforeValidator(_tuple)]
    ttl_cycles_by_origin: dict[NonEmptyStr,PositiveInt]; priority_by_origin: dict[NonEmptyStr,Probability]
    max_stimuli_per_person: PositiveInt; overflow_policy: Literal["BLOCK"]; exact_deduplication: Literal[True]
    same_cycle_forbidden: Literal[True]; require_evidence: Literal[True]
    @model_validator(mode="after")
    def complete(self) -> "StimulusBusConfig":
        names={x.value for x in self.allowed_sources}
        if set(self.ttl_cycles_by_origin)!=names or set(self.priority_by_origin)!=names:
            raise ValueError("TTL and priority maps must cover allowed sources")
        return self

def reject_forbidden_memory_patch(parameters: dict[str, object]) -> None:
    forbidden=("person_id","memory_id","content_ref","source_event","evidence_ref","tool_payload","experiment_memory")
    for key,value in parameters.items():
        if any(x in key.lower() for x in forbidden) or any(x in str(value).lower() for x in forbidden):
            raise S26PolicyError("Retro patch cannot name a person, memory, evidence or payload")
