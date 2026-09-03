from __future__ import annotations

from time import perf_counter

from ....shared.artifact_hashing import compute_artifact_hash as _compute_artifact_hash
from .canonical import content_hash, sha256_bytes
from .errors import ErrorCategory, InvariantViolationError, error
from .models import (
    ArtifactStatus,
    Capability,
    CapabilityStatus,
    ProviderRegistry,
    ProviderStatus,
    RagIndexArtifact,
    RetrievalConfig,
    RetrievalIndexManifest,
)
from .ports import ArtifactStorePort, EventSinkPort



def compute_artifact_hash(value: object) -> str:
    """Hash an artifact using this capability's canonical JSON policy."""
    return _compute_artifact_hash(value, hasher=content_hash)

class RetrievalIndexManifestBuilder:
    MODULE_ID = "P3.S12.M02"

    def __init__(self, *, artifact_store: ArtifactStorePort, event_sink: EventSinkPort) -> None:
        self._artifact_store = artifact_store
        self._events = event_sink

    def run(
        self,
        *,
        rag_index: RagIndexArtifact,
        retrieval_config: RetrievalConfig,
        provider_registry: ProviderRegistry,
    ) -> RetrievalIndexManifest:
        started = perf_counter()
        dimensions = {"run_id": rag_index.run_id, "module_id": self.MODULE_ID, "snapshot_id": rag_index.snapshot_id}
        self._events.emit("module_started", dimensions)
        try:
            if compute_artifact_hash(rag_index) != rag_index.content_hash:
                raise InvariantViolationError(
                    error(
                        "P3_S12_M02_RAG_ARTIFACT_HASH_MISMATCH",
                        ErrorCategory.INVARIANT,
                        "rag_index_artifact envelope hash is not recomputable",
                    )
                )
            resolved_config_hash = content_hash(retrieval_config)
            if rag_index.configuration_hash != resolved_config_hash:
                raise InvariantViolationError(
                    error(
                        "P3_S12_M02_CONFIGURATION_HASH_MISMATCH",
                        ErrorCategory.INVARIANT,
                        "retrieval_config differs from the configuration used by M01",
                    )
                )
            refs = {
                component.name: component.artifact_ref
                for component in (rag_index.chunk_catalog, rag_index.keyword_index, rag_index.vector_index)
                if component.artifact_ref is not None
            }
            for name, reference in refs.items():
                content = self._artifact_store.get_bytes(reference)
                if sha256_bytes(content) != reference.content_hash:
                    raise InvariantViolationError(
                        error(
                            "P3_S12_M02_ARTIFACT_HASH_MISMATCH",
                            ErrorCategory.INVARIANT,
                            "index component hash mismatch",
                            context={"component": name},
                        )
                    )

            capabilities: list[Capability] = [
                Capability(
                    capability_id="keyword_retrieval",
                    status=rag_index.keyword_index.status,
                    provider_id=None,
                    snapshot_id=rag_index.keyword_index.snapshot_id,
                    supported_filters=rag_index.keyword_index.supported_filters,
                    qualification_status=rag_index.keyword_index.qualification_status,
                    reason_code=rag_index.keyword_index.reason_code,
                ),
                Capability(
                    capability_id="semantic_retrieval",
                    status=rag_index.vector_index.status,
                    provider_id=_embedding_provider_id(rag_index, provider_registry),
                    model_id=rag_index.vector_index.model_id,
                    model_revision=rag_index.vector_index.model_revision,
                    dimensions=rag_index.vector_index.dimensions,
                    snapshot_id=rag_index.vector_index.snapshot_id,
                    supported_filters=rag_index.vector_index.supported_filters,
                    qualification_status=rag_index.vector_index.qualification_status,
                    reason_code=rag_index.vector_index.reason_code,
                ),
                _reranker_capability(retrieval_config, provider_registry),
                Capability(
                    capability_id="available_at_filtering",
                    status=(
                        CapabilityStatus.READY
                        if "available_at" in rag_index.keyword_index.supported_filters
                        else CapabilityStatus.DISABLED
                    ),
                    provider_id=None,
                    supported_filters=("available_at",),
                    qualification_status="IMPLEMENTED_QUALIFIED_INTERNAL",
                    reason_code=None,
                ),
            ]
            issues = list(rag_index.issues)
            semantic = next(item for item in capabilities if item.capability_id == "semantic_retrieval")
            fallback = None
            if semantic.status != CapabilityStatus.READY:
                if retrieval_config.allow_lexical_fallback and rag_index.keyword_index.status == CapabilityStatus.READY:
                    fallback = "DETERMINISTIC_KEYWORD_ONLY"
                elif rag_index.status != ArtifactStatus.EMPTY:
                    raise InvariantViolationError(
                        error(
                            "P3_S12_M02_CAPABILITY_INCONSISTENT",
                            ErrorCategory.INVARIANT,
                            "semantic retrieval unavailable without permitted fallback",
                        )
                    )

            base = {
                "artifact_name": "retrieval_index_manifest",
                "schema_id": "retrieval_index_manifest.v2",
                "schema_version": "2.0.0",
                "run_id": rag_index.run_id,
                "snapshot_id": rag_index.snapshot_id,
                "as_of_time": rag_index.as_of_time,
                "lineage_id": rag_index.lineage_id,
                "status": rag_index.status,
                "rag_index_artifact_hash": rag_index.content_hash,
                "chunk_schema_id": rag_index.chunk_schema_id,
                "chunk_count": rag_index.coverage.chunk_count,
                "capabilities": tuple(capabilities),
                "artifact_refs": refs,
                "required_metadata_filters": retrieval_config.required_metadata_filters,
                "configuration_hash": resolved_config_hash,
                "provider_fingerprints": rag_index.provider_fingerprints,
                "fallback_strategy": fallback,
                "issues": tuple(issues),
            }
            digest = compute_artifact_hash(base)
            manifest = RetrievalIndexManifest(
                artifact_id=f"retrieval_manifest_{digest[:20]}",
                content_hash=digest,
                **base,
            )
            self._events.emit(
                "module_succeeded",
                {
                    **dimensions,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                    "output_record_count": len(capabilities),
                    "warning_count": len(issues),
                    "error_count": 0,
                },
            )
            return manifest
        except Exception as exc:
            self._events.emit(
                "module_failed",
                {**dimensions, "duration_ms": round((perf_counter() - started) * 1000, 3), "error_type": type(exc).__name__},
            )
            raise


