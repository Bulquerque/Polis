from __future__ import annotations

from pathlib import Path

from quant_pipeline.phase_03_agents_rag_memory.integration import (
    FoundationManifestResolver,
    JsonFileArtifactStore,
)
from quant_pipeline.phase_03_agents_rag_memory.orchestration import (
    FoundationHandoffPublisher,
    FoundationViews,
)
from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import (
    FoundationGovernanceView,
    KnowledgeRuntimeView,
    MemoryRuntimeView,
    PopulationRuntimeView,
    SocialGraphRuntimeView,
    StateRuntimeView,
    ToolRuntimeView,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "integration_contract_pack"


def _load(name: str, model_type):
    return model_type.model_validate_json(
        (FIXTURES / name).read_text(encoding="utf-8"),
        strict=True,
    )


def test_portable_handoff_round_trip(tmp_path: Path) -> None:
    views = FoundationViews(
        governance=_load("foundation_governance_view.json", FoundationGovernanceView),
        population=_load("population_runtime_view.json", PopulationRuntimeView),
        social_graph=_load("social_graph_runtime_view.json", SocialGraphRuntimeView),
        state=_load("state_runtime_view.json", StateRuntimeView),
        knowledge=_load("knowledge_runtime_view.json", KnowledgeRuntimeView),
        memory=_load("memory_runtime_view.json", MemoryRuntimeView),
        tooling=_load("tool_runtime_view.json", ToolRuntimeView),
    )
    store = JsonFileArtifactStore(tmp_path)
    manifest, manifest_ref = FoundationHandoffPublisher(store).publish(
        identity=views.governance.identity,
        views=views,
        capabilities=("population", "knowledge", "memory", "tools"),
    )

    assert store.resolve(manifest_ref, type(manifest)) == manifest
    context = FoundationManifestResolver(store).resolve(manifest)
    assert context.population.population_id == views.population.population_id
    assert context.social_graph.records[0].strength == views.social_graph.records[0].strength
    assert len(list(tmp_path.glob("*.json"))) == 8
