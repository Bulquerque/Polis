"""Canonical extension entrypoint for P3.S40.M06."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import execute_m06

MODULE_ID = "P3.S40.M06"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "research_process_panel_p4_handoff_builder"
SUBPHASE = "P3.S40"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S40_M06_research_process_panel_p4_handoff_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('validated_tool_result_panel', 'tool_call_audit_panel', 'research_tool_result_envelope_panel', 'evidence_bound_belief_update_panel', 'phase3_run_snapshot', 'canonical_tool_operation_registry', 'research_mode_registry')
PRODUCED_OUTPUTS = ('research_process_panel', 'phase4_research_process_handoff_manifest', 'p4_research_handoff_compatibility_report')


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    return await execute_m06(inputs, context)
