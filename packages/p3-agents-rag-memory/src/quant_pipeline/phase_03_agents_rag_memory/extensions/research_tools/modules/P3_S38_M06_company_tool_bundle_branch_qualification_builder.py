"""Canonical entrypoint for P3.S38.M06."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.assembly import execute_m06

MODULE_ID = "P3.S38.M06"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "company_tool_bundle_branch_qualification_builder"
SUBPHASE = "P3.S38"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S38_M06_company_tool_bundle_branch_qualification_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('company_profile_filing_handler_bundle', 'financial_statement_handler_bundle', 'earnings_quality_capital_allocation_handler_bundle', 'guidance_peers_valuation_handler_bundle', 'company_operation_readiness_panel', 'company_contract_test_report', 'company_leakage_test_report')
PRODUCED_OUTPUTS = ('company_tool_handler_bundle', 'company_operation_mode_qualification', 'company_qualification_evidence_package')


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m06(inputs, context)
