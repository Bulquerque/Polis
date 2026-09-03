from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.core.errors import ResearchToolContractError
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s32 import build_mode_registry

from .support import build_m01, build_m02, load_yaml


def inputs():
    m01 = build_m01()
    return {
        "canonical_tool_operation_registry": m01["canonical_tool_operation_registry"],
        "operation_mode_registry_config": load_yaml("config/research_tools/OPERATION_MODE_REGISTRY.yaml"),
        "research_capability_taxonomy_config": load_yaml("config/research_tools/RESEARCH_CAPABILITY_TAXONOMY.yaml"),
    }


def test_all_operations_have_modes():
    out = build_m02()
    assert len(out["operation_mode_matrix"]["records"]) == 34
    assert out["research_mode_registry"]["mode_count"] == len(out["research_mode_registry"]["modes"])
    assert all(record["mode_ids"] for record in out["operation_mode_matrix"]["records"])


def test_assignment_order_is_irrelevant():
    payload = inputs()
    expected = build_mode_registry(payload)
    reordered = deepcopy(payload)
    reordered["operation_mode_registry_config"]["assignments"].reverse()
    assert build_mode_registry(reordered) == expected


def test_missing_assignment_rejected():
    payload = inputs()
    payload["operation_mode_registry_config"]["assignments"].pop()
    with pytest.raises(ResearchToolContractError):
        build_mode_registry(payload)


def test_unknown_capability_rejected():
    payload = inputs()
    payload["operation_mode_registry_config"]["templates"][0]["required_capabilities"] = [
        "not_a_capability"
    ]
    with pytest.raises(ResearchToolContractError):
        build_mode_registry(payload)


def test_downgrade_cycle_rejected():
    payload = inputs()
    assignment = next(
        item for item in payload["operation_mode_registry_config"]["assignments"]
        if len(item["mode_ids"]) >= 2
    )
    low, high = assignment["mode_ids"][0], assignment["mode_ids"][-1]
    assignment["downgrade_targets"] = {low: [high], high: [low]}
    with pytest.raises(ResearchToolContractError):
        build_mode_registry(payload)
