from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from typing import Any

from ..foundation.resources.gateway.module_m02 import ToolCallAuditContractBuilder
from ..foundation.resources.gateway.models import MCPGatewayPolicy
from ._runtime import require_service

MODULE_ID = "P3.S16.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "tool_call_audit_contract_builder"
SUBPHASE = "P3.S16"
IMPLEMENTATION_STATUS = "IMPLEMENTED_QUALIFIED_INTERNAL"


@deprecated_legacy_entrypoint("P3.S16.M02")
def run_module(
    inputs: dict[str, Any],
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the immutable audit contract for later tool executions."""
    service = require_service(config, expected_type=ToolCallAuditContractBuilder)
    result = service.run(mcp_gateway_policy=MCPGatewayPolicy.model_validate(inputs["mcp_gateway_policy"], strict=False))
    return {"tool_call_audit_contract": result.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
CONTRACT = 'modules/P3_S16_M02_tool_call_audit_contract_builder.yaml'
REQUIRED_INPUTS = ('mcp_gateway_policy',)
PRODUCED_OUTPUTS = ('tool_call_audit_contract',)
