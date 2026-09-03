from __future__ import annotations

import pytest
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.models import MCPGatewayPolicy, ToolGatewayConfig
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.module_m01 import MCPToolGatewayPolicyBuilder
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.module_m02 import ToolCallAuditContractBuilder
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.models import PersonToolEntitlementPanel, ToolRegistryArtifact
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S16_M01_mcp_tool_gateway_policy_builder import run_module as policy_module
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S16_M02_tool_call_audit_contract_builder import run_module as audit_module
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.resources_internal import entitlements_to_gateway, provider_registry_to_gateway, tool_registry_to_gateway
from .resource_support import ListEventSink, build_s15_outputs, load_yaml


@pytest.mark.asyncio
async def test_entitlement_policy_audit_contract_pipeline(root):
    registry_raw, entitlements_raw, providers, _ = await build_s15_outputs(root)
    registry = ToolRegistryArtifact.model_validate(registry_raw, strict=False)
    entitlements = PersonToolEntitlementPanel.model_validate(entitlements_raw, strict=False)
    policy_raw = policy_module({
        "tool_registry": tool_registry_to_gateway(registry),
        "person_tool_entitlement_panel": entitlements_to_gateway(entitlements),
        "tool_gateway_config": ToolGatewayConfig.model_validate(load_yaml(root / "config/resources/s16/tool_gateway_config.yaml"), strict=False),
        "provider_adapter_registry_config": provider_registry_to_gateway(providers),
    }, {"service": MCPToolGatewayPolicyBuilder(event_sink=ListEventSink())})["mcp_gateway_policy"]
    audit = audit_module({"mcp_gateway_policy": MCPGatewayPolicy.model_validate(policy_raw, strict=False)}, {"service": ToolCallAuditContractBuilder(event_sink=ListEventSink())})["tool_call_audit_contract"]
    assert policy_raw["global_controls"]["pit_required"] is True
    assert policy_raw["global_controls"]["audit_required"] is True
    assert policy_raw["global_controls"]["provider_failure_policy"] == "MATERIAL_NO_FAKE_SUCCESS"
    assert audit["fake_success_forbidden"] is True
    assert {"EXECUTION_SUCCEEDED", "EXECUTION_FAILED"} <= set(audit["terminal_event_types"])
