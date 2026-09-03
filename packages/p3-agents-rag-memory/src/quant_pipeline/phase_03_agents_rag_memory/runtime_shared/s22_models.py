from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from .s21_models import (
    ArtifactStatus,
    BeliefPayload,
    BeliefValueType,
    LineageRecord,
    NonEmptyStr,
    NonNegativeInt,
    Phase3RunSnapshot,
    Probability,
    PropositionRegistryConfig,
    RetrievalEvidenceMap,
    StrictModel,
    StructuredBeliefProposalPanel,
    StructuredBeliefProposalRecord,
    UTCDateTime,
    ValidatedToolResultPanel,
)

SCHEMA_VERSION = "p3.s22.v1"


class BeliefValidationStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED_PROPOSITION = "REJECTED_PROPOSITION"
    REJECTED_HORIZON = "REJECTED_HORIZON"
    REJECTED_PAYLOAD = "REJECTED_PAYLOAD"
    REJECTED_TEMPORAL = "REJECTED_TEMPORAL"
    REJECTED_DELTA_LIMIT = "REJECTED_DELTA_LIMIT"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"


class EvidenceBindingStatus(StrEnum):
    BOUND = "BOUND"
    UPSTREAM_REJECTED = "UPSTREAM_REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    FUTURE_EVIDENCE = "FUTURE_EVIDENCE"
    SUPPORT_OPPOSITION_OVERLAP = "SUPPORT_OPPOSITION_OVERLAP"


class EvidenceRelation(StrEnum):
    SUPPORTING = "SUPPORTING"
    OPPOSING = "OPPOSING"


class EvidenceSourceType(StrEnum):
    RETRIEVAL = "RETRIEVAL"
    GRAPH = "GRAPH"
    RAG = "RAG"
    TOOL = "TOOL"


