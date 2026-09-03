from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml

from tests.phase_specific.resource_support import ListEventSink, build_s15_outputs
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.models import (
    MCPGatewayPolicy,
    PersonToolEntitlementPanel,
    ProviderAdapterRegistry,
    ToolGatewayConfig,
    ToolRegistryArtifact,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.module_m01 import (
    MCPToolGatewayPolicyBuilder,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.s32 import (
    build_canonical_catalog,
    build_compatibility_overlay,
    build_extension_snapshot,
    build_mode_registry,
)

ROOT = Path(__file__).resolve().parents[3]


def load_yaml(relative: str) -> dict[str, Any]:
    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))


def build_m01() -> dict[str, Any]:
    return build_canonical_catalog({
        "research_tool_catalog_config": load_yaml("config/research_tools/RESEARCH_TOOL_CATALOG.yaml"),
        "provider_transport_bindings_config": load_yaml("config/research_tools/PROVIDER_TRANSPORT_BINDINGS.yaml"),
        "schema_bundle_manifest": load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST.yaml"),
        "extension_contract_version": "1.0.0",
    })


def build_m02(m01: dict[str, Any] | None = None) -> dict[str, Any]:
    m01 = m01 or build_m01()
    return build_mode_registry({
        "canonical_tool_operation_registry": m01["canonical_tool_operation_registry"],
        "operation_mode_registry_config": load_yaml("config/research_tools/OPERATION_MODE_REGISTRY.yaml"),
        "research_capability_taxonomy_config": load_yaml("config/research_tools/RESEARCH_CAPABILITY_TAXONOMY.yaml"),
    })


async def legacy_inputs() -> tuple[ToolRegistryArtifact, PersonToolEntitlementPanel, ProviderAdapterRegistry, MCPGatewayPolicy]:
    registry_raw, entitlement_raw, providers_raw, _ = await build_s15_outputs(ROOT)
    registry = ToolRegistryArtifact.model_validate(registry_raw, strict=False)
    entitlements = PersonToolEntitlementPanel.model_validate(entitlement_raw, strict=False)
    providers = ProviderAdapterRegistry.model_validate(providers_raw.model_dump(mode="python"), strict=False)
    config = ToolGatewayConfig.model_validate(
        load_yaml("config/resources/s16/tool_gateway_config.yaml"), strict=False
    )
    policy = MCPToolGatewayPolicyBuilder(event_sink=ListEventSink()).run(
        tool_registry=registry,
        person_tool_entitlement_panel=entitlements,
        tool_gateway_config=config,
        provider_adapter_registry_config=providers,
    )
    return registry, entitlements, providers, policy


def build_m03(m01: dict[str, Any] | None = None) -> dict[str, Any]:
    m01 = m01 or build_m01()
    registry, _, providers, policy = asyncio.run(legacy_inputs())
    return build_compatibility_overlay({
        "tool_registry": registry,
        "mcp_gateway_policy": policy,
        "provider_adapter_registry_config": providers,
        "canonical_research_tool_catalog": m01["canonical_research_tool_catalog"],
        "canonical_tool_operation_registry": m01["canonical_tool_operation_registry"],
        "compatibility_alias_config": load_yaml("config/research_tools/COMPATIBILITY_ALIASES.yaml"),
    })


def build_m04(
    m01: dict[str, Any] | None = None,
    m02: dict[str, Any] | None = None,
    m03: dict[str, Any] | None = None,
) -> dict[str, Any]:
    m01 = m01 or build_m01()
    m02 = m02 or build_m02(m01)
    m03 = m03 or build_m03(m01)
    return build_extension_snapshot({
        **m01,
        **m02,
        **m03,
        "schema_bundle_manifest": load_yaml("config/research_tools/SCHEMA_BUNDLE_MANIFEST.yaml"),
        "prompt_descriptor_template_manifest": load_yaml("config/research_tools/PROMPT_DESCRIPTOR_TEMPLATE_MANIFEST.yaml"),
        "extension_config_manifest": load_yaml("config/research_tools/EXTENSION_CONFIG_MANIFEST.yaml"),
    })
