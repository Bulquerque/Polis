"""Publish a portable, reference-only foundation handoff for the runtime."""

from __future__ import annotations

from dataclasses import dataclass

from ..integration import JsonFileArtifactStore
from ..shared.contracts import (
    FoundationGovernanceView,
    FoundationRuntimeManifest,
    KnowledgeRuntimeView,
    MemoryRuntimeView,
    PopulationRuntimeView,
    RunIdentity,
    SocialGraphRuntimeView,
    StateRuntimeView,
    ToolRuntimeView,
    ArtifactPointer,
)
from .assembly import build_foundation_runtime_manifest


@dataclass(frozen=True, slots=True)
class FoundationViews:
    governance: FoundationGovernanceView
    population: PopulationRuntimeView
    social_graph: SocialGraphRuntimeView
    state: StateRuntimeView
    knowledge: KnowledgeRuntimeView
    memory: MemoryRuntimeView
    tooling: ToolRuntimeView


class FoundationHandoffPublisher:
    """Publish all foundation-to-runtime views and the final manifest into one portable directory."""

    def __init__(self, store: JsonFileArtifactStore) -> None:
        self._store = store

    def publish(
        self,
        *,
        identity: RunIdentity,
        views: FoundationViews,
        capabilities: tuple[str, ...],
        degraded_capabilities: tuple[str, ...] = (),
        blocking_reasons: tuple[str, ...] = (),
    ) -> tuple[FoundationRuntimeManifest, ArtifactPointer]:
        governance_ref = self._store.publish(views.governance, producer_module_id="P3.S4.M02")
        population_ref = self._store.publish(
            views.population,
            producer_module_id="P3.S7.M02",
            row_count=len(views.population.records),
            grain=("person_id",),
        )
        graph_ref = self._store.publish(
            views.social_graph,
            producer_module_id="P3.S8.M02",
            row_count=len(views.social_graph.records),
            grain=("source_person_id", "target_person_id", "relationship_type"),
        )
        state_ref = self._store.publish(views.state, producer_module_id="P3.S11.M03")
        knowledge_ref = self._store.publish(views.knowledge, producer_module_id="P3.S13.M02")
        memory_ref = self._store.publish(views.memory, producer_module_id="P3.S14.M02")
        tool_ref = self._store.publish(views.tooling, producer_module_id="P3.S16.M02")

        manifest = build_foundation_runtime_manifest(
            identity=identity,
            governance_view=views.governance,
            population_view=views.population,
            social_graph_view=views.social_graph,
            state_view=views.state,
            knowledge_view=views.knowledge,
            memory_view=views.memory,
            tool_view=views.tooling,
            capabilities=capabilities,
            degraded_capabilities=degraded_capabilities,
            blocking_reasons=blocking_reasons,
            governance_view_ref=governance_ref,
            population_view_ref=population_ref,
            social_graph_view_ref=graph_ref,
            state_view_ref=state_ref,
            knowledge_view_ref=knowledge_ref,
            memory_view_ref=memory_ref,
            tool_view_ref=tool_ref,
        )
        manifest_ref = self._store.publish(manifest, producer_module_id="P3.ORCHESTRATOR")
        return manifest, manifest_ref