def _embedding_provider_id(rag_index: RagIndexArtifact, registry: ProviderRegistry) -> str | None:
    for provider_id in rag_index.provider_fingerprints:
        descriptor = registry.find(provider_id, "EmbeddingProvider")
        if descriptor is not None:
            return descriptor.provider_id
    return next(iter(rag_index.provider_fingerprints), None)


def _reranker_capability(config: RetrievalConfig, registry: ProviderRegistry) -> Capability:
    if not config.reranker.enabled:
        return Capability(
            capability_id="reranking",
            status=CapabilityStatus.DISABLED,
            provider_id=config.reranker.provider_id,
            qualification_status="DISABLED",
            reason_code="RERANKER_DISABLED",
        )
    if config.reranker.provider_id is None:
        return Capability(
            capability_id="reranking",
            status=CapabilityStatus.DISCONNECTED,
            provider_id=None,
            qualification_status="UNQUALIFIED",
            reason_code="RERANKER_PROVIDER_NOT_DECLARED",
        )
    descriptor = registry.find(config.reranker.provider_id, "RerankerProvider")
    if descriptor is None:
        return Capability(
            capability_id="reranking",
            status=CapabilityStatus.DISCONNECTED,
            provider_id=config.reranker.provider_id,
            qualification_status="UNQUALIFIED",
            reason_code="RERANKER_PROVIDER_NOT_REGISTERED",
        )
    status_map = {
        ProviderStatus.CONNECTED_QUALIFIED: CapabilityStatus.READY,
        ProviderStatus.CONNECTED_UNQUALIFIED: CapabilityStatus.UNQUALIFIED,
        ProviderStatus.CONFIGURED_DISCONNECTED: CapabilityStatus.DISCONNECTED,
        ProviderStatus.DISABLED: CapabilityStatus.DISABLED,
        ProviderStatus.FAILED: CapabilityStatus.DISCONNECTED,
        ProviderStatus.NOT_APPLICABLE: CapabilityStatus.NOT_APPLICABLE,
    }
    return Capability(
        capability_id="reranking",
        status=status_map[descriptor.status],
        provider_id=descriptor.provider_id,
        model_id=descriptor.model_id,
        model_revision=descriptor.model_revision,
        qualification_status=descriptor.qualification_status,
        reason_code=None if descriptor.status == ProviderStatus.CONNECTED_QUALIFIED else descriptor.status.value,
    )
