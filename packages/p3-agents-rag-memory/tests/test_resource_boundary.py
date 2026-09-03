from __future__ import annotations

from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.foundation.resources.tool_registry.models import (
    PersonToolEntitlementPanel,
    ToolRegistryArtifact,
)
from quant_pipeline.phase_03_agents_rag_memory.shared.adapters.resources_internal import (
    entitlements_to_gateway,
    tool_registry_to_gateway,
)


def test_tool_registry_and_gateway_share_one_contract(resource_outputs: dict[str, Any]) -> None:
    registry = ToolRegistryArtifact.model_validate(resource_outputs["tool_registry"], strict=False)
    entitlements = PersonToolEntitlementPanel.model_validate(
        resource_outputs["person_tool_entitlement_panel"], strict=False
    )

    gateway_registry = tool_registry_to_gateway(registry)
    gateway_entitlements = entitlements_to_gateway(entitlements)

    assert gateway_registry.content_hash == registry.content_hash
    assert gateway_entitlements.content_hash == entitlements.content_hash
    assert gateway_entitlements.tool_registry_hash == gateway_registry.content_hash
