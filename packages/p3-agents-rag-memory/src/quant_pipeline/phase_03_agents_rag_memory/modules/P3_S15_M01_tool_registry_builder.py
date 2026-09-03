from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.resources.tool_registry.module_m01 import ToolRegistryBuilder
from ._runtime import require_service

MODULE_ID = "P3.S15.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "tool_registry_builder"
SUBPHASE = "P3.S15"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S15.M01")
async def run_module_async(
    inputs: dict[str, Any],
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the qualified tool registry through an injected service."""
    service = require_service(config, expected_type=ToolRegistryBuilder)
    result = await service.run(
        config=inputs["tool_registry_config"],
        provider_registry=inputs["provider_adapter_registry_config"],
        active_retro_policy_patch=inputs.get("active_retro_policy_patch"),
    )
    return {"tool_registry": result.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S15_M01_tool_registry_builder.yaml'
REQUIRED_INPUTS = ('tool_registry_config', 'active_retro_policy_patch', 'provider_adapter_registry_config')
PRODUCED_OUTPUTS = ('tool_registry',)
