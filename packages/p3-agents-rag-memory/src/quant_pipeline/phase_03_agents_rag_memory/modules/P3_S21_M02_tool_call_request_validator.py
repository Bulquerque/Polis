from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.tooling import validate_tool_requests
from ..runtime_shared.s21_models import (
    MCPGatewayPolicy,
    PersonToolEntitlementPanel,
    ToolCallAuditContract,
    ToolCallRequestPanel,
)
from ._s21_wrapper import parse_model

MODULE_ID = "P3.S21.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "tool_call_request_validator"
SUBPHASE = "P3.S21"
CONTRACT = "modules/P3_S21_M02_tool_call_request_validator.yaml"
REQUIRED_INPUTS = ['tool_call_request_panel', 'person_tool_entitlement_panel', 'mcp_gateway_policy', 'tool_call_audit_contract']
PRODUCED_OUTPUTS = ('validated_tool_call_request_panel',)
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S21.M02")
def run_module(
    inputs: Mapping[str, object],
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    del config
    output = validate_tool_requests(
        requests=parse_model(
            inputs, "tool_call_request_panel", ToolCallRequestPanel, module_id=MODULE_ID
        ),
        entitlements=parse_model(
            inputs,
            "person_tool_entitlement_panel",
            PersonToolEntitlementPanel,
            module_id=MODULE_ID,
        ),
        gateway_policy=parse_model(
            inputs, "mcp_gateway_policy", MCPGatewayPolicy, module_id=MODULE_ID
        ),
        audit_contract=parse_model(
            inputs,
            "tool_call_audit_contract",
            ToolCallAuditContract,
            module_id=MODULE_ID,
        ),
    )
    return {"validated_tool_call_request_panel": output.model_dump(mode="json")}

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute through the canonical P3 module facade."""
    from ._canonical import invoke_legacy_entrypoint

    return dict(await invoke_legacy_entrypoint(globals(), inputs, context))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
