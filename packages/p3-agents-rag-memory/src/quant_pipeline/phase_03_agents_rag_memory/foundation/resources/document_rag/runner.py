from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .compatibility import (
    normalize_pit_context,
    normalize_provider_registry,
    normalize_retrieval_config,
    normalize_run_snapshot,
)
from .models import RagIndexArtifact, RetrievalIndexManifest
from .module_m01 import DocumentChunkerAndIndexer
from .module_m02 import RetrievalIndexManifestBuilder


@dataclass(frozen=True, slots=True)
class P3S12Result:
    rag_index_artifact: RagIndexArtifact
    retrieval_index_manifest: RetrievalIndexManifest


class P3S12Runner:
    def __init__(self, *, module_m01: DocumentChunkerAndIndexer, module_m02: RetrievalIndexManifestBuilder) -> None:
        self._m01 = module_m01
        self._m02 = module_m02

    async def run(self, inputs: dict[str, Any]) -> P3S12Result:
        context = normalize_pit_context(inputs["pit_validated_context"])
        snapshot = normalize_run_snapshot(inputs["phase3_run_snapshot"])
        config = normalize_retrieval_config(inputs["retrieval_config"])
        providers = normalize_provider_registry(inputs["provider_adapter_registry_config"])
        rag = await self._m01.run(
            context=context,
            snapshot=snapshot,
            retrieval_config=config,
            provider_registry=providers,
        )
        manifest = self._m02.run(
            rag_index=rag,
            retrieval_config=config,
            provider_registry=providers,
        )
        return P3S12Result(rag_index_artifact=rag, retrieval_index_manifest=manifest)
