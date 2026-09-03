from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from quant_pipeline.phase_03_agents_rag_memory.contracts.base import ContractModel

from .types import (
    ContentMode,
    CorpusMode,
    EvidenceDirection,
    NonEmptyStr,
    OutcomeStatus,
    Probability,
    RelationCertainty,
    Sha256,
    aware_utc,
)


class SearchHit(ContractModel):
    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    source_id: NonEmptyStr
    sequence_number: int = Field(ge=0)
    content: NonEmptyStr
    content_hash: Sha256
    available_at: datetime
    event_time: datetime | None = None
    effective_time: datetime | None = None
    source_quality: Probability
    entities: tuple[str, ...] = ()
    underlyings: tuple[str, ...] = ()
    lineage_refs: tuple[str, ...] = ()
    lexical_score: float = Field(ge=0.0)
    semantic_score: float | None = Field(default=None, ge=0.0)
    fused_score: float = Field(ge=0.0)
    rerank_score: float | None = None
    rank: int = Field(gt=0)

    _available = field_validator("available_at")(aware_utc)
    _event = field_validator("event_time", "effective_time")(aware_utc)


class DocumentResult(ContractModel):
    document_id: NonEmptyStr
    source_ids: tuple[NonEmptyStr, ...]
    content: str | None
    content_mode: ContentMode
    chunk_ids: tuple[NonEmptyStr, ...]
    available_at: datetime
    event_time: datetime | None = None
    effective_time: datetime | None = None
    source_quality: Probability
    entities: tuple[str, ...] = ()
    underlyings: tuple[str, ...] = ()
    lineage_refs: tuple[str, ...] = ()
    document_hash: Sha256

    _available = field_validator("available_at")(aware_utc)
    _event = field_validator("event_time", "effective_time")(aware_utc)

    @model_validator(mode="after")
    def content_mode_is_consistent(self) -> "DocumentResult":
        if self.content_mode is ContentMode.METADATA_ONLY and self.content is not None:
            raise ValueError("metadata-only document cannot include content")
        if self.content_mode is not ContentMode.METADATA_ONLY and self.content is None:
            raise ValueError("content-bearing mode requires content")
        return self


class VersionDifference(ContractModel):
    change_type: Literal["ADDED", "REMOVED", "UNCHANGED"]
    token: NonEmptyStr
    left_count: int = Field(ge=0)
    right_count: int = Field(ge=0)


class VersionComparisonResult(ContractModel):
    left_document_id: NonEmptyStr
    right_document_id: NonEmptyStr
    left_hash: Sha256
    right_hash: Sha256
    lexical_similarity: Probability
    differences: tuple[VersionDifference, ...]
    version_graph_confirmed: bool


class ProvenanceNode(ContractModel):
    node_id: NonEmptyStr
    node_type: Literal["SOURCE", "P1_ARTIFACT", "P2_RECORD", "P3_CHUNK", "P3_RESULT"]
    content_hash: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ProvenanceEdge(ContractModel):
    source_node_id: NonEmptyStr
    target_node_id: NonEmptyStr
    relation: Literal["WAS_DERIVED_FROM", "WAS_ATTRIBUTED_TO", "WAS_GENERATED_BY"]


class ProvenanceResult(ContractModel):
    subject_id: NonEmptyStr
    nodes: tuple[ProvenanceNode, ...]
    edges: tuple[ProvenanceEdge, ...]
    complete_to_p1: bool

    @model_validator(mode="after")
    def graph_references_known_nodes(self) -> "ProvenanceResult":
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("provenance node IDs must be unique")
        for edge in self.edges:
            if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
                raise ValueError("provenance edge references an unknown node")
        return self


class CounterevidenceHit(ContractModel):
    proposition: NonEmptyStr
    counter_query: NonEmptyStr
    evidence_direction: Literal[EvidenceDirection.COUNTER] = EvidenceDirection.COUNTER
    hit: SearchHit


class TimelineEvent(ContractModel):
    event_id: NonEmptyStr
    document_id: NonEmptyStr
    source_id: NonEmptyStr
    event_time: datetime | None
    published_or_reference_time: datetime | None
    available_at: datetime
    summary: NonEmptyStr
    evidence_chunk_ids: tuple[NonEmptyStr, ...]
    relation_certainty: RelationCertainty = RelationCertainty.OBSERVED

    _times = field_validator(
        "event_time", "published_or_reference_time", "available_at"
    )(aware_utc)


