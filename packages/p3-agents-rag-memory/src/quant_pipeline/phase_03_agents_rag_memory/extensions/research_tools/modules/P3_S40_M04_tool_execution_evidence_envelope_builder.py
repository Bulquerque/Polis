"""Canonical extension entrypoint for P3.S40.M04."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import execute_m04

MODULE_ID = "P3.S40.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "tool_execution_evidence_envelope_builder"
SUBPHASE = "P3.S40"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S40_M04_tool_execution_evidence_envelope_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('raw_tool_result_panel', 'tool_call_audit_panel', 'retrieval_evidence_map', 'phase3_run_snapshot')
PRODUCED_OUTPUTS = ('research_tool_result_envelope_panel', 'research_tool_evidence_map', 'extended_retrieval_evidence_map', 'research_tool_execution_trace_panel')


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    return await execute_m04(inputs, context)
