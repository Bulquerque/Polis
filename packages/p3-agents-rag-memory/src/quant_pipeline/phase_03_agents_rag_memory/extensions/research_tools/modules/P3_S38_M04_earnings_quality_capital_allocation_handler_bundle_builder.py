"""Canonical entrypoint for P3.S38.M04."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.assembly import execute_m04

MODULE_ID = "P3.S38.M04"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "earnings_quality_capital_allocation_handler_bundle_builder"
SUBPHASE = "P3.S38"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S38_M04_earnings_quality_capital_allocation_handler_bundle_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('financial_statement_handler_bundle', 'research_data_boundary_bundle', 'company_formula_registry', 'company_operation_readiness_panel')
PRODUCED_OUTPUTS = ('earnings_quality_capital_allocation_handler_bundle', 'company_formula_registry_manifest')


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m04(inputs, context)
