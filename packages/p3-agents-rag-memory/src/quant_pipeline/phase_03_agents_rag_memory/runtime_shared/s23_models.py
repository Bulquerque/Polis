from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .s21_models import (
    ArtifactPanel,
    ArtifactStatus,
    JsonValue,
    LineageRecord,
    NonEmptyStr,
    Probability,
    SCHEMA_VERSION,
    StrictModel,
    UTCDateTime,
)
from .s22_models import BeliefDelta, BeliefPayload, CurrentBeliefStatePanel


UnitIntervalMap = dict[NonEmptyStr, Probability]


class StateSpeedClass(StrEnum):
    SLOW = "SLOW"
    MEDIUM = "MEDIUM"
    FAST = "FAST"


class TransitionStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    NO_CHANGE = "NO_CHANGE"


class GuardStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class PersonStateIdentity(StrictModel):
    life_stage_at_creation: NonEmptyStr
    creator_provenance: dict[NonEmptyStr, JsonValue]


class CurrentPersonStateRecord(StrictModel):
    person_state_id: NonEmptyStr
    person_id: NonEmptyStr
    profile_hash: NonEmptyStr
    identity: PersonStateIdentity
    core_personality: UnitIntervalMap = Field(default_factory=dict)
    cognitive_capacity: UnitIntervalMap = Field(default_factory=dict)
    knowledge: UnitIntervalMap = Field(default_factory=dict)
    trust: UnitIntervalMap = Field(default_factory=dict)
    tool_proficiency: UnitIntervalMap = Field(default_factory=dict)
    attention: UnitIntervalMap = Field(default_factory=dict)
    confidence: UnitIntervalMap = Field(default_factory=dict)
    functional_affect: UnitIntervalMap = Field(default_factory=dict)
    belief_refs: tuple[NonEmptyStr, ...] = ()
    updated_at: UTCDateTime
    state_version: Annotated[int, Field(ge=1)] = 1


class CurrentPersonStatePanel(ArtifactPanel[CurrentPersonStateRecord]):
    pass


class PersonSchemaPolicy(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    policy_version: NonEmptyStr = "person-state-policy-v1"
    immutable_fields: tuple[NonEmptyStr, ...] = (
        "person_id",
        "profile_hash",
        "identity.life_stage_at_creation",
        "identity.creator_provenance",
    )
    slow_families: tuple[NonEmptyStr, ...] = ("core_personality", "cognitive_capacity")
    medium_families: tuple[NonEmptyStr, ...] = (
        "knowledge",
        "trust",
        "tool_proficiency",
    )
    fast_families: tuple[NonEmptyStr, ...] = (
        "attention",
        "confidence",
        "functional_affect",
    )
    transition_authorized_families: tuple[NonEmptyStr, ...] = (
        "knowledge",
        "attention",
        "confidence",
        "functional_affect",
    )

    @model_validator(mode="after")
    def families_are_disjoint(self) -> "PersonSchemaPolicy":
        groups = [set(self.slow_families), set(self.medium_families), set(self.fast_families)]
        if any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)):
            raise ValueError("state speed families must be disjoint")
        declared = set().union(*groups)
        if not set(self.transition_authorized_families).issubset(declared):
            raise ValueError("authorized transition families must be declared")
        return self

    def speed_for(self, family: str) -> StateSpeedClass:
        if family in self.slow_families:
            return StateSpeedClass.SLOW
        if family in self.medium_families:
            return StateSpeedClass.MEDIUM
        if family in self.fast_families:
            return StateSpeedClass.FAST
        raise ValueError(f"undeclared state family: {family}")


