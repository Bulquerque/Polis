from __future__ import annotations

from pathlib import Path

import pytest

from quant_pipeline.phase_03_agents_rag_memory.shared.contracts import (
    FoundationGovernanceView,
    KnowledgeRuntimeView,
    MemoryRuntimeView,
    PopulationRuntimeView,
    SocialGraphRuntimeView,
    StateRuntimeView,
    ToolRuntimeView,
)


@pytest.fixture(scope="session")
def integration_fixture_root() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "integration_contract_pack"


def _load(model_type, root: Path, name: str):
    return model_type.model_validate_json((root / f"{name}.json").read_text(encoding="utf-8"), strict=True)


@pytest.fixture(scope="session")
def foundation_views(integration_fixture_root: Path):
    return {
        "governance": _load(FoundationGovernanceView, integration_fixture_root, "foundation_governance_view"),
        "population": _load(PopulationRuntimeView, integration_fixture_root, "population_runtime_view"),
        "social_graph": _load(SocialGraphRuntimeView, integration_fixture_root, "social_graph_runtime_view"),
        "state": _load(StateRuntimeView, integration_fixture_root, "state_runtime_view"),
        "knowledge": _load(KnowledgeRuntimeView, integration_fixture_root, "knowledge_runtime_view"),
        "memory": _load(MemoryRuntimeView, integration_fixture_root, "memory_runtime_view"),
        "tooling": _load(ToolRuntimeView, integration_fixture_root, "tool_runtime_view"),
    }
