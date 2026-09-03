from __future__ import annotations

import asyncio

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.modules import (
    P3_S32_M01_canonical_research_tool_catalog_builder as m01,
    P3_S32_M02_research_mode_contract_registry_builder as m02,
    P3_S32_M03_legacy_tool_plane_compatibility_overlay_builder as m03,
    P3_S32_M04_extension_snapshot_manifest_builder as m04,
)

from .support import ROOT, legacy_inputs, load_yaml


def test_canonical_wrappers_execute_end_to_end():
    context = ModuleExecutionContext()
    out1 = asyncio.run(m01.execute({
        "research_tool_catalog_config": load_yaml("config/research_tools/RESEARCH_TOOL_CATALOG.yaml"),
        "provider_transport_bindings_config": load_yaml("config/research_tools/PROVIDER_TRANSPORT_BINDINGS.yaml"),
        "schema_bundle_manifest": load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST.yaml"),
        "extension_contract_version": "1.0.0",
    }, context))
    out2 = asyncio.run(m02.execute({
        "canonical_tool_operation_registry": out1["canonical_tool_operation_registry"],
        "operation_mode_registry_config": load_yaml("config/research_tools/OPERATION_MODE_REGISTRY.yaml"),
        "research_capability_taxonomy_config": load_yaml("config/research_tools/RESEARCH_CAPABILITY_TAXONOMY.yaml"),
    }, context))
    registry, _, providers, policy = asyncio.run(legacy_inputs())
    out3 = asyncio.run(m03.execute({
        "tool_registry": registry, "mcp_gateway_policy": policy,
        "provider_adapter_registry_config": providers, **out1,
        "compatibility_alias_config": load_yaml("config/research_tools/COMPATIBILITY_ALIASES.yaml"),
    }, context))
    out4 = asyncio.run(m04.execute({**out1, **out2, **out3,
        "schema_bundle_manifest": load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST.yaml"),
        "prompt_descriptor_template_manifest": load_yaml("config/research_tools/PROMPT_DESCRIPTOR_TEMPLATE_MANIFEST.yaml"),
        "extension_config_manifest": load_yaml("config/research_tools/EXTENSION_CONFIG_MANIFEST.yaml"),
    }, context))
    assert out4["research_tool_extension_snapshot"]["status"] == "READY"