class CorpusEvidenceRef(ContractModel):
    evidence_id: NonEmptyStr
    source_id: NonEmptyStr
    document_id: NonEmptyStr
    chunk_id: str | None = None
    available_at: datetime
    content_hash: Sha256
    source_quality: Probability
    lineage_refs: tuple[str, ...] = ()

    _available = field_validator("available_at")(aware_utc)


class CoverageReport(ContractModel):
    records_scanned: int = Field(ge=0)
    records_visible: int = Field(ge=0)
    records_returned: int = Field(ge=0)
    unique_documents: int = Field(ge=0)
    unique_sources: int = Field(ge=0)
    source_families: int = Field(ge=0)
    duplicate_records_removed: int = Field(ge=0)
    score: Probability
    missing_dimensions: tuple[str, ...] = ()
    truncated: bool = False

    @model_validator(mode="after")
    def counts_are_consistent(self) -> "CoverageReport":
        if self.records_visible > self.records_scanned:
            raise ValueError("records_visible cannot exceed records_scanned")
        if self.records_returned > self.records_visible:
            raise ValueError("records_returned cannot exceed records_visible")
        return self


class PitQueryProof(ContractModel):
    decision_time: datetime
    records_scanned: int = Field(ge=0)
    records_visible: int = Field(ge=0)
    records_rejected_future: int = Field(ge=0)
    records_rejected_filter: int = Field(ge=0)
    earliest_available_at: datetime | None = None
    latest_available_at: datetime | None = None
    snapshot_id: NonEmptyStr
    input_hashes: tuple[Sha256, ...]
    proof_hash: Sha256

    _decision = field_validator("decision_time")(aware_utc)
    _times = field_validator("earliest_available_at", "latest_available_at")(aware_utc)

    @model_validator(mode="after")
    def proof_is_consistent(self) -> "PitQueryProof":
        if self.latest_available_at and self.latest_available_at > self.decision_time:
            raise ValueError("PIT proof contains evidence after decision_time")
        if self.earliest_available_at and self.latest_available_at:
            if self.earliest_available_at > self.latest_available_at:
                raise ValueError("earliest_available_at cannot be after latest_available_at")
        accounted = (
            self.records_visible
            + self.records_rejected_future
            + self.records_rejected_filter
        )
        if accounted > self.records_scanned:
            raise ValueError("PIT proof record counts exceed records_scanned")
        if len(self.input_hashes) != len(set(self.input_hashes)):
            raise ValueError("PIT proof input hashes must be unique")
        return self


class ExecutionReport(ContractModel):
    handler_id: NonEmptyStr
    handler_version: NonEmptyStr
    requested_mode: CorpusMode
    executed_mode: CorpusMode
    internal_subqueries: int = Field(ge=0)
    internal_work_units: int = Field(ge=0)
    deterministic: bool
    seed: int = Field(ge=0)
    warnings: tuple[str, ...] = ()


class CorpusToolResultEnvelope(ContractModel):
    envelope_version: Literal["1.0.0"] = "1.0.0"
    tool_id: Literal["research.corpus.v1"] = "research.corpus.v1"
    operation_id: NonEmptyStr
    request_id: NonEmptyStr
    outcome_status: OutcomeStatus
    requested_mode: CorpusMode
    executed_mode: CorpusMode
    downgrade_reason: str | None = None
    records: tuple[dict[str, JsonValue], ...]
    evidence_refs: tuple[CorpusEvidenceRef, ...]
    coverage: CoverageReport
    provenance: ProvenanceResult | None = None
    pit_proof: PitQueryProof
    execution: ExecutionReport
    result_hash: Sha256

    @model_validator(mode="after")
    def envelope_is_consistent(self) -> "CorpusToolResultEnvelope":
        if self.executed_mode is not self.requested_mode and self.downgrade_reason is None:
            raise ValueError("mode downgrade requires downgrade_reason")
        if self.executed_mode is self.requested_mode and self.downgrade_reason is not None:
            raise ValueError("downgrade_reason requires an executed mode change")
        if self.outcome_status is OutcomeStatus.EMPTY_VALID and self.records:
            raise ValueError("EMPTY_VALID result cannot contain records")
        if self.coverage.records_returned != len(self.records):
            raise ValueError("coverage records_returned must match result records")
        if self.execution.requested_mode is not self.requested_mode:
            raise ValueError("execution requested_mode must match envelope")
        if self.execution.executed_mode is not self.executed_mode:
            raise ValueError("execution executed_mode must match envelope")
        return self