class StateChangeConfig(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    config_version: NonEmptyStr = "s23-state-change-v1"
    average_calendar_days_per_month: Annotated[float, Field(gt=27.0, lt=32.0)] = 30.4375
    slow_max_delta_per_month: Annotated[float, Field(ge=0.0, le=1.0)] = 0.01
    medium_max_delta_per_month: Annotated[float, Field(ge=0.0, le=1.0)] = 0.05
    fast_max_delta_per_cycle: Annotated[float, Field(ge=0.0, le=1.0)] = 0.25
    knowledge_gain_rate: Annotated[float, Field(ge=0.0, le=1.0)] = 0.04
    attention_gain_per_bound_update: Annotated[float, Field(ge=0.0, le=1.0)] = 0.08
    confidence_alignment_rate: Annotated[float, Field(ge=0.0, le=1.0)] = 0.50
    uncertainty_alignment_rate: Annotated[float, Field(ge=0.0, le=1.0)] = 0.50
    tool_proficiency_requires_executed_call: Literal[True] = True
    tool_proficiency_without_audit_policy: Literal["PRESERVE"] = "PRESERVE"
    numeric_tolerance: Annotated[float, Field(gt=0.0, le=1e-6)] = 1e-12


class PersonFieldChange(StrictModel):
    field_path: NonEmptyStr
    speed_class: StateSpeedClass
    prior_value: Probability
    candidate_value: Probability
    accepted_value: Probability
    delta: Annotated[float, Field(ge=-1.0, le=1.0)]
    allowed_delta: Annotated[float, Field(ge=0.0, le=1.0)]
    reason_code: NonEmptyStr
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    cause_ids: tuple[NonEmptyStr, ...] = ()
    executed_tool_call_refs: tuple[NonEmptyStr, ...] = ()


class NextPersonStateRecord(StrictModel):
    transition_id: NonEmptyStr
    person_id: NonEmptyStr
    prior_person_state_id: NonEmptyStr
    prior_state_version: Annotated[int, Field(ge=1)]
    candidate_state: CurrentPersonStateRecord
    field_changes: tuple[PersonFieldChange, ...]
    belief_update_ids: tuple[NonEmptyStr, ...] = ()
    transition_at: UTCDateTime
    transition_status: TransitionStatus
    policy_version: NonEmptyStr
    config_version: NonEmptyStr

    @model_validator(mode="after")
    def status_matches_changes(self) -> "NextPersonStateRecord":
        if self.transition_status is TransitionStatus.NO_CHANGE and self.field_changes:
            raise ValueError("NO_CHANGE transition cannot contain field changes")
        if self.candidate_state.person_id != self.person_id:
            raise ValueError("candidate state person mismatch")
        return self


class NextPersonStatePanel(ArtifactPanel[NextPersonStateRecord]):
    pass


class NextBeliefStateRecord(StrictModel):
    belief_state_id: NonEmptyStr
    prior_belief_state_id: NonEmptyStr | None = None
    belief_update_id: NonEmptyStr | None = None
    person_id: NonEmptyStr
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    payload: BeliefPayload
    prior_payload: BeliefPayload | None = None
    delta: BeliefDelta | None = None
    confidence: Probability
    uncertainty: Probability
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    cause_ids: tuple[NonEmptyStr, ...] = ()
    updated_at: UTCDateTime
    state_version: Annotated[int, Field(ge=1)]
    state_origin: Literal["UPDATED", "UNCHANGED"]


class NextBeliefStatePanel(ArtifactPanel[NextBeliefStateRecord]):
    pass


class RejectedPersonStateTransition(StrictModel):
    transition_id: NonEmptyStr
    person_id: NonEmptyStr
    reason_codes: tuple[NonEmptyStr, ...]


class ValidatedNextPersonStatePanel(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: ArtifactStatus
    records: tuple[CurrentPersonStateRecord, ...]
    rejections: tuple[RejectedPersonStateTransition, ...] = ()
    lineage: LineageRecord
    reason_code: str | None = None


# Re-export upstream consumer model.
__all__ = [
    "CurrentBeliefStatePanel",
    "CurrentPersonStatePanel",
    "CurrentPersonStateRecord",
    "GuardStatus",
    "NextBeliefStatePanel",
    "NextBeliefStateRecord",
    "NextPersonStatePanel",
    "NextPersonStateRecord",
    "PersonFieldChange",
    "PersonSchemaPolicy",
    "PersonStateIdentity",
    "RejectedPersonStateTransition",
    "StateChangeConfig",
    "StateSpeedClass",
    "TransitionStatus",
    "ValidatedNextPersonStatePanel",
]
