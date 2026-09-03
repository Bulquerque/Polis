from __future__ import annotations

from pathlib import Path

import yaml

from quant_pipeline.phase_03_agents_rag_memory.orchestration.runtime import execute_module


def test_executor_returns_uniform_envelope(root: Path) -> None:
    tag_config = yaml.safe_load(
        (root / "config/governance/PERSONALITY_TAG_REGISTRY.yaml").read_text(encoding="utf-8")
    )
    result = execute_module(
        "P3.S4.M01",
        {"personality_tag_registry_config": tag_config},
    )
    assert result.module_id == "P3.S4.M01"
    assert result.subphase_id == "P3.S4"
    assert "personality_tag_registry" in result.outputs
    assert result.production_promotion_allowed is False
