"""Canonical extension entrypoint for P3.S40.M02."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import execute_m02

MODULE_ID = "P3.S40.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "composite_tool_gateway_runtime_factory"
SUBPHASE = "P3.S40"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S40_M02_composite_tool_gateway_runtime_factory.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('internal_handler_registry', 'handler_registry_completeness_report', 'research_tool_extension_snapshot')
PRODUCED_OUTPUTS = ('composite_tool_gateway_binding_manifest', 'gateway_runtime_readiness_report')


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    return await execute_m02(inputs, context)
