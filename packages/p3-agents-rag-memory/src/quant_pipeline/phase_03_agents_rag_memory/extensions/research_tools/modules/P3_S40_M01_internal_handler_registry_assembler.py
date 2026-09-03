"""Canonical extension entrypoint for P3.S40.M01."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.runtime.assembly import execute_m01

MODULE_ID = "P3.S40.M01"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "internal_handler_registry_assembler"
SUBPHASE = "P3.S40"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S40_M01_internal_handler_registry_assembler.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('canonical_tool_operation_registry', 'compatibility_alias_registry', 'research_data_boundary_bundle', 'corpus_index_snapshot', 'corpus_retrieval_policy', 'corpus_internal_work_budget', 'corpus_tool_handler_bundle', 'corpus_operation_mode_qualification', 'corpus_tool_readiness_report', 'market_tool_handler_bundle', 'options_tool_handler_bundle', 'market_derivatives_operation_mode_qualification', 'market_derivatives_tool_readiness_report', 'macro_series_release_catalog', 'macro_asset_context_config_snapshot', 'macro_tool_handler_bundle', 'macro_operation_mode_qualification', 'macro_tool_readiness_report', 'company_operation_readiness_panel', 'company_tool_handler_bundle', 'company_operation_mode_qualification', 'company_qualification_evidence_package', 'quant_tool_handler_bundle', 'quant_operation_mode_qualification', 'quant_qualification_evidence_package')
PRODUCED_OUTPUTS = ('internal_handler_registry', 'handler_registry_completeness_report')


async def execute(
    inputs: Mapping[str, Any],
    context: ModuleExecutionContext,
) -> dict[str, Any]:
    return await execute_m01(inputs, context)
