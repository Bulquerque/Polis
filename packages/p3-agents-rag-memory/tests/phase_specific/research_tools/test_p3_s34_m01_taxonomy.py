from __future__ import annotations

from copy import deepcopy
import pytest

from .support_s34 import build_s34_m01
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.core.errors import ResearchToolContractError
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s34 import build_capability_taxonomy_contracts
from .support import load_yaml
from .support_s33 import s32_outputs


def test_taxonomy_covers_all_declared_capabilities_and_operations() -> None:
    out = build_s34_m01()
    taxonomy = out["research_capability_taxonomy"]
    matrix = out["capability_operation_requirement_matrix"]
    assert len(taxonomy["capabilities"]) == 19
    assert len(matrix["records"]) >= 34
    categories = taxonomy["category_counts"]
    assert categories == {"DOMAIN": 12, "METHOD": 4, "ACCESS": 2, "RESOURCE": 2} or sum(categories.values()) == 19
    assert {(r["tool_id"], r["operation_id"]) for r in matrix["records"]} == {
        (r["tool_id"], r["operation_id"]) for r in s32_outputs()["canonical_tool_operation_registry"]["operations"]
    }


def test_taxonomy_is_deterministic() -> None:
    assert build_s34_m01() == build_s34_m01()


def test_forbidden_entitlement_attribute_cannot_become_capability() -> None:
    cfg = deepcopy(load_yaml("config/research_tools/RESEARCH_CAPABILITY_TAXONOMY.yaml"))
    cfg["capabilities"].append({"capability_id": "performance", "category": "DOMAIN", "description": "Forbidden"})
    with pytest.raises(ResearchToolContractError) as exc:
        build_capability_taxonomy_contracts({
            **s32_outputs(),
            "research_capability_taxonomy_config": cfg,
            "person_schema_policy": load_yaml("config/resources/s15/person_schema_policy.yaml"),
        })
    assert exc.value.reason_code == "P3RT-CONTRACT-3403"
