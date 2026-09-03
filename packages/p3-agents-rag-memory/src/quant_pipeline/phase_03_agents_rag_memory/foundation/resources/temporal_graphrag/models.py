from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JsonScalar = str | int | float | bool | None


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, validate_default=True)


class ArtifactStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    EMPTY = "EMPTY"
    BLOCKED = "BLOCKED"


class CapabilityStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    DISCONNECTED = "DISCONNECTED"
    UNQUALIFIED = "UNQUALIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ProviderStatus(StrEnum):
    CONNECTED_QUALIFIED = "CONNECTED_QUALIFIED"
    CONNECTED_UNQUALIFIED = "CONNECTED_UNQUALIFIED"
    CONFIGURED_DISCONNECTED = "CONFIGURED_DISCONNECTED"
    DISABLED = "DISABLED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class NodeType(StrEnum):
    SOURCE = "SOURCE"
    DOCUMENT = "DOCUMENT"
    CHUNK = "CHUNK"
    ENTITY = "ENTITY"
    ORGANIZATION = "ORGANIZATION"
    PERSON = "PERSON"
    UNDERLYING = "UNDERLYING"
    EVENT = "EVENT"
    CLAIM = "CLAIM"
    TOPIC = "TOPIC"
    MACRO_INDICATOR = "MACRO_INDICATOR"


class RelationType(StrEnum):
    PUBLISHED_BY = "PUBLISHED_BY"
    CONTAINS = "CONTAINS"
    MENTIONS = "MENTIONS"
    REFERS_TO = "REFERS_TO"
    DESCRIBES = "DESCRIBES"
    INVOLVES = "INVOLVES"
    CO_OCCURS_WITH = "CO_OCCURS_WITH"
    SUPPORTS = "SUPPORTS"
    OPPOSES = "OPPOSES"
    RELATED_TO = "RELATED_TO"
    AFFECTS = "AFFECTS"


class EvidenceRole(StrEnum):
    PROVENANCE = "PROVENANCE"
    SUPPORT = "SUPPORT"
    OPPOSITION = "OPPOSITION"
    MENTION = "MENTION"
    DEFINITION = "DEFINITION"
    TEMPORAL_CONTEXT = "TEMPORAL_CONTEXT"
    CAUSAL_CONTEXT = "CAUSAL_CONTEXT"


class EvidenceOrigin(StrEnum):
    STRUCTURED_METADATA = "STRUCTURED_METADATA"
    TEXT_SPAN = "TEXT_SPAN"
    PROVIDER_PROPOSAL = "PROVIDER_PROPOSAL"


class ExtractionMethod(StrEnum):
    STRUCTURED_RULE = "STRUCTURED_RULE"
    CO_OCCURRENCE_RULE = "CO_OCCURRENCE_RULE"
    PROVIDER_STRUCTURED_OUTPUT = "PROVIDER_STRUCTURED_OUTPUT"


class ConflictStatus(StrEnum):
    NONE = "NONE"
    DISPUTED = "DISPUTED"


class GraphElementType(StrEnum):
    NODE = "NODE"
    EDGE = "EDGE"


class RecordFormat(StrEnum):
    JSONL = "JSONL"
    PARQUET = "PARQUET"


class PublicationStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PUBLISHED = "PUBLISHED"
    FAILED_OPTIONAL = "FAILED_OPTIONAL"
    BLOCKED = "BLOCKED"


class ArtifactRef(StrictModel):
    artifact_type: str
    uri: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str
    size_bytes: int = Field(ge=0)
    record_count: int | None = Field(default=None, ge=0)
    format_version: str


