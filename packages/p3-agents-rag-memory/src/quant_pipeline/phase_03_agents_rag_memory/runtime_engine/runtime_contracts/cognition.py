from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, JsonValue, field_validator, model_validator

from .base import (
    BeliefDirection,
    CanonicalArtifact,
    LineageRecord,
    NonEmptyStr,
    NonNegativeInt,
    Probability,
    SocialLifecycle,
    StrictModel,
    _utc,
)


class BeliefUpdateRecord(StrictModel):
    belief_update_id: NonEmptyStr
    commitment_id: str | None = None
    person_id: NonEmptyStr
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    value_type: NonEmptyStr
    direction: BeliefDirection
    prior_score: Annotated[float, Field(ge=-1.0, le=1.0)]
    new_score: Annotated[float, Field(ge=-1.0, le=1.0)]
    delta_score: Annotated[float, Field(ge=-2.0, le=2.0)]
    confidence: Probability
    uncertainty: Probability
    supporting_evidence_refs: tuple[str, ...] = ()
    opposing_evidence_refs: tuple[str, ...] = ()
    changed_at: datetime
    lineage_ids: tuple[NonEmptyStr, ...]
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("changed_at")
    @classmethod
    def aware_changed_at(cls, value: datetime) -> datetime:
        return _utc(value)


class BeliefUpdatePanel(CanonicalArtifact):
    records: tuple[BeliefUpdateRecord, ...]

    @model_validator(mode="after")
    def belief_updates_not_future(self) -> "BeliefUpdatePanel":
        if any(item.changed_at > self.as_of_time for item in self.records):
            raise ValueError("belief update occurs after as_of_time")
        return self


class BeliefCommitmentRecord(StrictModel):
    commitment_id: NonEmptyStr
    belief_update_id: NonEmptyStr
    person_id: NonEmptyStr
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    direction: BeliefDirection
    score: Annotated[float, Field(ge=-1.0, le=1.0)]
    confidence: Probability
    uncertainty: Probability
    evidence_refs: tuple[str, ...] = ()
    snapshot_id: NonEmptyStr
    committed_at: datetime
    matures_at: datetime
    commit_hash: NonEmptyStr
    lineage_ids: tuple[NonEmptyStr, ...]
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("committed_at", "matures_at")
    @classmethod
    def aware_commitment_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def commitment_precedes_maturity(self) -> "BeliefCommitmentRecord":
        if self.matures_at <= self.committed_at:
            raise ValueError("belief must be committed before maturity")
        return self


class BeliefCommitmentLog(CanonicalArtifact):
    records: tuple[BeliefCommitmentRecord, ...]

    @model_validator(mode="after")
    def commitments_precede_cutoff(self) -> "BeliefCommitmentLog":
        if any(item.committed_at > self.as_of_time for item in self.records):
            raise ValueError("commitment occurs after as_of_time")
        return self


class PersonStateDeltaRecord(StrictModel):
    person_id: NonEmptyStr
    prior_state_version: NonNegativeInt
    next_state_version: NonNegativeInt
    changed_at: datetime
    changed_fields: tuple[NonEmptyStr, ...]
    attention_score: Probability | None = None
    information_access_score: Probability | None = None
    cause_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    lineage_ids: tuple[NonEmptyStr, ...]

    @field_validator("changed_at")
    @classmethod
    def aware_state_change(cls, value: datetime) -> datetime:
        return _utc(value)


class PersonStateDeltaPanel(CanonicalArtifact):
    records: tuple[PersonStateDeltaRecord, ...]


class SocialDeliveryObservation(StrictModel):
    message_id: NonEmptyStr
    sender_person_id: NonEmptyStr
    recipient_person_id: NonEmptyStr
    lifecycle: SocialLifecycle
    created_cycle_id: NonEmptyStr
    effective_cycle_id: NonEmptyStr
    created_at: datetime
    status_at: datetime
    causal_parent_id: str | None = None
    underlying_id: str | None = None
    proposition_id: str | None = None
    horizon: str | None = None
    evidence_refs: tuple[str, ...] = ()
    lineage_ids: tuple[NonEmptyStr, ...]

    @field_validator("created_at", "status_at")
    @classmethod
    def aware_social_time(cls, value: datetime) -> datetime:
        return _utc(value)


class SocialObservationPanel(CanonicalArtifact):
    records: tuple[SocialDeliveryObservation, ...]
