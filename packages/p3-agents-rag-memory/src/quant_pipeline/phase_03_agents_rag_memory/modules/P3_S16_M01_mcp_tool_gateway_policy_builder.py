from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.resources.gateway.module_m01 import MCPToolGatewayPolicyBuilder
from ..foundation.resources.gateway.models import (
    PersonToolEntitlementPanel, ProviderAdapterRegistry, ToolGatewayConfig, ToolRegistryArtifact,
)
from ._runtime import require_service

MODULE_ID = "P3.S16.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "mcp_tool_gateway_policy_builder"
SUBPHASE = "P3.S16"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S16.M01")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the fail-closed gateway policy from canonical tool contracts."""
    service = require_service(config, expected_type=MCPToolGatewayPolicyBuilder)
    result = service.run(
        tool_registry=ToolRegistryArtifact.model_validate(inputs["tool_registry"], strict=False),
        person_tool_entitlement_panel=PersonToolEntitlementPanel.model_validate(inputs["person_tool_entitlement_panel"], strict=False),
        tool_gateway_config=ToolGatewayConfig.model_validate(inputs["tool_gateway_config"], strict=False),
        provider_adapter_registry_config=ProviderAdapterRegistry.model_validate(inputs["provider_adapter_registry_config"], strict=False),
    )
    return {"mcp_gateway_policy": result.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S16_M01_mcp_tool_gateway_policy_builder.yaml'
REQUIRED_INPUTS = ('tool_registry', 'person_tool_entitlement_panel', 'tool_gateway_config', 'provider_adapter_registry_config')
PRODUCED_OUTPUTS = ('mcp_gateway_policy',)