class Chunk(StrictModel):
    chunk_id: str
    document_id: str
    source_id: str
    sequence_number: int = Field(ge=0)
    start_word: int = Field(ge=0)
    end_word: int = Field(gt=0)
    content: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_time: datetime | None = None
    effective_time: datetime | None = None
    available_at: datetime
    source_quality: Annotated[float, Field(ge=0.0, le=1.0)]
    entities: tuple[str, ...]
    underlyings: tuple[str, ...]
    lineage_refs: tuple[str, ...]
    chunker_version: str

    @field_validator("event_time", "effective_time", "available_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value


class IndexComponent(StrictModel):
    name: str
    status: CapabilityStatus
    artifact_ref: ArtifactRef | None
    adapter_id: str
    adapter_version: str
    model_id: str | None = None
    model_revision: str | None = None
    dimensions: int | None = Field(default=None, ge=1)
    record_count: int = Field(ge=0)
    snapshot_id: str | None = None
    supported_filters: tuple[str, ...] = ()
    qualification_status: str
    reason_code: str | None = None


class RagCoverage(StrictModel):
    source_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    rejected_document_count: int = Field(ge=0)
    rejected_chunk_count: int = Field(ge=0)


class RagIndexArtifact(StrictModel):
    artifact_name: Literal["rag_index_artifact"] = "rag_index_artifact"
    schema_id: Literal["rag_index_artifact.v2"] = "rag_index_artifact.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: str
    run_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ArtifactStatus
    reason_code: str | None = None
    grain: tuple[str, ...] = ("chunk_id",)
    primary_key: tuple[str, ...] = ("chunk_id",)
    chunk_schema_id: Literal["rag_chunk.v1"] = "rag_chunk.v1"
    chunk_catalog: IndexComponent
    keyword_index: IndexComponent
    vector_index: IndexComponent
    coverage: RagCoverage
    configuration_hash: str
    provider_fingerprints: dict[str, str]
    issues: tuple[str, ...] = ()

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware as_of_time required")
        return value


class DocumentRecord(StrictModel):
    record_type: Literal["document"]
    document_id: str
    source_id: str
    content: str
    event_time: datetime | None = None
    effective_time: datetime | None = None
    available_at: datetime
    ingested_at: datetime | None = None
    source_quality: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    entities: tuple[str, ...] = ()
    underlyings: tuple[str, ...] = ()
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)
    lineage_refs: tuple[str, ...] = ()

    @field_validator("event_time", "effective_time", "available_at", "ingested_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value


class PitValidatedContext(StrictModel):
    schema_id: str
    schema_version: str
    records: tuple[DocumentRecord, ...]
    lineage_id: str


class RunSnapshot(StrictModel):
    schema_id: str
    schema_version: str
    run_id: str
    snapshot_id: str
    as_of_time: datetime
    pipeline_version: str
    architecture_revision: str
    config_hashes: dict[str, str]
    provider_fingerprints: dict[str, str]
    timezone: str = "UTC"

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware as_of_time required")
        return value


class ProviderDescriptor(StrictModel):
    provider_id: str
    interface_id: str
    adapter_id: str
    adapter_version: str
    status: ProviderStatus
    model_id: str | None = None
    model_revision: str | None = None
    supports_json_schema: bool = False
    supports_batching: bool = False
    supports_temporal_metadata: bool = False
    supports_snapshot_pin: bool = False
    qualification_status: str
    fingerprint: str
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)


class ProviderRegistry(StrictModel):
    schema_id: str
    schema_version: str
    providers: tuple[ProviderDescriptor, ...]

    def find(self, provider_id: str, interface_id: str) -> ProviderDescriptor | None:
        return next((p for p in self.providers if p.provider_id == provider_id and p.interface_id == interface_id), None)


class ProposalSettings(StrictModel):
    enabled: bool = False
    required: bool = False
    provider_id: str | None = None
    min_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.80
    max_chunks_per_request: int = Field(default=8, ge=1, le=64)
    max_proposals_per_chunk: int = Field(default=8, ge=1, le=128)

    @model_validator(mode="after")
    def provider_when_enabled(self) -> "ProposalSettings":
        if self.enabled and not self.provider_id:
            raise ValueError("provider_id is required when proposals are enabled")
        return self


class PublicationSettings(StrictModel):
    enabled: bool = False
    required: bool = False
    adapter_id: str | None = None
    database: str | None = None

    @model_validator(mode="after")
    def adapter_when_enabled(self) -> "PublicationSettings":
        if self.enabled and not self.adapter_id:
            raise ValueError("adapter_id is required when publication is enabled")
        return self


class GraphConfig(StrictModel):
    schema_id: Literal["p3_s13_graph_config.v2"] = "p3_s13_graph_config.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    ontology_version: str = "p3_graph_ontology.v1"
    entity_resolution_version: str = "typed_exact_alias_v1"
    relation_rules_version: str = "structured_cooccurrence_v1"
    max_query_hops: int = Field(default=3, ge=1, le=8)
    edge_requires_evidence: bool = True
    temporal_edges_required: bool = True
    orphan_edge_policy: Literal["fail"] = "fail"
    conflict_policy: Literal["preserve_disputed"] = "preserve_disputed"
    record_format: RecordFormat = RecordFormat.JSONL
    low_quality_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.50
    provider_proposals: ProposalSettings = Field(default_factory=ProposalSettings)
    publication: PublicationSettings = Field(default_factory=PublicationSettings)


