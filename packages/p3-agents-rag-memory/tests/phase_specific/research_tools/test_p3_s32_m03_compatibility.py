from __future__ import annotations

from copy import deepcopy

import pytest

from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.core.errors import ResearchToolContractError
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s32 import build_compatibility_overlay

from .support import build_m01, build_m03, legacy_inputs, load_yaml


def test_real_s15_s16_inputs_are_projected_without_false_external_qualification():
    out = build_m03()
    providers = {item["provider_id"]: item for item in out["provider_transport_overlay"]["providers"]}
    assert providers["internal_research"]["availability"] == "QUALIFIED_LOCAL"
    assert providers["quant_local"]["availability"] == "QUALIFIED_LOCAL"
    assert providers["research_mcp"]["availability"] == "OPTIONAL_NOT_CONFIGURED"
    assert providers["disconnected_vendor"]["availability"] == "OPTIONAL_NOT_CONFIGURED"
    assert out["provider_transport_overlay"]["global_visible_call_limit"] <= 5
    assert out["legacy_contract_projection_report"]["external_providers_downgraded"] == 2


def test_aliases_resolve_to_single_canonical_operation():
    out = build_m03()
    aliases = {item["alias_tool_id"]: item for item in out["compatibility_alias_registry"]["aliases"]}
    assert aliases["research.search_filings.v1"]["target_tool_id"] == "research.corpus.v1"
    assert aliases["quant.realized_volatility.v1"]["target_operation_id"] == "realized_volatility"
    assert all(item["second_handler_forbidden"] for item in aliases.values())


def test_secret_material_is_rejected_even_when_nested():
    import asyncio
    registry, _, providers, policy = asyncio.run(legacy_inputs())
    m01 = build_m01()
    provider_payload = providers.model_dump(mode="python")
    provider_payload["adapters"][0]["metadata"] = {"nested": {"api_key": ["secret"]}}
    with pytest.raises(ResearchToolContractError):
        build_compatibility_overlay({
            "tool_registry": registry,
            "mcp_gateway_policy": policy,
            "provider_adapter_registry_config": provider_payload,
            "canonical_research_tool_catalog": m01["canonical_research_tool_catalog"],
            "canonical_tool_operation_registry": m01["canonical_tool_operation_registry"],
            "compatibility_alias_config": load_yaml("config/research_tools/COMPATIBILITY_ALIASES.yaml"),
        })


def test_duplicate_alias_rejected():
    import asyncio
    registry, _, providers, policy = asyncio.run(legacy_inputs())
    m01 = build_m01()
    aliases = load_yaml("config/research_tools/COMPATIBILITY_ALIASES.yaml")
    aliases["aliases"].append(deepcopy(aliases["aliases"][0]))
    with pytest.raises(ResearchToolContractError):
        build_compatibility_overlay({
            "tool_registry": registry,
            "mcp_gateway_policy": policy,
            "provider_adapter_registry_config": providers,
            "canonical_research_tool_catalog": m01["canonical_research_tool_catalog"],
            "canonical_tool_operation_registry": m01["canonical_tool_operation_registry"],
            "compatibility_alias_config": aliases,
        })
