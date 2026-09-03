"""Canonical entrypoint for P3.S38.M01."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.assembly import execute_m01

MODULE_ID = "P3.S38.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "company_operation_readiness_gate_builder"
SUBPHASE = "P3.S38"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S38_M01_company_operation_readiness_gate_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('research_tool_extension_snapshot', 'tool_operation_registry', 'research_mode_registry', 'research_data_boundary_bundle', 'phase2_research_view_manifest', 'company_readiness_policy_config')
PRODUCED_OUTPUTS = ('company_operation_readiness_panel', 'company_data_gap_report')


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m01(inputs, context)
