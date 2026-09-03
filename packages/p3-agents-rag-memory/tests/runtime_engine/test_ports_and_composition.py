from __future__ import annotations

from quant_pipeline.phase_03_agents_rag_memory.runtime_engine import build_runtime_composition
from quant_pipeline.phase_03_agents_rag_memory.runtime_engine.ports import (
    ArtifactStorePort,
    CheckpointPort,
    ClockPort,
    KnowledgeIndexPort,
    LLMPort,
    MemoryStorePort,
    SettingsPort,
    ToolGatewayPort,
)


def test_composition_builds_without_optional_dependencies() -> None:
    composition = build_runtime_composition()
    assert composition.production_promotion_allowed is False
    assert all(item.installed for item in composition.dependencies if item.required_for_core)


def test_public_ports_are_runtime_protocols() -> None:
    assert ClockPort is not None
    assert LLMPort is not None
    assert ToolGatewayPort is not None
    assert KnowledgeIndexPort is not None
    assert MemoryStorePort is not None
    assert ArtifactStorePort is not None
    assert CheckpointPort is not None
    assert SettingsPort is not None
