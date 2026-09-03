from __future__ import annotations

from dataclasses import replace
from time import perf_counter

from .canonical import content_hash
from ....shared.artifact_hashing import compute_artifact_hash as _compute_artifact_hash
from .chunking import DeterministicChunker
from .errors import ErrorCategory, ProviderFailureError, error
from .indexing import build_keyword_index, persist_chunk_catalog, persist_keyword_index
from .models import (
    ArtifactStatus,
    CapabilityStatus,
    IndexComponent,
    PitValidatedContext,
    ProviderRegistry,
    ProviderStatus,
    RagCoverage,
    RagIndexArtifact,
    RetrievalConfig,
    RunSnapshot,
)
from .ports import ArtifactStorePort, EmbeddingProviderPort, EventSinkPort, VectorStorePort



def compute_artifact_hash(value: object) -> str:
    """Hash an artifact using this capability's canonical JSON policy."""
    return _compute_artifact_hash(value, hasher=content_hash)

class DocumentChunkerAndIndexer:
    MODULE_ID = "P3.S12.M01"

    def __init__(
        self,
        *,
        artifact_store: ArtifactStorePort,
        embedding_provider: EmbeddingProviderPort,
        vector_store: VectorStorePort,
        event_sink: EventSinkPort,
    ) -> None:
        self._artifact_store = artifact_store
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._events = event_sink

    def _build_lexical_components(
        self, *, chunks: tuple, retrieval_config: RetrievalConfig
    ) -> tuple[IndexComponent, IndexComponent]:
        chunk_ref = persist_chunk_catalog(chunks, self._artifact_store)
        keyword_index = build_keyword_index(chunks)
        keyword_ref = persist_keyword_index(keyword_index, self._artifact_store)
        filters = retrieval_config.required_metadata_filters
        chunk_component = IndexComponent(
            name="chunk_catalog",
            status=CapabilityStatus.READY if chunks else CapabilityStatus.NOT_APPLICABLE,
            artifact_ref=chunk_ref, adapter_id="jsonl_chunk_catalog", adapter_version="1.0.0",
            record_count=len(chunks), snapshot_id=chunk_ref.content_hash, supported_filters=filters,
            qualification_status="IMPLEMENTED_QUALIFIED_INTERNAL",
            reason_code=None if chunks else "EMPTY_CORPUS",
        )
        keyword_component = IndexComponent(
            name="keyword_index",
            status=CapabilityStatus.READY if chunks else CapabilityStatus.NOT_APPLICABLE,
            artifact_ref=keyword_ref, adapter_id="deterministic_inverted_index", adapter_version="1.0.0",
            record_count=len(keyword_index), snapshot_id=keyword_ref.content_hash, supported_filters=filters,
            qualification_status="QUALIFIED_LOCAL_BASELINE_ONLY",
            reason_code=None if chunks else "EMPTY_CORPUS",
        )
        return chunk_component, keyword_component

    async def _validated_provider(
        self, *, retrieval_config: RetrievalConfig, provider_registry: ProviderRegistry, snapshot: RunSnapshot
    ):
        provider = await self._embedding_provider.describe()
        configured_id = retrieval_config.embedding.provider_id
        declared = provider_registry.find(configured_id, "EmbeddingProvider")
        if retrieval_config.embedding.enabled and declared is None:
            raise ProviderFailureError(error(
                "P3_S12_M01_UNDECLARED_EMBEDDING_PROVIDER", ErrorCategory.PROVIDER,
                "embedding provider is not declared in provider_adapter_registry_config",
                context={"provider_id": configured_id},
            ))
        if provider.provider_id != configured_id:
            raise ProviderFailureError(error(
                "P3_S12_M01_PROVIDER_ID_MISMATCH", ErrorCategory.PROVIDER,
                "injected embedding adapter does not match retrieval_config provider_id",
                context={"configured_provider_id": configured_id, "runtime_provider_id": provider.provider_id},
            ))
        if retrieval_config.embedding.enabled and provider.provider_id not in snapshot.provider_fingerprints:
            raise ProviderFailureError(error(
                "P3_S12_M01_PROVIDER_NOT_FROZEN", ErrorCategory.PROVIDER,
                "embedding provider is absent from phase3_run_snapshot provider_fingerprints",
                context={"provider_id": provider.provider_id},
            ))
        return provider

    @staticmethod
    def _disabled_vector_component() -> IndexComponent:
        return IndexComponent(
            name="vector_index", status=CapabilityStatus.DISABLED, artifact_ref=None,
            adapter_id="none", adapter_version="1.0.0", record_count=0, supported_filters=(),
            qualification_status="DISABLED", reason_code="EMBEDDING_DISABLED",
        )

    async def _build_vector_component(
        self, *, chunks: tuple, retrieval_config: RetrievalConfig, provider
    ) -> tuple[IndexComponent, list[str]]:
        if not chunks or not retrieval_config.embedding.enabled:
            return self._disabled_vector_component(), []
        if provider.status in {ProviderStatus.CONNECTED_QUALIFIED, ProviderStatus.CONNECTED_UNQUALIFIED}:
            batch = await self._embedding_provider.embed_passages([chunk.content for chunk in chunks])
            expected = retrieval_config.embedding.expected_dimensions
            actual = len(batch.vectors[0]) if batch.vectors else batch.provider.dimensions
            if expected is not None and actual != expected:
                raise ProviderFailureError(error(
                    "P3_S12_M01_EMBEDDING_DIMENSION_MISMATCH", ErrorCategory.PROVIDER,
                    "embedding dimension differs from retrieval configuration",
                    context={"expected": expected, "actual": actual},
                ))
            component = (await self._vector_store.build(
                chunks=chunks, embeddings=batch, artifact_store=self._artifact_store,
                supported_filters=retrieval_config.required_metadata_filters,
            )).component
            return component, []
        if retrieval_config.embedding.semantic_required or not retrieval_config.allow_lexical_fallback:
            raise ProviderFailureError(error(
                "P3_S12_M01_EMBEDDING_PROVIDER_FAILURE", ErrorCategory.PROVIDER,
                "semantic indexing is required but embedding provider is unavailable",
                context={"provider_status": provider.status.value},
            ))
        component = IndexComponent(
            name="vector_index", status=CapabilityStatus.DISCONNECTED, artifact_ref=None,
            adapter_id=provider.adapter_id, adapter_version=provider.adapter_version,
            model_id=provider.model_id, model_revision=provider.model_revision, dimensions=provider.dimensions,
            record_count=0, supported_filters=(), qualification_status=provider.qualification_status,
            reason_code="LEXICAL_FALLBACK_PROVIDER_UNAVAILABLE",
        )
        return component, ["semantic_index_unavailable_lexical_fallback_active"]

    @staticmethod
    def _status_for(chunks: tuple, vector_component: IndexComponent) -> tuple[ArtifactStatus, str | None]:
        if not chunks:
            return ArtifactStatus.EMPTY, "EMPTY_CORPUS"
        if vector_component.status == CapabilityStatus.READY:
            return ArtifactStatus.READY, None
        return ArtifactStatus.DEGRADED, "LEXICAL_ONLY_DEGRADED"

    def _materialize_artifact(
        self, *, context: PitValidatedContext, snapshot: RunSnapshot, retrieval_config: RetrievalConfig,
        chunks: tuple, chunk_component: IndexComponent, keyword_component: IndexComponent,
        vector_component: IndexComponent, provider, issues: list[str]
    ) -> RagIndexArtifact:
        status, reason = self._status_for(chunks, vector_component)
        coverage = RagCoverage(
            source_count=len({doc.source_id for doc in context.records}),
            document_count=len(context.records), chunk_count=len(chunks),
            rejected_document_count=0, rejected_chunk_count=0,
        )
        base = {
            "artifact_name": "rag_index_artifact", "schema_id": "rag_index_artifact.v2",
            "schema_version": "2.0.0", "run_id": snapshot.run_id, "snapshot_id": snapshot.snapshot_id,
            "as_of_time": snapshot.as_of_time, "lineage_id": context.lineage_id, "status": status,
            "reason_code": reason, "grain": ("chunk_id",), "primary_key": ("chunk_id",),
            "chunk_schema_id": "rag_chunk.v1", "chunk_catalog": chunk_component,
            "keyword_index": keyword_component, "vector_index": vector_component, "coverage": coverage,
            "configuration_hash": content_hash(retrieval_config),
            "provider_fingerprints": {provider.provider_id: provider.fingerprint},
            "issues": tuple(issues),
        }
        digest = compute_artifact_hash(base)
        return RagIndexArtifact(artifact_id=f"rag_{digest[:24]}", content_hash=digest, **base)

    async def run(
        self, *, context: PitValidatedContext, snapshot: RunSnapshot,
        retrieval_config: RetrievalConfig, provider_registry: ProviderRegistry,
    ) -> RagIndexArtifact:
        started = perf_counter()
        dimensions = {"run_id": snapshot.run_id, "module_id": self.MODULE_ID, "snapshot_id": snapshot.snapshot_id}
        self._events.emit("module_started", dimensions)
        try:
            self._events.emit("input_contract_validated", dimensions)
            chunks = DeterministicChunker(retrieval_config.chunking).chunk_documents(context.records, snapshot)
            chunk_component, keyword_component = self._build_lexical_components(
                chunks=chunks, retrieval_config=retrieval_config
            )
            provider = await self._validated_provider(
                retrieval_config=retrieval_config, provider_registry=provider_registry, snapshot=snapshot
            )
            vector_component, issues = await self._build_vector_component(
                chunks=chunks, retrieval_config=retrieval_config, provider=provider
            )
            artifact = self._materialize_artifact(
                context=context, snapshot=snapshot, retrieval_config=retrieval_config, chunks=chunks,
                chunk_component=chunk_component, keyword_component=keyword_component,
                vector_component=vector_component, provider=provider, issues=issues,
            )
            self._events.emit("module_succeeded", {
                **dimensions, "duration_ms": round((perf_counter() - started) * 1000, 3),
                "input_record_count": len(context.records), "output_record_count": len(chunks),
                "warning_count": len(issues), "error_count": 0,
            })
            return artifact
        except Exception as exc:
            self._events.emit("module_failed", {
                **dimensions, "duration_ms": round((perf_counter() - started) * 1000, 3),
                "error_type": type(exc).__name__,
            })
            raise

