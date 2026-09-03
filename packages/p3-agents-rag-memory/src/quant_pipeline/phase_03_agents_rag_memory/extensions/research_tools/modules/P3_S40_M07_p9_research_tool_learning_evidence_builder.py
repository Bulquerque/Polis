"""Canonical extension entrypoint for P3.S40.M07."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import execute_m07

MODULE_ID = "P3.S40.M07"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "p9_research_tool_learning_evidence_builder"
SUBPHASE = "P3.S40"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S40_M07_p9_research_tool_learning_evidence_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('research_process_panel', 'belief_outcome_commitment_log', 'research_tool_execution_trace_panel', 'phase3_run_snapshot', 'model_knowledge_cutoff_report')
PRODUCED_OUTPUTS = ('p9_research_tool_learning_evidence', 'p9_research_tool_learning_handoff_manifest', 'p9_consumer_compatibility_report')


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    return await execute_m07(inputs, context)
