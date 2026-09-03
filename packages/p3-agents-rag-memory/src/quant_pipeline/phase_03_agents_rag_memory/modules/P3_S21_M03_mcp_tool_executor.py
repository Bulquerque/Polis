from __future__ import annotations

from ._deprecation import deprecated_legacy_entrypoint

from ..contracts import ModuleExecutionContext

from collections.abc import Mapping

from ..runtime.tooling import execute_tool_requests
from ..runtime_shared.s21_models import (
    MCPGatewayPolicy,
    ProviderAdapterRegistryConfig,
    ToolCallAuditContract,
    ValidatedToolCallRequestPanel,
)
from ..runtime_shared.s21_ports import S21Runtime
from ._s21_wrapper import parse_model, run_sync, serialize_outputs

MODULE_ID = "P3.S21.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "mcp_tool_executor"
SUBPHASE = "P3.S21"
CONTRACT = "modules/P3_S21_M03_mcp_tool_executor.yaml"
REQUIRED_SERVICES = ("runtime",)
REQUIRED_INPUTS = ['validated_tool_call_request_panel', 'mcp_gateway_policy', 'tool_call_audit_contract', 'provider_adapter_registry_config']
PRODUCED_OUTPUTS = ('raw_tool_result_panel', 'tool_call_audit_panel', 'tool_discovery_event_panel')
IMPLEMENTED = True


@deprecated_legacy_entrypoint("P3.S21.M03")
async def run_module_async(
    inputs: Mapping[str, object], *, runtime: S21Runtime
) -> dict[str, object]:
    outputs = await execute_tool_requests(
        validated_requests=parse_model(
            inputs,
            "validated_tool_call_request_panel",
            ValidatedToolCallRequestPanel,
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
        provider_registry=parse_model(
            inputs,
            "provider_adapter_registry_config",
            ProviderAdapterRegistryConfig,
            module_id=MODULE_ID,
        ),
        runtime=runtime,
    )
    return serialize_outputs(outputs)


@deprecated_legacy_entrypoint("P3.S21.M03")
def run_module(
    inputs: Mapping[str, object],
    config: Mapping[str, object] | None = None,
    *,
    runtime: S21Runtime,
) -> dict[str, object]:
    del config
    return run_sync(run_module_async(inputs, runtime=runtime), module_id=MODULE_ID)

async def execute(
    inputs: "Mapping[str, Any]",
    context: "ModuleExecutionContext",
) -> dict[str, Any]:
    """Execute tools through the canonical context-injected runtime."""
    runtime = context.services.get("runtime")
    if runtime is None:
        raise TypeError("ModuleExecutionContext.services['runtime'] is required")
    return dict(await run_module_async(inputs, runtime=runtime))



# Canonical Phase 3 module metadata.
IMPLEMENTATION_STATUS = 'IMPLEMENTED_QUALIFIED_INTERNAL'
