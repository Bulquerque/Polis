from __future__ import annotations

import json

import pytest
import yaml
from jsonschema import Draft202012Validator

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.models import (
    MCPGatewayPolicy,
    PersonToolEntitlementPanel,
    ToolGatewayConfig,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.models import (
    ToolRegistryArtifact,
)
from quant_pipeline.phase_03_agents_rag_memory.modules.P3_S16_M01_mcp_tool_gateway_policy_builder import (
    run_module as policy_module,
)
from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.gateway.module_m01 import (
    MCPToolGatewayPolicyBuilder,
)
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.resources_internal import (
    entitlements_to_gateway,
    provider_registry_to_gateway,
    tool_registry_to_gateway,
)
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.compatibility.s21_gateway_policy import (
    gateway_policy_projection_receipt,
    project_gateway_policy,
)
from .resource_support import ListEventSink, build_s15_outputs, load_yaml


@pytest.mark.asyncio
async def test_s16_policy_matches_bound_json_schema(root) -> None:
    registry_raw, entitlements_raw, providers, _ = await build_s15_outputs(root)
    registry = ToolRegistryArtifact.model_validate(registry_raw, strict=False)
    entitlements = PersonToolEntitlementPanel.model_validate(entitlements_raw, strict=False)
    policy_raw = policy_module(
        {
            "tool_registry": tool_registry_to_gateway(registry),
            "person_tool_entitlement_panel": entitlements_to_gateway(entitlements),
            "tool_gateway_config": ToolGatewayConfig.model_validate(
                load_yaml(root / "config/resources/s16/tool_gateway_config.yaml"), strict=False
            ),
            "provider_adapter_registry_config": provider_registry_to_gateway(providers),
        },
        {"service": MCPToolGatewayPolicyBuilder(event_sink=ListEventSink())},
    )["mcp_gateway_policy"]
    policy = MCPGatewayPolicy.model_validate(policy_raw, strict=False)
    schema = yaml.safe_load(
        (root / "schemas/mcp_gateway_policy.schema.yaml").read_text(encoding="utf-8")
    )
    errors = sorted(
        Draft202012Validator(schema).iter_errors(policy.model_dump(mode="json")),
        key=lambda error: list(error.path),
    )
    assert not errors, "bound mcp_gateway_policy schema rejected the real S16 artifact: " + json.dumps(
        [error.message for error in errors], ensure_ascii=False
    )
    assert schema["schema_id"] == "mcp_gateway_policy.v2"
    assert schema["schema_version"] == "2.0.0"


@pytest.mark.asyncio
async def test_s16_policy_projects_through_single_s21_adapter(root) -> None:
    registry_raw, entitlements_raw, providers, _ = await build_s15_outputs(root)
    registry = ToolRegistryArtifact.model_validate(registry_raw, strict=False)
    entitlements = PersonToolEntitlementPanel.model_validate(entitlements_raw, strict=False)
    policy = MCPGatewayPolicy.model_validate(
        policy_module(
            {
                "tool_registry": tool_registry_to_gateway(registry),
                "person_tool_entitlement_panel": entitlements_to_gateway(entitlements),
                "tool_gateway_config": ToolGatewayConfig.model_validate(
                    load_yaml(root / "config/resources/s16/tool_gateway_config.yaml"), strict=False
                ),
                "provider_adapter_registry_config": provider_registry_to_gateway(providers),
            },
            {"service": MCPToolGatewayPolicyBuilder(event_sink=ListEventSink())},
        )["mcp_gateway_policy"],
        strict=False,
    )
    projected = project_gateway_policy(policy)
    receipt = gateway_policy_projection_receipt(policy, projected)
    assert projected.schema_version == "p3.s21.v1"
    assert projected.pit_required is True
    assert projected.credential_policy == "handle_only"
    assert receipt["source_schema_id"] == "mcp_gateway_policy.v2"
    assert receipt["target_schema_id"] == "p3.s21.gateway_policy.v1"
    assert len(receipt["receipt_hash"]) == 64
