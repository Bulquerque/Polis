from __future__ import annotations

from .models import GraphConfig, PitValidatedContext, ProviderRegistry, RagIndexArtifact, RunSnapshot
from .module_m01 import TemporalGraphBuilder
from .module_m02 import GraphEvidenceLinker


class P3S13Runner:
    def __init__(self, *, m01: TemporalGraphBuilder, m02: GraphEvidenceLinker) -> None:
        self._m01 = m01
        self._m02 = m02

    async def run(self, *, rag_index: RagIndexArtifact, context: PitValidatedContext, snapshot: RunSnapshot, graph_config: GraphConfig, provider_registry: ProviderRegistry):
        graph = await self._m01.run(rag_index=rag_index, context=context, snapshot=snapshot, graph_config=graph_config, provider_registry=provider_registry)
        evidence = self._m02.run(graph=graph, rag_index=rag_index, graph_config=graph_config)
        return graph, evidence
