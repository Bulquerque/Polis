"""Canonical extension entrypoint for P3.S40.M05."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import execute_m05

MODULE_ID = "P3.S40.M05"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "operation_mode_qualification_leakage_runner"
SUBPHASE = "P3.S40"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S40_M05_operation_mode_qualification_leakage_runner.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('corpus_operation_mode_qualification', 'market_derivatives_operation_mode_qualification', 'macro_operation_mode_qualification', 'company_operation_mode_qualification', 'quant_operation_mode_qualification', 's21_runtime_preflight_report', 'handler_registry_completeness_report', 'integration_test_receipts', 'leakage_test_receipts', 'replay_test_receipts')
PRODUCED_OUTPUTS = ('operation_mode_qualification_matrix', 'research_tool_leakage_report', 'qualification_evidence_manifest')


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    return await execute_m05(inputs, context)
