"""Canonical entrypoint for P3.S38.M02."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.assembly import execute_m02

MODULE_ID = "P3.S38.M02"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "company_profile_filing_xbrl_handler_bundle_builder"
SUBPHASE = "P3.S38"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S38_M02_company_profile_filing_xbrl_handler_bundle_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('company_operation_readiness_panel', 'research_data_boundary_bundle', 'temporal_entity_resolution_service', 'company_profile_policy_config')
PRODUCED_OUTPUTS = ('company_profile_filing_handler_bundle', 'company_profile_handler_qualification_report')


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m02(inputs, context)