class GraphNode(StrictModel):
    node_id: str
    node_type: NodeType
    canonical_name: str
    aliases: tuple[str, ...] = ()
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    available_at: datetime
    attributes: dict[str, JsonScalar] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...]
    ontology_version: str
    resolution_key: str
    provenance: tuple[str, ...] = ()

    @field_validator("valid_from", "valid_to", "available_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value

    @model_validator(mode="after")
    def interval_valid(self) -> "GraphNode":
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        if not self.evidence_refs:
            raise ValueError("graph node requires evidence")
        return self


class GraphEdge(StrictModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: RelationType
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    available_at: datetime
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence_refs: tuple[str, ...]
    extraction_method: ExtractionMethod
    ontology_version: str
    conflict_group_id: str | None = None
    conflict_status: ConflictStatus = ConflictStatus.NONE
    provenance: tuple[str, ...] = ()

    @field_validator("valid_from", "valid_to", "available_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value

    @model_validator(mode="after")
    def edge_valid(self) -> "GraphEdge":
        if self.source_node_id == self.target_node_id:
            raise ValueError("self edges are not permitted")
        if not self.evidence_refs:
            raise ValueError("graph edge requires evidence")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not precede valid_from")
        return self


class GraphEvidenceAssertion(StrictModel):
    assertion_id: str
    graph_element_id: str
    graph_element_type: GraphElementType
    evidence_role: EvidenceRole
    evidence_origin: EvidenceOrigin
    chunk_id: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    span_start_word: int | None = Field(default=None, ge=0)
    span_end_word: int | None = Field(default=None, ge=1)
    quote_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    provenance: tuple[str, ...] = ()

    @model_validator(mode="after")
    def span_valid(self) -> "GraphEvidenceAssertion":
        if (self.span_start_word is None) != (self.span_end_word is None):
            raise ValueError("span start and end must be both set or both absent")
        if self.span_start_word is not None and self.span_end_word <= self.span_start_word:
            raise ValueError("span_end_word must be greater than span_start_word")
        return self


class GraphComponent(StrictModel):
    name: str
    status: CapabilityStatus
    artifact_ref: ArtifactRef
    adapter_id: str
    adapter_version: str
    record_count: int = Field(ge=0)
    format_version: str
    qualification_status: str


class GraphCoverage(StrictModel):
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    assertion_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    entity_count: int = Field(ge=0)
    event_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    rejected_proposal_count: int = Field(ge=0)


class PublicationResult(StrictModel):
    status: PublicationStatus
    adapter_id: str | None = None
    database: str | None = None
    published_node_count: int = Field(default=0, ge=0)
    published_edge_count: int = Field(default=0, ge=0)
    reason_code: str | None = None


class GraphRagArtifact(StrictModel):
    artifact_name: Literal["graph_rag_artifact"] = "graph_rag_artifact"
    schema_id: Literal["graph_rag_artifact.v2"] = "graph_rag_artifact.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: str
    run_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ArtifactStatus
    reason_code: str | None = None
    grain: tuple[str, ...] = ("graph_element_id",)
    ontology_version: str
    entity_resolution_version: str
    relation_rules_version: str
    rag_index_artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    nodes: GraphComponent
    edges: GraphComponent
    evidence_assertions: GraphComponent
    coverage: GraphCoverage
    publication: PublicationResult
    provider_fingerprints: dict[str, str]
    issues: tuple[str, ...] = ()

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware as_of_time required")
        return value


class ProposedNode(StrictModel):
    node_type: NodeType
    canonical_name: str
    aliases: tuple[str, ...] = ()
    chunk_ids: tuple[str, ...]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class ProposedEdge(StrictModel):
    source_type: NodeType
    source_name: str
    target_type: NodeType
    target_name: str
    relation_type: RelationType
    chunk_ids: tuple[str, ...]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class GraphProposalBatch(StrictModel):
    nodes: tuple[ProposedNode, ...] = ()
    edges: tuple[ProposedEdge, ...] = ()


class EvidenceRecord(StrictModel):
    evidence_record_id: str
    assertion_id: str
    graph_element_id: str
    graph_element_type: GraphElementType
    relation_type: RelationType | None = None
    evidence_role: EvidenceRole
    evidence_origin: EvidenceOrigin
    chunk_id: str
    document_id: str
    source_id: str
    event_time: datetime | None = None
    available_at: datetime
    source_quality: Annotated[float, Field(ge=0.0, le=1.0)]
    chunk_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    span_start_word: int | None = Field(default=None, ge=0)
    span_end_word: int | None = Field(default=None, ge=1)
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    lineage_refs: tuple[str, ...]

    @field_validator("event_time", "available_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value


class EvidenceCoverage(StrictModel):
    graph_element_count: int = Field(ge=0)
    fully_linked_count: int = Field(ge=0)
    partially_linked_count: int = Field(ge=0)
    orphan_count: int = Field(ge=0)
    future_evidence_count: int = Field(ge=0)
    low_quality_evidence_count: int = Field(ge=0)
    evidence_record_count: int = Field(ge=0)
    coverage_ratio: Annotated[float, Field(ge=0.0, le=1.0)]


class GraphEvidenceMap(StrictModel):
    artifact_name: Literal["graph_evidence_map"] = "graph_evidence_map"
    schema_id: Literal["graph_evidence_map.v2"] = "graph_evidence_map.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: str
    run_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ArtifactStatus
    graph_rag_artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rag_index_artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    records: GraphComponent
    coverage: EvidenceCoverage
    issues: tuple[str, ...] = ()

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware as_of_time required")
        return value
