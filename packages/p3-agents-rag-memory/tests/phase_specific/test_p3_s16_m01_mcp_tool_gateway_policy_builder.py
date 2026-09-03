import pytest
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.models import ToolGatewayConfig
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.module_m01 import MCPToolGatewayPolicyBuilder
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S16_M01_mcp_tool_gateway_policy_builder import run_module
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.resources_internal import entitlements_to_gateway, provider_registry_to_gateway, tool_registry_to_gateway
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.models import ToolRegistryArtifact, PersonToolEntitlementPanel
from .resource_support import build_s15_outputs, load_yaml, ListEventSink

@pytest.mark.asyncio
async def test_gateway_policy_preserves_s15_hashes(root):
    registry_raw, entitlements_raw, providers, _ = await build_s15_outputs(root)
    registry = ToolRegistryArtifact.model_validate(registry_raw, strict=False)
    entitlements = PersonToolEntitlementPanel.model_validate(entitlements_raw, strict=False)
    output = run_module({
        "tool_registry": tool_registry_to_gateway(registry),
        "person_tool_entitlement_panel": entitlements_to_gateway(entitlements),
        "tool_gateway_config": ToolGatewayConfig.model_validate(load_yaml(root / "config/resources/s16/tool_gateway_config.yaml"), strict=False),
        "provider_adapter_registry_config": provider_registry_to_gateway(providers),
    }, {"service": MCPToolGatewayPolicyBuilder(event_sink=ListEventSink())})["mcp_gateway_policy"]
    assert output["tool_registry_hash"] == registry.content_hash
    assert output["entitlement_panel_hash"] == entitlements.content_hash
    assert output["global_controls"]["audit_required"] is True
