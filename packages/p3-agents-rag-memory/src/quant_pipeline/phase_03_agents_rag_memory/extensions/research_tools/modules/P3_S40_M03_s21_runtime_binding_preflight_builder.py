"""Canonical extension entrypoint for P3.S40.M03."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import execute_m03

MODULE_ID = "P3.S40.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "s21_runtime_binding_preflight_builder"
SUBPHASE = "P3.S40"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S40_M03_s21_runtime_binding_preflight_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('internal_handler_registry', 'handler_registry_completeness_report', 'composite_tool_gateway_binding_manifest', 'gateway_runtime_readiness_report', 'provider_adapter_registry_config', 'mcp_gateway_policy', 'extended_person_tool_entitlement_panel', 'extended_validated_person_context_bundle', 'canonical_tool_operation_registry', 'research_tool_extension_snapshot')
PRODUCED_OUTPUTS = ('s21_research_tool_runtime_binding_manifest', 's21_runtime_preflight_report')


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    return await execute_m03(inputs, context)