class S22ArtifactPanel(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: ArtifactStatus = ArtifactStatus.READY
    lineage: LineageRecord
    reason_code: str | None = None


class CurrentBeliefStateRecord(StrictModel):
    belief_state_id: NonEmptyStr
    person_id: NonEmptyStr
    underlying_id: NonEmptyStr
    proposition_id: NonEmptyStr
    horizon: NonEmptyStr
    payload: BeliefPayload
    confidence: Probability
    uncertainty: Probability
    evidence_refs: tuple[NonEmptyStr, ...] = ()
    updated_at: UTCDateTime
    state_version: Annotated[int, Field(ge=1)] = 1


class CurrentBeliefStatePanel(S22ArtifactPanel):
    records: tuple[CurrentBeliefStateRecord, ...]


class BeliefDelta(StrictModel):
    value_type: BeliefValueType
    prior_payload: BeliefPayload | None = None
    accepted_payload: BeliefPayload
    scalar_delta: float | None = None
    component_deltas: dict[NonEmptyStr, float] = Field(default_factory=dict)
    distance_l1: Annotated[float, Field(ge=0.0)] = 0.0


class ValidatedBeliefUpdateRecord(StrictModel):
    belief_update_id: NonEmptyStr
    proposal: StructuredBeliefProposalRecord
    prior_state: CurrentBeliefStateRecord | None = None
    validation_status: BeliefValidationStatus
    reason_codes: tuple[NonEmptyStr, ...] = ()
    delta: BeliefDelta | None = None
    validated_at: UTCDateTime
    next_state_version: Annotated[int, Field(ge=1)]
    policy_version: NonEmptyStr


class ValidatedBeliefUpdatePanel(S22ArtifactPanel):
    records: tuple[ValidatedBeliefUpdateRecord, ...]


class GraphEvidenceRecord(StrictModel):
    evidence_id: NonEmptyStr
    source_id: NonEmptyStr
    edge_id: NonEmptyStr
    available_at: UTCDateTime
    content_hash: NonEmptyStr
    source_quality: Probability = 1.0
    path_node_ids: tuple[NonEmptyStr, ...] = ()


class GraphEvidenceMap(S22ArtifactPanel):
    records: tuple[GraphEvidenceRecord, ...]


class RagEvidenceRecord(StrictModel):
    evidence_id: NonEmptyStr
    source_id: NonEmptyStr
    chunk_id: NonEmptyStr
    available_at: UTCDateTime
    content_hash: NonEmptyStr
    source_quality: Probability = 1.0


class RagIndexArtifact(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    artifact_id: NonEmptyStr
    created_at: UTCDateTime
    as_of: UTCDateTime
    content_hash: NonEmptyStr
    records: tuple[RagEvidenceRecord, ...] = ()
    lineage: LineageRecord


class BoundEvidenceRecord(StrictModel):
    evidence_id: NonEmptyStr
    relation: EvidenceRelation
    source_type: EvidenceSourceType
    source_id: NonEmptyStr
    available_at: UTCDateTime
    content_hash: NonEmptyStr
    source_quality: Probability


class EvidenceBoundBeliefUpdateRecord(StrictModel):
    validated_update: ValidatedBeliefUpdateRecord
    binding_status: EvidenceBindingStatus
    supporting_evidence: tuple[BoundEvidenceRecord, ...] = ()
    opposing_evidence: tuple[BoundEvidenceRecord, ...] = ()
    unresolved_refs: tuple[NonEmptyStr, ...] = ()
    future_refs: tuple[NonEmptyStr, ...] = ()
    evidence_coverage: Probability = 0.0
    mean_source_quality: Probability = 0.0
    reason_codes: tuple[NonEmptyStr, ...] = ()
    bound_at: UTCDateTime


class EvidenceBoundBeliefUpdatePanel(S22ArtifactPanel):
    records: tuple[EvidenceBoundBeliefUpdateRecord, ...]


class BeliefOutcomeCommitmentRecord(StrictModel):
    commitment_id: NonEmptyStr
    person_id: NonEmptyStr
    subject: NonEmptyStr
    proposition: NonEmptyStr
    direction: NonEmptyStr
    strength: Probability
    confidence: Probability
    uncertainty: Probability
    horizon: NonEmptyStr
    value_payload: dict[str, JsonValue]
    evidence_refs: tuple[NonEmptyStr, ...]
    belief_update_id: NonEmptyStr
    run_id: NonEmptyStr
    cycle_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    generated_at: UTCDateTime
    committed_at: UTCDateTime
    matures_at: UTCDateTime
    commit_hash: NonEmptyStr
    lineage_id: NonEmptyStr

    @model_validator(mode="after")
    def maturity_after_commit(self) -> "BeliefOutcomeCommitmentRecord":
        if self.matures_at <= self.committed_at:
            raise ValueError("maturity must be after commitment")
        return self


class BeliefOutcomeCommitmentLog(S22ArtifactPanel):
    records: tuple[BeliefOutcomeCommitmentRecord, ...]


class BeliefPolicyConfig(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    policy_version: NonEmptyStr = "s22-policy-v1"
    allow_initial_belief: bool = True
    max_directional_score_delta: Annotated[float, Field(ge=0.0, le=2.0)] = 2.0
    max_volatility_level_delta: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    max_regime_l1_delta: Annotated[float, Field(ge=0.0, le=2.0)] = 2.0
    minimum_supporting_evidence: NonNegativeInt = 1
    tool_result_source_quality: Probability = 0.8
    horizon_calendar_days: dict[NonEmptyStr, Annotated[int, Field(gt=0)]] = Field(
        default_factory=lambda: {"1d": 1, "5d": 5, "21d": 21, "63d": 63, "252d": 252}
    )

    def maturity_delta(self, horizon: str) -> timedelta:
        try:
            days = self.horizon_calendar_days[horizon]
        except KeyError as exc:
            raise ValueError(f"missing maturity mapping for horizon: {horizon}") from exc
        return timedelta(days=days)


# Re-export exact upstream types for wrappers and schema generation.
__all__ = [
    "ArtifactStatus",
    "BeliefOutcomeCommitmentLog",
    "BeliefOutcomeCommitmentRecord",
    "BeliefPolicyConfig",
    "BeliefValidationStatus",
    "BoundEvidenceRecord",
    "CurrentBeliefStatePanel",
    "CurrentBeliefStateRecord",
    "EvidenceBindingStatus",
    "EvidenceBoundBeliefUpdatePanel",
    "EvidenceBoundBeliefUpdateRecord",
    "EvidenceRelation",
    "EvidenceSourceType",
    "GraphEvidenceMap",
    "GraphEvidenceRecord",
    "Phase3RunSnapshot",
    "PropositionRegistryConfig",
    "RagIndexArtifact",
    "RetrievalEvidenceMap",
    "StructuredBeliefProposalPanel",
    "ValidatedBeliefUpdatePanel",
    "ValidatedBeliefUpdateRecord",
    "ValidatedToolResultPanel",
]
