"""Canonical extension entrypoint for P3.S40.M08."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import execute_m08

MODULE_ID = "P3.S40.M08"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "research_tool_extension_release_gate"
SUBPHASE = "P3.S40"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S40_M08_research_tool_extension_release_gate.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('handler_registry_completeness_report', 's21_runtime_preflight_report', 'operation_mode_qualification_matrix', 'research_tool_leakage_report', 'qualification_evidence_manifest', 'phase4_research_process_handoff_manifest', 'p4_research_handoff_compatibility_report', 'p9_research_tool_learning_handoff_manifest', 'p9_consumer_compatibility_report', 'contract_test_report', 'schema_test_report', 'code_quality_report', 'hash_integrity_report', 'rollback_report')
PRODUCED_OUTPUTS = ('research_tool_extension_release_gate', 'research_tool_extension_evidence_package', 'research_tool_extension_blocking_issue_panel')


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    return await execute_m08(inputs, context)
