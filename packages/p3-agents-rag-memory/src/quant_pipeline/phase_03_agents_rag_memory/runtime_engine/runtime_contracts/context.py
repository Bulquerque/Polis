from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from .base import (
    ArtifactStatus,
    CanonicalArtifact,
    LineageRecord,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    Probability,
    StrictModel,
    _utc,
)


class EvidenceRecord(StrictModel):
    evidence_id: NonEmptyStr
    evidence_kind: NonEmptyStr
    source_id: NonEmptyStr
    document_id: str | None = None
    chunk_id: str | None = None
    graph_path_id: str | None = None
    content_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    event_time: datetime | None = None
    available_at: datetime
    source_quality_score: Probability = 1.0
    evidence_refs: tuple[str, ...] = ()
    lineage_ids: tuple[NonEmptyStr, ...]

    @field_validator("event_time", "available_at")
    @classmethod
    def aware_optional_datetime(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value)


class RetrievalEvidenceMap(CanonicalArtifact):
    records: tuple[EvidenceRecord, ...]

    @model_validator(mode="after")
    def evidence_identity_unique(self) -> "RetrievalEvidenceMap":
        keys = [(item.evidence_id, item.content_hash) for item in self.records]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate evidence identity")
        if any(item.available_at > self.as_of_time for item in self.records):
            raise ValueError("retrieval evidence is not point-in-time safe")
        return self


class ContextSection(StrictModel):
    section_type: NonEmptyStr
    text: str
    mandatory: bool
    evidence_refs: tuple[str, ...] = ()


class PersonContextRecord(StrictModel):
    activation_id: NonEmptyStr
    cognition_transaction_id: NonEmptyStr
    person_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    seed: NonNegativeInt
    personality_summary: NonEmptyStr
    current_belief_summary: str = ""
    prompt_context: NonEmptyStr
    structured_context: tuple[ContextSection, ...]
    retrieved_evidence_refs: tuple[str, ...] = ()
    allowed_tool_ids: tuple[str, ...] = ()
    tool_budget: NonNegativeInt = 0
    context_token_count: NonNegativeInt
    context_token_limit: PositiveInt
    lineage: LineageRecord

    @model_validator(mode="after")
    def token_budget_respected(self) -> "PersonContextRecord":
        if self.context_token_count > self.context_token_limit:
            raise ValueError("context exceeds token budget")
        return self


class PersonContextBundle(CanonicalArtifact):
    records: tuple[PersonContextRecord, ...]


class StimulusRecord(StrictModel):
    stimulus_id: NonEmptyStr
    origin: NonEmptyStr
    source_event_id: NonEmptyStr
    causal_parent_id: str | None = None
    target_person_id: str | None = None
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    created_cycle_id: NonEmptyStr
    target_cycle_id: NonEmptyStr
    event_time: datetime
    available_at: datetime
    evidence_refs: tuple[str, ...] = ()
    lineage_ids: tuple[NonEmptyStr, ...]

    @field_validator("event_time", "available_at")
    @classmethod
    def aware_stimulus_time(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def available_after_event(self) -> "StimulusRecord":
        if self.available_at < self.event_time:
            raise ValueError("available_at precedes event_time")
        return self


class StimulusPanel(CanonicalArtifact):
    records: tuple[StimulusRecord, ...]

    @model_validator(mode="after")
    def point_in_time_safe(self) -> "StimulusPanel":
        if any(item.available_at > self.as_of_time for item in self.records):
            raise ValueError("stimulus is not point-in-time safe")
        return self


class ActivationRecord(StrictModel):
    activation_id: NonEmptyStr
    person_id: NonEmptyStr
    stimulus_id: NonEmptyStr
    activation_reason: NonEmptyStr
    formula_id: NonEmptyStr
    formula_version: NonEmptyStr
    formula_components: dict[str, float]
    activation_score: NonNegativeFloat
    threshold: NonNegativeFloat
    seed: NonNegativeInt
    scheduled_at: datetime
    causal_parent_id: str | None = None
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    lineage_ids: tuple[NonEmptyStr, ...]

    @field_validator("scheduled_at")
    @classmethod
    def aware_scheduled_at(cls, value: datetime) -> datetime:
        return _utc(value)


class ActivationPanel(CanonicalArtifact):
    records: tuple[ActivationRecord, ...]

    @model_validator(mode="after")
    def activation_not_future(self) -> "ActivationPanel":
        if any(item.scheduled_at > self.as_of_time for item in self.records):
            raise ValueError("activation is scheduled after as_of_time")
        return self


class LearningTrajectoryRecord(StrictModel):
    experience_id: NonEmptyStr
    person_id: NonEmptyStr
    experience_type: NonEmptyStr
    event_time: datetime
    available_at: datetime
    content_ref: NonEmptyStr
    fingerprint: NonEmptyStr
    source_event_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    importance: Probability
    confidence: Probability
    matured: bool
    commitment_id: str | None = None
    lineage_ids: tuple[NonEmptyStr, ...]

    @field_validator("event_time", "available_at")
    @classmethod
    def aware_trajectory_time(cls, value: datetime) -> datetime:
        return _utc(value)


class LearningTrajectoryBundle(CanonicalArtifact):
    records: tuple[LearningTrajectoryRecord, ...]

    @model_validator(mode="after")
    def trajectory_point_in_time_safe(self) -> "LearningTrajectoryBundle":
        if any(item.available_at > self.as_of_time for item in self.records):
            raise ValueError("learning trajectory contains future information")
        return self
