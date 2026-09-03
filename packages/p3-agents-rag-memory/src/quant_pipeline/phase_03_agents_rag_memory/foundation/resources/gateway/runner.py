from __future__ import annotations

from .models import MCPGatewayPolicy, PersonToolEntitlementPanel, ProviderAdapterRegistry, ToolCallAuditContract, ToolGatewayConfig, ToolRegistryArtifact
from .module_m01 import MCPToolGatewayPolicyBuilder
from .module_m02 import ToolCallAuditContractBuilder


class P3S16Runner:
    def __init__(self, *, policy_builder: MCPToolGatewayPolicyBuilder, audit_builder: ToolCallAuditContractBuilder) -> None:
        self._policy_builder = policy_builder
        self._audit_builder = audit_builder

    def run(self, *, tool_registry: ToolRegistryArtifact, person_tool_entitlement_panel: PersonToolEntitlementPanel,
            tool_gateway_config: ToolGatewayConfig, provider_adapter_registry_config: ProviderAdapterRegistry) -> tuple[MCPGatewayPolicy, ToolCallAuditContract]:
        policy = self._policy_builder.run(tool_registry=tool_registry, person_tool_entitlement_panel=person_tool_entitlement_panel,
                                          tool_gateway_config=tool_gateway_config,
                                          provider_adapter_registry_config=provider_adapter_registry_config)
        contract = self._audit_builder.run(mcp_gateway_policy=policy)
        return policy, contract
