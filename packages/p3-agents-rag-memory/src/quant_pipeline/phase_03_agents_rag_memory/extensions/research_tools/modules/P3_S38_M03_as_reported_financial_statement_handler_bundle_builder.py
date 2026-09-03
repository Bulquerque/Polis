"""Canonical entrypoint for P3.S38.M03."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.assembly import execute_m03

MODULE_ID = "P3.S38.M03"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "as_reported_financial_statement_handler_bundle_builder"
SUBPHASE = "P3.S38"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S38_M03_as_reported_financial_statement_handler_bundle_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('company_operation_readiness_panel', 'research_data_boundary_bundle', 'company_statement_policy_config', 'statement_concept_mapping_registry')
PRODUCED_OUTPUTS = ('financial_statement_handler_bundle', 'statement_semantics_manifest')


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m03(inputs, context)
