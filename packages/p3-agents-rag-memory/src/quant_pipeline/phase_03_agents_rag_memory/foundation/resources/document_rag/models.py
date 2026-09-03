from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
    )


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


class ArtifactRef(StrictModel):
    artifact_type: str
    uri: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str
    size_bytes: int = Field(ge=0)
    record_count: int | None = Field(default=None, ge=0)
    format_version: str


class DocumentRecord(StrictModel):
    record_type: Literal["document"]
    document_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    content: str
    event_time: datetime | None = None
    effective_time: datetime | None = None
    available_at: datetime
    ingested_at: datetime | None = None
    source_quality: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    entities: tuple[str, ...] = ()
    underlyings: tuple[str, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    lineage_refs: tuple[str, ...] = ()

    @field_validator("event_time", "effective_time", "available_at", "ingested_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timezone-aware datetime required")
        return value


class PitValidatedContext(StrictModel):
    schema_id: str = "pit_validated_context.s12.v1"
    schema_version: str = "1.0.0"
    records: tuple[DocumentRecord, ...]
    lineage_id: str


class RunSnapshot(StrictModel):
    schema_id: str = "phase3_run_snapshot.s12.v1"
    schema_version: str = "1.0.0"
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


class ChunkingSettings(StrictModel):
    strategy: Literal["paragraph_word_window_v1"] = "paragraph_word_window_v1"
    max_words: int = Field(default=180, ge=16, le=4096)
    overlap_words: int = Field(default=30, ge=0, le=1024)
    min_words: int = Field(default=3, ge=1)
    normalization_version: str = "nfkc_lf_v1"

    @model_validator(mode="after")
    def overlap_smaller_than_window(self) -> "ChunkingSettings":
        if self.overlap_words >= self.max_words:
            raise ValueError("overlap_words must be smaller than max_words")
        return self


class EmbeddingSettings(StrictModel):
    enabled: bool = True
    semantic_required: bool = False
    provider_id: str = "offline_hashing"
    batch_size: int = Field(default=32, ge=1, le=1024)
    expected_dimensions: int | None = Field(default=None, ge=1)
    input_type: Literal["passage"] = "passage"
    truncate: Literal["NONE", "END"] = "NONE"


class RerankerSettings(StrictModel):
    enabled: bool = False
    provider_id: str | None = None
    required_when_connected: bool = True


class RetrievalConfig(StrictModel):
    schema_id: str = "p3_s12_retrieval_config.v1"
    schema_version: str = "1.0.0"
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    allow_lexical_fallback: bool = True
    keyword_tokenizer_version: str = "unicode_word_casefold_v1"
    required_metadata_filters: tuple[str, ...] = (
        "available_at",
        "source_id",
        "document_id",
        "underlyings",
        "entities",
    )


class ProviderDescriptor(StrictModel):
    provider_id: str
    interface_id: str
    adapter_id: str
    adapter_version: str
    status: ProviderStatus
    model_id: str | None = None
    model_revision: str | None = None
    dimensions: int | None = Field(default=None, ge=1)
    supports_batching: bool = False
    supports_available_at_filter: bool = False
    supports_snapshot_pin: bool = False
    qualification_status: str
    fingerprint: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class ProviderRegistry(StrictModel):
    schema_id: str = "provider_adapter_registry.s12.v1"
    schema_version: str = "1.0.0"
    providers: tuple[ProviderDescriptor, ...]

    def find(self, provider_id: str, interface_id: str) -> ProviderDescriptor | None:
        return next(
            (
                item
                for item in self.providers
                if item.provider_id == provider_id and item.interface_id == interface_id
            ),
            None,
        )


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


class Capability(StrictModel):
    capability_id: str
    status: CapabilityStatus
    provider_id: str | None
    model_id: str | None = None
    model_revision: str | None = None
    dimensions: int | None = Field(default=None, ge=1)
    snapshot_id: str | None = None
    supported_filters: tuple[str, ...] = ()
    qualification_status: str
    reason_code: str | None = None


class RetrievalIndexManifest(StrictModel):
    artifact_name: Literal["retrieval_index_manifest"] = "retrieval_index_manifest"
    schema_id: Literal["retrieval_index_manifest.v2"] = "retrieval_index_manifest.v2"
    schema_version: Literal["2.0.0"] = "2.0.0"
    artifact_id: str
    run_id: str
    snapshot_id: str
    as_of_time: datetime
    lineage_id: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: ArtifactStatus
    rag_index_artifact_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    chunk_schema_id: str
    chunk_count: int = Field(ge=0)
    capabilities: tuple[Capability, ...]
    artifact_refs: dict[str, ArtifactRef]
    required_metadata_filters: tuple[str, ...]
    configuration_hash: str
    provider_fingerprints: dict[str, str]
    fallback_strategy: str | None
    issues: tuple[str, ...] = ()

    @field_validator("as_of_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timezone-aware as_of_time required")
        return value


class EmbeddingBatch(StrictModel):
    vectors: tuple[tuple[float, ...], ...]
    provider: ProviderDescriptor
    request_hash: str


class VectorSnapshot(StrictModel):
    component: IndexComponent
