from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.resources.document_rag.adapters import (
    HashingEmbeddingProvider,
    InMemoryArtifactStore,
    JsonVectorStore,
    ListEventSink,
)
from ..foundation.resources.document_rag.compatibility import (
    normalize_pit_context,
    normalize_provider_registry,
    normalize_retrieval_config,
    normalize_run_snapshot,
)
from ..foundation.resources.document_rag.module_m01 import DocumentChunkerAndIndexer
from ..orchestration.execution_profiles import ExecutionProfile, resolve_execution_profile
from ._runtime import run_coroutine

MODULE_ID = "P3.S12.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "document_chunker_and_indexer"
SUBPHASE = "P3.S12"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S12.M01")
async def run_module_async(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic PIT-safe document index."""
    runtime = (config or {}).get("runtime", {})
    profile = resolve_execution_profile(config)
    artifact_store = runtime.get("artifact_store")
    embedding_provider = runtime.get("embedding_provider")
    vector_store = runtime.get("vector_store")
    if profile is not ExecutionProfile.TEST:
        missing = [
            name
            for name, value in (
                ("artifact_store", artifact_store),
                ("embedding_provider", embedding_provider),
                ("vector_store", vector_store),
            )
            if value is None
        ]
        if missing:
            raise RuntimeError(
                f"S12 {profile.value} requires injected persistent/qualified dependencies: {missing}"
            )
    service = DocumentChunkerAndIndexer(
        artifact_store=artifact_store or InMemoryArtifactStore(),
        embedding_provider=embedding_provider or HashingEmbeddingProvider(),
        vector_store=vector_store or JsonVectorStore(),
        event_sink=runtime.get("event_sink") or ListEventSink(),
    )
    artifact = await service.run(
        context=normalize_pit_context(inputs["pit_validated_context"]),
        snapshot=normalize_run_snapshot(inputs["phase3_run_snapshot"]),
        retrieval_config=normalize_retrieval_config(inputs["retrieval_config"]),
        provider_registry=normalize_provider_registry(
            inputs["provider_adapter_registry_config"]
        ),
    )
    return artifact.model_dump(mode="json")


@deprecated_legacy_entrypoint("P3.S12.M01")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return run_coroutine(run_module_async(inputs, config))

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S12_M01_document_chunker_and_indexer.yaml'
REQUIRED_INPUTS = ('pit_validated_context', 'phase3_run_snapshot', 'provider_adapter_registry_config', 'retrieval_config')
PRODUCED_OUTPUTS = ('rag_index_artifact',)
