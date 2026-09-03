"""Canonical entrypoint for P3.S38.M05."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quant_pipeline.phase_03_agents_rag_memory.contracts import ModuleExecutionContext
from quant_pipeline.phase_03_agents_rag_memory.extensions.research_tools.families.company.assembly import execute_m05

MODULE_ID = "P3.S38.M05"
LEGACY_ENTRYPOINT_DEPRECATED = True
MODULE_NAME = "guidance_peers_valuation_handler_bundle_builder"
SUBPHASE = "P3.S38"
CONTRACT = "contracts/extensions/research_tools/modules/P3_S38_M05_guidance_peers_valuation_handler_bundle_builder.yaml"
IMPLEMENTATION_STATUS = "IMPLEMENTED_LOCAL_QUALIFICATION_REQUIRED"
REQUIRED_INPUTS = ('company_operation_readiness_panel', 'research_data_boundary_bundle', 'guidance_policy_config', 'peer_authority_policy_config', 'valuation_method_registry', 'company_profile_filing_handler_bundle', 'financial_statement_handler_bundle')
PRODUCED_OUTPUTS = ('guidance_peers_valuation_handler_bundle', 'valuation_method_registry_manifest')


async def execute(inputs: Mapping[str, Any], context: ModuleExecutionContext) -> dict[str, Any]:
    return execute_m05(inputs, context)
