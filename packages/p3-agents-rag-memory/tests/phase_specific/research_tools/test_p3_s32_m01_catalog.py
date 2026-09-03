from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.core.errors import ResearchToolContractError
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s32 import build_canonical_catalog

from .support import build_m01, load_yaml


def base_inputs():
    return {
        "research_tool_catalog_config": load_yaml("config/research_tools/RESEARCH_TOOL_CATALOG.yaml"),
        "provider_transport_bindings_config": load_yaml("config/research_tools/PROVIDER_TRANSPORT_BINDINGS.yaml"),
        "schema_bundle_manifest": load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST.yaml"),
        "extension_contract_version": "1.0.0",
    }


def test_catalog_has_exact_canonical_surface():
    outputs = build_m01()
    catalog = outputs["canonical_research_tool_catalog"]
    operations = outputs["canonical_tool_operation_registry"]
    assert catalog["tool_count"] == 6 == len(catalog["tools"])
    assert operations["operation_count"] == 34 == len(operations["operations"])
    assert all(item["read_only"] and item["point_in_time_safe"] for item in operations["operations"])
    assert len({(item["tool_id"], item["operation_id"]) for item in operations["operations"]}) == 34


def test_catalog_is_order_invariant():
    inputs = base_inputs()
    expected = build_canonical_catalog(inputs)
    shuffled = deepcopy(inputs)
    shuffled["research_tool_catalog_config"]["tools"].reverse()
    for tool in shuffled["research_tool_catalog_config"]["tools"]:
        tool["operations"].reverse()
    assert build_canonical_catalog(shuffled) == expected


def test_duplicate_tool_is_rejected():
    inputs = base_inputs()
    inputs["research_tool_catalog_config"]["tools"].append(
        deepcopy(inputs["research_tool_catalog_config"]["tools"][0])
    )
    inputs["research_tool_catalog_config"]["expected_tool_count"] = 7
    inputs["research_tool_catalog_config"]["expected_operation_count"] += len(
        inputs["research_tool_catalog_config"]["tools"][0]["operations"]
    )
    with pytest.raises(ResearchToolContractError):
        build_canonical_catalog(inputs)


def test_missing_schema_is_rejected():
    inputs = base_inputs()
    inputs["research_tool_catalog_config"]["tools"][0]["operations"][0][
        "request_schema_ref"
    ] = "p3.missing.schema.v1"
    with pytest.raises(ResearchToolContractError):
        build_canonical_catalog(inputs)


def test_forbidden_authority_is_rejected():
    inputs = base_inputs()
    inputs["research_tool_catalog_config"]["tools"][0]["operations"][0][
        "forbidden_authorities"
    ] = []
    with pytest.raises(ResearchToolContractError):
        build_canonical_catalog(inputs)
